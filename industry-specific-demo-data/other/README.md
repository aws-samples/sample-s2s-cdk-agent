# Generic Implementation Setup Guide

This guide will help you set up and deploy the Amazon Nova Sonic Call Center Agent demo with a generic implementation that you can customize for your specific industry.

## Overview

The generic implementation includes:
- Knowledge base integration for retrieving information
- Customer profile lookup tool with customizable data structure
- Framework for adding your own industry-specific tools

## Setup Instructions

### 1. Environment Configuration

1. Create a copy of `template.env` as `.env`:
   ```bash
   cp template.env .env
   ```

2. Edit the `.env` file with your specific configuration:
   - `ENV`: Your deployment environment (e.g., "dev", "prod")
   - `VPC_ID`: (Optional) Your VPC ID if you want to use an existing VPC
   - `KNOWLEDGE_BASE_ID`: Your Amazon Bedrock Knowledge Base ID containing your domain-specific information
   - `DYNAMODB_TABLE_NAME`: Your DynamoDB table name for customer data

3. `.env` will be automatically copied to backend folder by the deployment script.


### 2. Knowledge Base Setup

The knowledge base tool allows the agent to retrieve information from your Amazon Bedrock Knowledge Base:

1. Create a Knowledge Base in Amazon Bedrock:
   - Navigate to the Amazon Bedrock console
   - Select "Knowledge bases" from the left navigation
   - Click "Create knowledge base"
   - Follow the wizard to create a knowledge base with your domain-specific content
   - Choose appropriate embedding and retrieval models
   - Add your documents containing FAQs, policies, or other information

2. Once created, copy the Knowledge Base ID and add it to your `.env` file:
   ```
   KNOWLEDGE_BASE_ID=your-knowledge-base-id
   ```
### 3. Deployment

Return to the project root directory and run the deployment script:
```bash
cd ../
./deploy-industry-sepecific-demo.py
```

When prompted, select "other" as your industry-specific demo.

## Testing the Demo

After deployment:
1. Access the frontend URL provided in the deployment output
2. Sign in with your Cognito credentials
3. Start a conversation with the agent
4. Try queries like:
   - "Can you look up my account information?"
   - "What's my current plan?"
   - "I have a question about [topic in your knowledge base]"

## Customization

### Adding Custom Tools

You can extend the generic implementation by adding your own industry-specific tools:

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

3. Register your tool in the MCP Tool Registry by editing `mcp_tool_registry.py`:

```python
from . import my_custom_tool

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

### Tool Design Best Practices

When creating tools for Amazon Nova Sonic:

- **Clear Descriptions**: Write clear descriptions for your tool and parameters so the model knows when and how to use it
- **Proper Error Handling**: Always include try/except blocks to handle errors gracefully
- **Logging**: Include logging statements to help with debugging
- **Return Format**: Return results as a dictionary with a consistent structure
- **Parameter Types**: Use appropriate type annotations with descriptive Field parameters
- **Tool Naming**: Use camelCase for tool names and descriptive names that indicate functionality

### Creating Your Own Industry-Specific Implementation

If you want to create a new industry-specific implementation:

1. Create a new directory under `industry-specific-demo-data` with your industry name
2. Copy the structure from this generic implementation
3. Customize the README.md with industry-specific instructions
4. Add any industry-specific tools to the `tools` directory
5. Create sample data relevant to your industry
6. Update the deployment script to include your new industry option
7. add .env file with list of environment variables (e.g. KNOWLEDGE_BASE_ID)