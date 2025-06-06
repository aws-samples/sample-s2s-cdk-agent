# Telecom Industry Demo Setup Guide

This guide will help you set up and deploy the Amazon Nova Sonic Call Center Agent demo specifically configured for the telecom industry.

## Overview

The telecom demo includes:
- Customer profile lookup tool with telecom-specific customer data
- Knowledge base integration for telecom FAQs, plans, and policies

## Setup Instructions

### 1. Environment Configuration

1. Create a copy of the root `template.env` as `.env`:
   ```bash
   cp ../template.env .env
   ```

2. Edit the `.env` file with your specific configuration:
   - `ENV`: Your deployment environment (e.g., "dev", "prod")
   - `VPC_ID`: (Optional) Your VPC ID if you want to use an existing VPC
   - `KNOWLEDGE_BASE_ID`: Your Amazon Bedrock Knowledge Base ID containing telecom FAQs, plans, and policies
   - `DYNAMODB_TABLE_NAME`: Your DynamoDB table name for customer data (e.g telco_demo_customer_data). This DynamoDB table will be automatically created (if doesn't exist), in step "2. Sample data import" below or as part of the deployment script (by running ./deploy-industry-sepecific-demo.py).

3. `.env` will be automatically copied to backend folder by the deployment script.

### 2. Knowledge Base Setup

For optimal performance, your knowledge base should contain information about:
- Telecom plans and pricing
- Device upgrade policies
- International roaming information
- Troubleshooting common issues
- Billing policies

The agent will use this knowledge base to provide accurate information to customers.

### 3. Sample Data Import

Note: You can skip this step and go to "Deployment" step where you will be prompted for option to import data. Use following steps to import data if you are customising the sample data or import script and want to test the import script without running the full deployment. 

The `sample-data` directory contains:
- `telco_customer_sample_data.csv`: Sample customer profiles with telecom-specific fields like:
  - Current plan details
  - Monthly bill amount
  - Data usage
  - Contract information
  - Account status

1. Navigate to the sample-data directory:
   ```bash
   cd sample-data
   ```

2. Install required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the import script:
   ```bash
   python import_data_to_dynamodb.py
   ```


### 4. Deployment

Return to the project root directory and run the deployment script:
```bash
cd ../
./deploy-industry-sepecific-demo.py
```

When prompted, select "telco" as your industry-specific demo.

## Testing the Demo

After deployment:
1. Access the frontend URL provided in the deployment output
2. Sign in with your Cognito credentials
3. Start a conversation with the agent
4. Try queries like:
   - "I want to check my current plan"
   - "Tell me about your unlimited plans"
   - "I'm having trouble with my connection"
   - "What are my international roaming options?"

## Customization

You can customize the demo by:
- Adding more data to your knowledge base
- Modifying the customer data structure
- Extending the tools in the `tools` directory
- Adding additional telecom-specific functionality

## Adding Custom Tools

The telecom demo uses the Model Context Protocol (MCP) to implement tools that Amazon Nova Sonic can use during conversations. You can add your own custom tools by following these steps:

### 1. Create a New Tool Implementation

1. Create a new Python file in the `tools` directory (e.g., `network_status_checker.py`)
2. Implement your tool functionality with a `main()` function that accepts the necessary parameters and returns a dictionary result:

```python
# network_status_checker.py
def main(zip_code):
    # Your tool implementation here
    # This could check for network outages in a specific area
    result = {
        "status": "success",
        "data": {
            "area_status": "operational",
            "last_outage": "2025-04-15",
            "current_signal_strength": "excellent"
        }
    }
    return result
```

### 2. Register Your Tool in the MCP Tool Registry

Open `mcp_tool_registry.py` and add your new tool:

1. Import your tool module at the top:
```python
from . import network_status_checker
```

2. Create a new tool function with the MCP decorator:
```python
@mcp_server.tool(
    name="networkStatusCheck",
    description="Checks the network status and recent outages in a specific area by zip code"
)
async def network_status_check_tool(
    zip_code: Annotated[str, Field(description="the zip code to check network status for")]
) -> dict:
    """Check network status and recent outages in a specific area"""
    try:
        logger.info(f"Network status check for zip code: {zip_code}")
        results = network_status_checker.main(zip_code)
        return results
    except Exception as e:
        logger.error(f"Error in network status check: {str(e)}", exc_info=True)
        return {"status": "error", "error": str(e)}
```

### 3. Tool Design Best Practices

When creating tools for Amazon Nova Sonic:

- **Clear Descriptions**: Write clear descriptions for your tool and parameters so the model knows when and how to use it
- **Proper Error Handling**: Always include try/except blocks to handle errors gracefully
- **Logging**: Include logging statements to help with debugging
- **Return Format**: Return results as a dictionary with a consistent structure
- **Parameter Types**: Use appropriate type annotations with descriptive Field parameters
- **Tool Naming**: Use camelCase for tool names and descriptive names that indicate functionality

### 4. Testing Your Tool

After adding your tool:

1. Deploy the updated code
2. Test your tool by having conversations that would trigger its use
3. Check the CloudWatch logs to verify your tool is being called correctly

The MCP framework will automatically make your tool available to Amazon Nova Sonic during conversations.
