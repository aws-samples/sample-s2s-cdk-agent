# Airline Industry Demo Setup Guide

This guide will help you set up and deploy the Amazon Nova Sonic Call Center Agent demo specifically configured for the airline industry.

## Overview

The airline demo includes:
- Customer profile lookup tool with airline-specific customer data
- Flight search capabilities using Amadeus API (optional)
- Knowledge base integration for airline FAQs and policies

## Setup Instructions

### 1. Environment Configuration

1. Create a copy of `template.env` as `.env`:
   ```bash
   cp template.env .env
   ```

2. Edit the `.env` file with your specific configuration:
   - `ENV`: Your deployment environment (e.g., "dev", "prod")
   - `VPC_ID`: (Optional) Your VPC ID if you want to use an existing VPC
   - `KNOWLEDGE_BASE_ID`: Your Amazon Bedrock Knowledge Base ID containing airline FAQs and policies
   - `DYNAMODB_TABLE_NAME`: Your DynamoDB table name for customer data

3. `.env` will be automatically copied to backend folder by the deployment script.

### 2. Sample Data Import

The `sample-data` directory contains:
- `airline_customer_sample_data.csv`: Sample customer data and their upcoming flights.
[IMPORTANT] : Review the csv file and update the departure date to make sure they are in the future. Tools are implemented to only bring upcoming flights.

Note: You can skip rest of the step and go to "Deployment" step where you will be prompted for option to import data. Use following steps to import data if you are customising the sample data or import script and want to test the import script without running the full deployment. 

To import this sample data to your DynamoDB table:

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

### 3. Deployment

Return to the project root directory and run the deployment script:
```bash
cd ../
./deploy-industry-sepecific-demo.py
```

When prompted, select "airline" as your industry-specific demo. 

## Testing the Demo

After deployment:
1. Access the frontend URL provided in the deployment output
2. Create a cognito user by going to AWS Console. Sign in with your Cognito credentials. 
3. Start a conversation with the agent
4. Try queries like:
   - "I want to check my upcoming flights"
   - "I would like to change my meal booking"
   - "I cannot make the flight with booking reference number AYT7AZ, can you please log a support ticket for someone to call me as I would like to discuss cancellation and refund policy."
   - "What's your baggage policy?"
   - "Can i fly with my guide dog on the flight?"

## Customization

You can customize the demo by:
- Adding more data to your knowledge base
- Modifying the customer data structure
- Extending the tools in the `tools` directory

## Adding Custom Tools

The airline demo uses the Model Context Protocol (MCP) to implement tools that Amazon Nova Sonic can use during conversations. You can add your own custom tools by following these steps:

### 1. Create a New Tool Implementation

1. Create a new Python file in the `tools` directory (e.g., `my_custom_tool.py`)
2. Implement your tool functionality with a `main()` function that accepts the necessary parameters and returns a dictionary result:

```python
# my_custom_tool.py
def main(param1, param2):
    # Your tool implementation here
    result = {
        "status": "success",
        "data": {
            # Your tool's response data
            "field1": "value1",
            "field2": "value2"
        }
    }
    return result
```

### 2. Register Your Tool in the MCP Tool Registry

Open `mcp_tool_registry.py` and add your new tool:

1. Import your tool module at the top:
```python
from . import my_custom_tool
```

2. Create a new tool function with the MCP decorator:
```python
@mcp_server.tool(
    name="myCustomTool",
    description="Description of what your tool does and when it should be used"
)
async def my_custom_tool_function(
    param1: Annotated[str, Field(description="description of parameter 1")],
    param2: Annotated[int, Field(description="description of parameter 2")]
) -> dict:
    """Detailed description of your tool's functionality"""
    try:
        logger.info(f"My custom tool called with: {param1}, {param2}")
        results = my_custom_tool.main(param1, param2)
        return results
    except Exception as e:
        logger.error(f"Error in my custom tool: {str(e)}", exc_info=True)
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
