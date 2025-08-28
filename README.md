# Structure Agent API

A Azure Functions-based API that uses Azure AI Agents to help define structural engineering requirements and return them in a standardized JSON format.

## Features

- **Structural Engineering Expert**: AI agent specialized in gathering structural requirements
- **Interactive Workflow**: Guides users through requirement definition with intelligent questioning
- **Standardized Output**: Returns requirements in consistent JSON format
- **Job Execution**: Two-step process for requirement definition and execution confirmation
- **CORS Enabled**: Ready for web application integration

## Prerequisites

- Python 3.8+
- Azure CLI
- Azure AI Foundry project with deployed model
- Azure subscription with appropriate permissions

## Setup

### 1. Clone and Install Dependencies

```bash
git clone <your-repo-url>
cd create-structure-api
python -m venv .venv
.venv\Scripts\activate  # Windows
# or
source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
```

### 2. Azure Authentication

Login to Azure CLI:
```bash
az login
```

Ensure you have the **Azure AI Developer** role on your Azure AI project resource.

### 3. Environment Configuration

Update `local.settings.json` with your Azure AI project details:

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "PROJECT_ENDPOINT": "https://your-project.services.ai.azure.com/api/projects/your-project-name",
    "MODEL_DEPLOYMENT_NAME": "your-model-deployment-name"
  }
}
```

**Where to find these values:**
- **PROJECT_ENDPOINT**: Azure AI Foundry project → Overview → Project details
- **MODEL_DEPLOYMENT_NAME**: Your deployed model name (e.g., "gpt-4o-mini", "gpt-5-chat")

### 4. Run Locally

```bash
func host start
```

The API will be available at `http://localhost:7071`

## API Usage

### Endpoint
```
POST/GET http://localhost:7071/api/structure_agent
```

### Request Format

**JSON Body (recommended):**
```json
{
  "prompt": "Your structural engineering question or requirements",
  "debug": true  // Optional: adds debug information to responses
}
```

**Query Parameter (alternative):**
```
GET http://localhost:7071/api/structure_agent?prompt=Your question&debug=1
```

### Response Format

**Standard Response:**
```json
{
  "response": "Agent's response text",
  "run_status": "completed",
  "agent_id": "asst_...",
  "thread_id": "thread_..."
}
```

**With Debug Info:**
```json
{
  "response": "Agent's response text",
  "run_status": "completed", 
  "agent_id": "asst_...",
  "thread_id": "thread_...",
  "debug_messages": [...],
  "total_messages": 2
}
```

## Workflow Examples

### Example 1: Complete Requirements Provided
```bash
curl -X POST http://localhost:7071/api/structure_agent \
  -H "Content-Type: application/json" \
  -d '{"prompt": "I need a structure at coordinates 10,15,20 meters, cutoff frequency 30 Hz, max load 5G"}'
```

**Response:**
```json
{
  "response": "{\n  \"structure_requirements\": {\n    \"xyz_coordinates_m\": [10, 15, 20],\n    \"cutoff_frequency_hz\": 30,\n    \"max_load_n\": 5\n  }\n}\n\nWould you like me to proceed with running the job to create this structure?",
  "run_status": "completed",
  "agent_id": "asst_...",
  "thread_id": "thread_..."
}
```

### Example 2: Partial Requirements (Follow-up Needed)
```bash
curl -X POST http://localhost:7071/api/structure_agent \
  -H "Content-Type: application/json" \
  -d '{"prompt": "I need a structure that can handle 500N load"}'
```

**Agent will ask for missing information:**
- XYZ coordinates
- Cutoff frequency

### Example 3: Job Execution Confirmation
After receiving the JSON structure, respond with:
```bash
curl -X POST http://localhost:7071/api/structure_agent \
  -H "Content-Type: application/json" \
  -d '{"prompt": "yes"}'
```

**Response:**
```json
{
  "response": "Completed job!",
  "run_status": "completed",
  "agent_id": "asst_...",
  "thread_id": "thread_..."
}
```

## Target JSON Structure

The agent aims to collect information for this structure:

```json
{
  "structure_requirements": {
    "xyz_coordinates_m": [x, y, z],    // Position in meters
    "cutoff_frequency_hz": number,     // Frequency in Hz
    "max_load_n": number              // Maximum load in Newtons
  }
}
```

## Web Application Integration

The API includes CORS headers for web application integration:

```javascript
// Example JavaScript fetch
fetch('http://localhost:7071/api/structure_agent', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    prompt: 'I need structural requirements for a space platform'
  })
})
.then(response => response.json())
.then(data => {
  console.log('Agent response:', data.response);
});
```

## Troubleshooting

### Common Issues

**1. Permission Denied Error**
```
PermissionDenied: lacks required data action Microsoft.CognitiveServices/accounts/AIServices/agents/write
```
**Solution:** Assign "Azure AI Developer" role to your user on the Azure AI project resource.

**2. Import Errors**
```
ImportError: cannot import name 'MessageRole' from 'azure.ai.agents'
```
**Solution:** These have been resolved in the current version. Ensure you've run `pip install -r requirements.txt`.

**3. Authentication Issues**
**Solution:** 
- Run `az login` 
- Verify you're in the correct subscription: `az account show`
- If multiple subscriptions: `az account set --subscription "your-subscription-id"`

**4. No Response Content**
**Solution:** Add `?debug=1` to see debug information about message parsing.

### Debug Mode

Enable debug mode for troubleshooting:
```bash
curl -X POST "http://localhost:7071/api/structure_agent?debug=1" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "test prompt"}'
```

This provides additional information about:
- Message parsing details
- Run steps and status
- Available object attributes
- Error traces

## Project Structure

```
create-structure-api/
├── function_app.py           # Main Azure Function
├── agent_instructions.py     # Agent system instructions
├── requirements.txt          # Python dependencies
├── local.settings.json       # Local configuration
├── host.json                 # Azure Functions host config
└── README.md                # This file
```

## Deployment

For production deployment to Azure:

1. Create Azure Function App
2. Set environment variables in Azure portal
3. Deploy using Azure Functions Core Tools:
   ```bash
   func azure functionapp publish <your-function-app-name>
   ```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test locally
5. Submit a pull request

## License

[Your License Here]
