# Amazon Nova Sonic Call Center Agent w/ Tools

**Overview**

This template provides an AWS cloud-based solution for deploying applications that interact with the Amazon Nova Sonic Model. It serves as a foundation for developing future speech-to-speech tooling use cases. Unlike other implementations that required locally hosted backend and frontend, this cloud architecture leverages:

- **Frontend:** Hosted on Amazon CloudFront and S3
- **Backend:** Deployed on Amazon ECS
- **Connection:** Websocket communication through Network Load Balancer (NLB)
- **Authentication:** Integrated Amazon Cognito authentication

The sample application demonstrates Amazon Nova Sonic model interactions in a customer support context. There are two deployment options: 
- 1. Basic deployment where you get a Agentic AI powered digital concierge for AnyTelco handling customer calls and responding to the customers in real time. 
- 2. Industry specific deployment where you get option to deploy the solution for an industry (airline, telco, etc.) of your choice with industry specific sample data and set of MCP tools. This is a quick and easy way to deploy the solution before you customise it for your specific use cases. 

**Note:** This is a sample application. For production, please modify the application to align with your security standards.

## Table of Contents

1. [Introduction](#introduction)
2. [Architecture](#architecture)
   - [Speech-to-Speech Conversation Flow](#speech-to-speech-conversation-flow)
3. [Getting Started](#getting-started)
   - [Prerequisites](#prerequisites)
   - [Configuration](#configuration)
   - [Deployment](#deployment)
4. [Usage](#usage)
5. [Customization](#customization)
   - [Prompting](#prompting)
   - [Tooling](#tooling)
   - [Local Frontend Development](#local-frontend-development)

## Architecture

![Diagram describing the basic solution architecture](diagrams/basic.png)

### Speech-to-Speech Conversation Flow

1. The user signs onto the frontend hosted on Amazon Cloudfront with a static S3 web page. If the user is unauthenticated, they are re-directed to the Amazon Cognito sign on page where they can sign on with their credentials.
2. The user clicks start session to open the websocket connection to the python backend. The connect payload contains the JWT which is validated against cognito by the python backend before connection is established.
3. Speech data is transmitted bidirectionally through this connection for real-time conversation. The user speaks and audio from the user is sent to the Nova Sonic model through the python backend.
4. Nova Sonic processes the audio. It first outputs a transcription of the user audion. It then does one of two things:
   1. Outputs a response which is streamed back to the user. This response includes the assistant response audio and assistant response text.
   2. Outputs a tool use request which is picked up and implemented by the Python backend. The backend returns the tool result to Nova Sonic which generates a final response which is streamed back to the user. This response includes the assistant response audio and assistant response text.

## Getting started

### Prerequisites

The versions below are tested and validated. Minor version differences would likely be acceptable.

- Python 3.12
- Node.js v20
- Node Package Manager (npm) v10.8
- Docker v27.4 (if your build environment is x86, make sure your docker environment is configured to be able to build Arm64 container images)
- AWS Account (make sure your account is bootstrapped for CDK)
- Amazon Nova Sonic is enabled via the [Bedrock model access console](https://us-east-1.console.aws.amazon.com/bedrock/home?region=us-east-1#/modelaccess)
- Chrome, Safari, or Edge browser environment (Firefox is currently not supported)
- Working microphone and speakers

### Deployment
IMPORTANT: Ensure you are deploying to aws region `us-east-1` since this is the only region that currently supports Amazon Nova Sonic model in Amazon Bedrock.

**Option1: Basic deployment**

Basic deployment will use the tools available inside `backend/tools/` folder and system prompts from the `config/system_prompt.txt` folder to complete the deployment. 
   - **Step 1**: Copy `template.env` from the selecte folder to a new file `.env`. 
   
   For  `KNOWLEDGE_BASE_ID`, provide your Amazon Bedrock Knowledge Base ID. 
   
   For `DYNAMODB_TABLE_NAME`, create a dynamo DB table with phone_number as primary key. You can add additional columns like customerName, plan, monthlyBill, dataUsage, minsUsed, contractEndDate,accountStatus, paymentMethod, fullAddress, etc. as per your requirements. You can manually add some sample data in the table, or you can look at a sample csv file inside industry-specific-demo-data/telco/sample-data/telco_customer_sample_data.csv. Put the name of the dynamodb table inside the .env file. 
   
   If you want to bring your own VPC rather than the solution deploying a new VPC for you, specify your VPC ID in `VPC_ID`.

   - **Step 2**: Run the deployment script to deploy two stacks: Network and S2S. Make sure both stacks get deployed. `./deploy.sh`

**Option2: Industry specific deployment**

This approach allows you to quickly deploy industry-tailored demos with appropriate prompts, tools, and sample data already configured.
   - **Step 1**: Go to the industry-specific-demo-data, you will find deploy-industry-sepecific-demo.py which automates the deployment.
   - **Step 2**: Select the industry of your choice. If your preferred industry is not available in the `industry-specific-demo-data` directory, select "other" for a generic deployment which you can customize by updating prompts and adding new tools. 
   - **Step 3**: copy template.env to .env and update the environment variables. Check the README.md for industry specific setup insutructions.
   - **Step 4**: inside the industry-specific-demo-data folder, run `python deploy-industry-sepecific-demo.py`. You will also be prompted to import sample data for the selected industry. 
   
   **Please note that during deployment all tools inside `backend/tools/` will be reset by the tools for the selected industry. Make sure you take a backup of your existing tools in the backend/tools folder before deploying for a specific industry.**

**ASK:** As you setup demos for different industries (insurance, FSI, travel, etc.), we invite you add them inside industry-specific-demo-data. Kindly remove any PII and anonymise the sample data and system prompt before adding them in the folder and submitting a pull request.

---
After completion of successful deployment, you should see an output like this:

```bash
Outputs:
S2SStack-dev.BackendUrl = https://{cloudfront_distribution}/api
S2SStack-dev.CognitoAppClientId = random_string
S2SStack-dev.CognitoDomain = domain_with_prefix_you_specified_in_cdk_json
S2SStack-dev.CognitoUserPoolId = random_string
S2SStack-dev.FrontendUrl = https://{cloudfront_distribution}
S2SStack-dev.NlbUrl = nlb_endpoint_url
Stack ARN:
arn:aws:cloudformation:us-east-1:123456789101:stack/S2SStack-dev/{stack_id}

✨  Total time: 307.96s
```
### Setup user to access frontend
Create a Cognito user in your console and access the frontend URL in your browser to get started.

To create a Cognito user in CLI, use these commands:

1. **Create a User**
   Use the `admin-create-user` command to create a user in the Cognito User Pool. Replace placeholders with your actual values.

```bash
aws cognito-idp admin-create-user \
  --user-pool-id YOUR_USER_POOL_ID \
  --username USERNAME \
  --user-attributes Name=email,Value=USER_EMAIL \
  --temporary-password TEMPORARY_PASSWORD \
  --region YOUR_AWS_REGION
```

- `YOUR_USER_POOL_ID`: The ID of your Cognito User Pool.
- `USERNAME`: The desired username for the user.
- `USER_EMAIL`: The email address of the user.
- `TEMPORARY_PASSWORD`: A temporary password for the user.
- `YOUR_AWS_REGION`: Your AWS region (e.g., `us-east-1`).

2. **Log in and change password**
   Click on the frontend URL with the username and temporary password you just created. You will be asked to change the password when you first log in.

## Usage

1. Click "Start Session" to begin
2. Speak into your microphone to interact with the application. You are acting as the customer and the solution acts as the call center agent.
3. The chat history will automatically update with the discussion transcript and the assistant audio will play through your speakers.

## Customization

### Prompting

You can change the system prompt from the UI.

![](./diagrams/ui_screenshot.png)

### Tooling

Tooling for Amazon Nova Sonic is implemented using the Model Context Protocol (MCP) in the backend Python application. Amazon Nova Sonic outputs text indicating it wants to use a tool, the MCP server processes the tool call, and the response is returned back to the model for use in generation.

To add a new tool:

1. **Define the tool using MCP decorators** in `backend/tools/mcp_tool_registry.py`.

Tools are defined using the `@mcp_server.tool()` decorator with explicit type annotations. The MCP server automatically generates the tool specifications that get sent to Amazon Nova Sonic. Give your tool a name, description, and specify the input parameters with types. The model uses the description to know when to use the tool and the parameter descriptions to understand the input format.

In our example there are two tools, knowledge base lookup and user profile search. To add your own tool, follow this pattern:

```python
@mcp_server.tool(
    name="lookup",
    description="Runs query against a knowledge base to retrieve information."
)
async def lookup_tool(
    query: Annotated[str, Field(description="the query to search")]
) -> dict:
    """Look up information in the knowledge base"""
    try:
        results = knowledge_base_lookup.main(query)
        return results
    except Exception as e:
        return {"status": "error", "error": str(e)}
```

2. **Implement the tool logic** in a separate Python file. You can create a new Python file to implement the tool functionality, like how `backend/tools/retrieve_user_profile.py` implements the user lookup tool and `backend/tools/knowledge_base_lookup.py` implements the knowledge base search tool. These examples show how you can interact with AWS resources via these tools to retrieve real information for the model.

3. **Import your tool implementation** in `backend/tools/mcp_tool_registry.py`. The tool function should import and call your implementation module:

```python
from . import knowledge_base_lookup

# Then call it in your tool function:
results = knowledge_base_lookup.main(query)
```

The MCP server handles converting your tool definitions into the proper format for Amazon Nova Sonic and automatically processes tool calls during conversations.

### Local development

Assume credentials for an AWS account with Amazon Nova Sonic enabled in Amazon Bedrock and export: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` and `AWS_SESSION_TOKEN`.

Make sure your `.env` file is in the backend folder.

Run `npm run dev` in the same shell session as above to start frontend and backend containers.
Both use a file watching mechanism to be notified of local code changes and reload automatically.
Re-run the `npm` command only if changes are made to the Dockerfile, Python libraries or NPM dependencies that require installation, as these are not picked up by the file watcher.

The frontend is accessible at http://localhost:5173/ and the backend at http://localhost:8080/, with authentication disabled for both.

## FAQ/trouble shooting

1. I get `ERROR: process "/bin/sh -c chmod +x entrypoint.sh" did not complete successfully: exit code: 255` during build time.

- Your docker environment in x86 may not be configured properly. You may need to change the FROM statement in the backend [Dockerfile](./backend/Dockerfile).

```
ARG TARGETARCH=arm64
FROM --platform=$TARGETARCH python:3.12
```

2. `npm run dev` hangs and the backend container does not exit. I get the error `docker: Error response from daemon: driver failed programming external connectivity on endpoint s2s-backend-dev` when I try to run the command again.

Run `docker rm -f s2s-backend-dev` to remove the running container image and run `npm run dev` again.

## Contributors

- [Reilly Manton](https://www.linkedin.com/in/reilly-manton/)  
- [Shuto Araki](https://www.linkedin.com/in/shuto-araki/)  
- [Andrew Young](https://www.linkedin.com/in/andrewjunyoung/)  
- [Ratan Kumar](https://www.linkedin.com/in/kumar-ratan/)