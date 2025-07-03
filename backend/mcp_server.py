#
# Copyright 2025 Amazon.com, Inc. and its affiliates. All Rights Reserved.
#
# Licensed under the Amazon Software License (the "License").
# You may not use this file except in compliance with the License.
# A copy of the License is located at
#
#   http://aws.amazon.com/asl/
#
# or in the "license" file accompanying this file. This file is distributed
# on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
# express or implied. See the License for the specific language governing
# permissions and limitations under the License.
#

import asyncio
import json
import logging
import os
from fastmcp import FastMCP

# Configure logging
logger = logging.getLogger(__name__)

# Create the MCP server
mcp_server = FastMCP(name="AIToolsServer")

# Function to extract MCP tool specs in Bedrock format
async def get_bedrock_tool_specs():
    """Convert MCP tool definitions to Bedrock tool specifications"""
    bedrock_specs = []
    
    tools_dict = await mcp_server.get_tools()
    
    for tool_name, tool in tools_dict.items():
        bedrock_tool = {
            "toolSpec": {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": {
                    "json": json.dumps(tool.parameters)
                }
            }
        }
        bedrock_specs.append(bedrock_tool)
    
    return bedrock_specs

# Function to handle Bedrock tool calls through MCP
async def handle_bedrock_tool_call(tool_name, tool_content):
    """Process a Bedrock tool call using the MCP server"""
    try:
        # Extract parameters from Bedrock format
        if isinstance(tool_content, dict) and "content" in tool_content:
            params = json.loads(tool_content.get("content", "{}"))
        else:
            params = {}
        
        logger.info(f"Executing tool {tool_name}")       
        
        tools_dict = await mcp_server.get_tools()
        tool = tools_dict.get(tool_name.lower()) or next((tool for name, tool in tools_dict.items() if name.lower() == tool_name.lower()), None)
        
        if not tool:
            logger.warning(f"Tool not found: {tool_name}")
            return {"status": "error", "error": f"Tool '{tool_name}' not found"}
        
        # Execute the tool
        result = await tool.run(params)

        # Handle different result types
        if hasattr(result, 'content') and result.content:
            content = result.content[0] if isinstance(result.content, list) else result.content
            if hasattr(content, 'text'):
                actual_text = content.text
                try:
                    return json.loads(actual_text)
                except:
                    return actual_text
        elif hasattr(result, 'structured_content') and result.structured_content:
            return result.structured_content
        elif isinstance(result, (dict, list)):
            return result
        
        return str(result)
        
    except Exception as e:
        logger.error(f"Error handling tool call: {str(e)}", exc_info=True)
        return {"status": "error", "error": f"Tool execution failed: {str(e)}"}

# Function to start the MCP server
async def start_mcp_server(host="127.0.0.1", port=8000):
    """Start the MCP server"""
    logger.info(f"Starting MCP server on {host}:{port}")
    def run_server():
        mcp_server.run(transport="sse", host=host, port=port)
    
    import threading
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    await asyncio.sleep(0.05)