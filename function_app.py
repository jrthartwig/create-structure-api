import azure.functions as func
import logging
import os
import json
import time
import traceback
from typing import Optional

from azure.identity import DefaultAzureCredential
from azure.ai.agents import AgentsClient
from agent_instructions import STRUCTURAL_ENGINEER_INSTRUCTIONS

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


@app.route(route="structure_agent", methods=["POST", "GET", "OPTIONS"])
def structure_agent(req: func.HttpRequest) -> func.HttpResponse:
    """Basic interaction with an Azure AI Agent.\n\n    Request body (JSON): { "prompt": "..." } or query string ?prompt=...\n    Environment variables required:\n      PROJECT_ENDPOINT  -> Azure AI Project endpoint (e.g. https://<your-project>.<region>.models.ai.azure.com)\n      MODEL_DEPLOYMENT_NAME -> Deployed model name within the project (e.g. gpt-4o-mini)\n      (Optional) AGENT_ID -> If provided, reuse existing agent instead of creating each request.\n    """
    
    # Handle CORS preflight requests
    if req.method == "OPTIONS":
        return func.HttpResponse(
            status_code=200,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization"
            }
        )
    
    logging.info("structure_agent function invoked")

    # --- Input Extraction ---
    prompt = req.params.get("prompt")
    debug_flag = (req.params.get("debug") or "").lower() in ("1", "true", "yes")
    if not prompt:
        try:
            body = req.get_json()
        except ValueError:
            body = None
        if body:
            prompt = body.get("prompt")
            if isinstance(body, dict):
                debug_flag = debug_flag or str(body.get("debug")).lower() in ("1", "true", "yes")

    if not prompt:
        return _json_response({"error": "Missing 'prompt'. Supply in JSON body { 'prompt': '...' } or as query parameter ?prompt=..."}, status_code=400)

    # --- Configuration ---
    endpoint = os.getenv("PROJECT_ENDPOINT")
    model_deployment = os.getenv("MODEL_DEPLOYMENT_NAME")
    existing_agent_id = os.getenv("AGENT_ID")

    missing = [name for name, val in [("PROJECT_ENDPOINT", endpoint), ("MODEL_DEPLOYMENT_NAME", model_deployment)] if not val]
    if missing:
        return _json_response({
            "error": "Missing required environment variables.",
            "missing": missing
        }, status_code=500)

    # --- Agent Interaction ---
    try:
        credential = DefaultAzureCredential()
        agents_client = AgentsClient(endpoint=endpoint, credential=credential)

        # Optionally reuse an existing agent if AGENT_ID set; else create ephemeral agent (simple first version)
        if existing_agent_id:
            agent_id = existing_agent_id
        else:
            agent = agents_client.create_agent(
                model=model_deployment,
                name="structure-agent",
                instructions=STRUCTURAL_ENGINEER_INSTRUCTIONS
            )
            agent_id = agent.id

        thread = agents_client.threads.create()
        agents_client.messages.create(
            thread_id=thread.id,
            role="user",
            content=prompt
        )

        run = agents_client.runs.create(thread_id=thread.id, agent_id=agent_id)

        # Basic polling loop (simple first version)
        deadline = time.time() + 60  # 60s timeout
        while run.status in ["queued", "in_progress", "requires_action"]:
            if time.time() > deadline:
                return _json_response({"error": "Agent run timed out", "status": run.status}, status_code=504)
            time.sleep(1)
            run = agents_client.runs.get(thread_id=thread.id, run_id=run.id)
            if run.status == "requires_action":
                # For this basic version we don't support tool calls / approvals.
                return _json_response({"error": "Run requires action (tools/functions not supported in basic version)", "status": run.status}, status_code=501)

        if run.status != "completed":
            failure_payload = {"error": "Run did not complete successfully", "status": run.status, "run_id": run.id}
            if debug_flag:
                # Collect run steps for diagnostics
                try:
                    step_summaries = []
                    for step in agents_client.run_steps.list(thread_id=thread.id, run_id=run.id):
                        step_summaries.append({
                            "id": getattr(step, "id", None),
                            "type": getattr(step, "type", None),
                            "status": getattr(step, "status", None),
                        })
                    failure_payload["run_steps"] = step_summaries
                except Exception as list_ex:  # noqa: BLE001
                    failure_payload["run_steps_error"] = str(list_ex)
                # Try to surface any attributes that look like error messages
                for attr in ["error", "last_error", "failure_reason", "failed_reason", "message"]:
                    val = getattr(run, attr, None)
                    if val and isinstance(val, (str, dict)):
                        failure_payload[attr] = val
                # Add available attributes for debugging (filtered)
                failure_payload["available_attrs"] = [a for a in dir(run) if not a.startswith("_")][:50]
            return _json_response(failure_payload, status_code=502)

        # Retrieve messages and extract last agent response text
        # List messages (remove explicit sort to avoid ListSortOrder import issues)
        messages = agents_client.messages.list(thread_id=thread.id)
        agent_messages = []
        all_messages_debug = []  # For debugging
        
        for msg in messages:
            msg_role = getattr(msg, "role", None)
            all_messages_debug.append({
                "role": msg_role,
                "has_text_messages": hasattr(msg, "text_messages"),
                "has_content": hasattr(msg, "content"),
                "available_attrs": [a for a in dir(msg) if not a.startswith("_")][:20]
            })
            
            # Try multiple role variations and message extraction methods
            if msg_role in ["agent", "assistant"]:
                # Method 1: text_messages attribute
                if hasattr(msg, "text_messages") and msg.text_messages:
                    for block in msg.text_messages:
                        try:
                            if hasattr(block, "text") and hasattr(block.text, "value"):
                                agent_messages.append(block.text.value)
                            elif hasattr(block, "value"):
                                agent_messages.append(block.value)
                            else:
                                agent_messages.append(str(block))
                        except AttributeError:
                            agent_messages.append(str(block))
                
                # Method 2: content attribute (alternative structure)
                elif hasattr(msg, "content") and msg.content:
                    if isinstance(msg.content, list):
                        for content_item in msg.content:
                            if hasattr(content_item, "text") and hasattr(content_item.text, "value"):
                                agent_messages.append(content_item.text.value)
                            elif hasattr(content_item, "value"):
                                agent_messages.append(content_item.value)
                            else:
                                agent_messages.append(str(content_item))
                    elif isinstance(msg.content, str):
                        agent_messages.append(msg.content)
                    else:
                        agent_messages.append(str(msg.content))

        response_text = agent_messages[-1] if agent_messages else "(no response content)"
        
        # Add debug info if no response found
        result_payload = {
            "response": response_text,
            "run_status": run.status,
            "agent_id": agent_id,
            "thread_id": thread.id
        }
        
        if not agent_messages and debug_flag:
            result_payload["debug_messages"] = all_messages_debug
            result_payload["total_messages"] = len(list(messages))

        return _json_response(result_payload)
    except Exception as ex:  # Broad catch for initial version
        logging.exception("Error during agent interaction")
        if debug_flag:
            return _json_response({"error": str(ex), "trace": traceback.format_exc()}, status_code=500)
        return _json_response({"error": str(ex)}, status_code=500)


def _json_response(payload: dict, status_code: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        body=json.dumps(payload),
        status_code=status_code,
        mimetype="application/json",
        headers={
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization"
        }
    )
