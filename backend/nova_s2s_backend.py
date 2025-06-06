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

#nova_s2s_backend.py
import json
import logging
import os
import uuid
import warnings
import asyncio
import websockets

# Import the Cognito validation module
import cognito

from aws_sdk_bedrock_runtime.client import (
    BedrockRuntimeClient,  # Use BedrockRuntimeClient instead of BedrockRuntime
    InvokeModelWithBidirectionalStreamOperationInput,
)
from aws_sdk_bedrock_runtime.models import (
    InvokeModelWithBidirectionalStreamInputChunk,
    BidirectionalInputPayloadPart,
)
from aws_sdk_bedrock_runtime.config import (
    Config,
    HTTPAuthSchemeResolver,
    SigV4AuthScheme,
)
from smithy_aws_core.credentials_resolvers.environment import (
    EnvironmentCredentialsResolver,
)

from mcp_server import get_bedrock_tool_specs, handle_bedrock_tool_call, start_mcp_server, mcp_server
import tools.mcp_tool_registry

# Configure logging
LOGLEVEL = os.environ.get("LOGLEVEL", "INFO").upper()
logging.basicConfig(level=LOGLEVEL, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)
RUNNING_IN_DEV_MODE = os.environ.get("DEV_MODE", "False").lower() == "true"

# Suppress warnings
warnings.filterwarnings("ignore")
# Suppress websockets server non-critical logs that are triggered by NLB health checks (empty TCP packets)
logging.getLogger("websockets.server").setLevel(logging.CRITICAL)


class BedrockStreamManager:
    """Manages bidirectional streaming with AWS Bedrock using asyncio"""

    def __init__(self, model_id="amazon.nova-sonic-v1:0", region="us-east-1"):
        """Initialize the stream manager."""
        self.model_id = model_id
        self.region = region
        self.last_credential_refresh = 0

        # Audio and output queues
        self.audio_input_queue = asyncio.Queue()
        self.output_queue = asyncio.Queue()

        self.response_task = None
        self.stream_response = None
        self.is_active = False
        self.bedrock_client = None

        # Session information
        self.prompt_name = None  # Will be set from frontend
        self.content_name = None  # Will be set from frontend
        self.audio_content_name = None  # Will be set from frontend
        self.toolUseContent = ""
        self.toolUseId = ""
        self.toolName = ""

    def _initialize_client(self):
        """Initialize the Bedrock client."""
        config = Config(
            endpoint_uri=f"https://bedrock-runtime.{self.region}.amazonaws.com",
            region=self.region,
            aws_credentials_identity_resolver=EnvironmentCredentialsResolver(),
            http_auth_scheme_resolver=HTTPAuthSchemeResolver(),
            http_auth_schemes={"aws.auth#sigv4": SigV4AuthScheme()},
        )
        self.bedrock_client = BedrockRuntimeClient(config=config)

    async def initialize_stream(self):
        """Initialize the bidirectional stream with Bedrock."""
        if not self.bedrock_client:
            self._initialize_client()

        try:
            self.stream_response = (
                await self.bedrock_client.invoke_model_with_bidirectional_stream(
                    InvokeModelWithBidirectionalStreamOperationInput(
                        model_id=self.model_id
                    )
                )
            )
            self.is_active = True

            # Start listening for responses
            self.response_task = asyncio.create_task(self._process_responses())

            # Start processing audio input
            asyncio.create_task(self._process_audio_input())

            # Wait a bit to ensure everything is set up
            await asyncio.sleep(0.1)

            logger.info("Stream initialized successfully")
            return self
        except Exception as e:
            self.is_active = False
            logger.error(f"Failed to initialize stream: {str(e)}")
            raise
    
    async def handle_prompt_start_with_tools(self, original_session_data):
        """Handle session start by adding tool configuration"""
        
        # Get the original session start data
        prompt_config = original_session_data["event"]["promptStart"]
        
        # Add tool configuration using MCP tools
        prompt_config["toolConfiguration"] = {
            "tools": await get_bedrock_tool_specs()
        }
        
        # Create the enhanced session start event
        enhanced_prompt_start_event = {
            "event": {
                "promptStart": prompt_config
            }
        }
        
        logger.info("Starting session")
        
        # Send the enhanced event to Bedrock
        await self.send_raw_event(enhanced_prompt_start_event)

    async def send_raw_event(self, event_data):
        """Send a raw event to the Bedrock stream."""
        if not self.stream_response or not self.is_active:
            logger.info("Stream not initialized or closed")
            return

        # Convert to JSON string if it's a dict
        if isinstance(event_data, dict):
            event_json = json.dumps(event_data)
        else:
            event_json = event_data

        # Create the event chunk
        event = InvokeModelWithBidirectionalStreamInputChunk(
            value=BidirectionalInputPayloadPart(bytes_=event_json.encode("utf-8"))
        )

        try:
            await self.stream_response.input_stream.send(event)

            # Define event_type outside the conditional blocks
            if isinstance(event_data, dict):
                event_type = list(event_data.get("event", {}).keys())
            else:
                event_type = list(json.loads(event_json).get("event", {}).keys())

            if "promptStart" in event_type or 'contentStart' in event_type:
                logger.info(event_data)

            if len(event_json) > 200:
                if (
                    "audioInput" not in event_type
                ):  # constant stream of audio inputs so we don't want to log them all
                    logger.info(f"Sent event type: {event_type}")
            else:
                if (
                    "audioInput" not in event_type
                ):  # constant stream of audio inputs so we don't want to log them all
                    logger.info(f"Sent event type: {event_type}")
        except Exception as e:
            logger.info(f"Error sending event: {str(e)}", exc_info=True)

    async def _process_audio_input(self):
        """Process audio input from the queue and send to Bedrock."""
        while self.is_active:
            try:
                # Get audio data from the queue
                data = await self.audio_input_queue.get()

                # Extract data from the queue item
                prompt_name = data.get("prompt_name")
                content_name = data.get("content_name")
                audio_bytes = data.get("audio_bytes")

                if not audio_bytes or not prompt_name or not content_name:
                    logger.info("Missing required audio data properties")
                    continue

                # Create the audio input event
                audio_event = {
                    "event": {
                        "audioInput": {
                            "promptName": prompt_name,
                            "contentName": content_name,
                            "content": (
                                audio_bytes.decode("utf-8")
                                if isinstance(audio_bytes, bytes)
                                else audio_bytes
                            ),
                            "role": "USER",
                        }
                    }
                }

                # Send the event
                await self.send_raw_event(audio_event)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.info(f"Error processing audio: {e}", exc_info=True)

    def add_audio_chunk(self, prompt_name, content_name, audio_data):
        """Add an audio chunk to the queue."""
        # The audio_data is already a base64 string from the frontend
        self.audio_input_queue.put_nowait(
            {
                "prompt_name": prompt_name,
                "content_name": content_name,
                "audio_bytes": audio_data,
            }
        )

    async def _process_responses(self):
        """Process incoming responses from Bedrock."""
        try:
            while self.is_active:
                try:
                    output = await self.stream_response.await_output()
                    result = await output[1].receive()
                    if result.value and result.value.bytes_:
                        try:
                            response_data = result.value.bytes_.decode("utf-8")
                            json_data = json.loads(response_data)

                            # Handle different response types
                            if "event" in json_data:
                                event_data = json_data["event"]
                                if "contentStart" in event_data:
                                    logging.debug("Content start detected")
                                    content_start = event_data["contentStart"]
                                    # Check for speculative content
                                    if "additionalModelFields" in content_start:
                                        try:
                                            additional_fields = json.loads(
                                                content_start["additionalModelFields"]
                                            )
                                            if (
                                                additional_fields.get("generationStage")
                                                == "SPECULATIVE"
                                            ):
                                                logging.debug(
                                                    "Speculative content detected"
                                                )
                                        except json.JSONDecodeError:
                                            logging.error(
                                                "Error parsing additionalModelFields",
                                                exc_info=True,
                                            )
                                elif "textOutput" in event_data:
                                    text_content = event_data["textOutput"]["content"]
                                    role = event_data["textOutput"]["role"]
                                    if role == "ASSISTANT":
                                        logger.info(f"Assistant Message Redacted")
                                        # here you could log the message for testing
                                    elif role == "USER":
                                        logger.info(f"User Message Redacted")
                                        # here you could log the message for testing
                                # Handle tool use detection
                                elif "toolUse" in event_data:
                                    self.toolUseContent = event_data["toolUse"]
                                    self.toolName = event_data["toolUse"]["toolName"]
                                    self.toolUseId = event_data["toolUse"]["toolUseId"]
                                    logger.info(
                                        f"Tool use detected: {self.toolName}, ID: {self.toolUseId}"
                                    )

                                # Process tool use when content ends
                                elif (
                                    "contentEnd" in event_data
                                    and event_data.get("contentEnd", {}).get("type")
                                    == "TOOL"
                                ):
                                    logger.info(
                                        "Processing tool use and sending result"
                                    )

                                    # Process the tool use using the registry
                                    toolResult = await self.processToolUse(
                                        self.toolName, self.toolUseContent
                                    )

                                    # Create a unique content name for this tool result
                                    toolContent = str(uuid.uuid4())

                                    logger.info(f"Tool Use Id {toolContent}")

                                    # Send tool start event
                                    tool_start_event = {
                                        "event": {
                                            "contentStart": {
                                                "interactive": True,
                                                "promptName": self.prompt_name,
                                                "contentName": toolContent,
                                                "type": "TOOL",
                                                "role": "TOOL",
                                                "toolResultInputConfiguration": {
                                                    "toolUseId": self.toolUseId,
                                                    "type": "TEXT",
                                                    "textInputConfiguration": {
                                                        "mediaType": "text/plain"
                                                    },
                                                },
                                            }
                                        }
                                    }
                                    await self.send_raw_event(
                                        json.dumps(tool_start_event)
                                    )

                                    # Send tool result event
                                    if isinstance(toolResult, dict):
                                        content_json_string = json.dumps(toolResult)
                                    else:
                                        content_json_string = str(toolResult)

                                    # check if tool use resulted in an error that needs to be reported to Sonic
                                    if isinstance(toolResult, dict):
                                        content_json_string = json.dumps(toolResult)
                                        # Simple error check - only if it's a dict and has a status field
                                        status = "error" if toolResult.get("status") == "error" else "success"
                                    else:
                                        content_json_string = str(toolResult)
                                        status = "success"
                                    # logger.info(f"Tool result {toolResult} and value of status is {status}")

                                    tool_result_event = {
                                        "event": {
                                            "toolResult": {
                                                "promptName": self.prompt_name,
                                                "contentName": toolContent,
                                                "content": content_json_string,
                                                "status": status,
                                            }
                                        }
                                    }
                                    await self.send_raw_event(
                                        json.dumps(tool_result_event)
                                    )

                                    # Send tool content end event
                                    tool_content_end_event = {
                                        "event": {
                                            "contentEnd": {
                                                "promptName": self.prompt_name,
                                                "contentName": toolContent,
                                            }
                                        }
                                    }
                                    await self.send_raw_event(
                                        json.dumps(tool_content_end_event)
                                    )

                            # Put the response in the output queue for forwarding to the frontend
                            await self.output_queue.put(json_data)
                        except json.JSONDecodeError:
                            await self.output_queue.put({"raw_data": response_data})
                except StopAsyncIteration:
                    # Stream has ended
                    break
                except Exception as e:
                    # Handle ValidationException properly
                    if "ValidationException" in str(e):
                        error_message = str(e)
                        logger.error(f"Validation error: {error_message}")
                    else:
                        logger.error(f"Error receiving response: {e}")
                    break

        except Exception as e:
            logger.error(f"Response processing error: {e}")
        finally:
            self.is_active = False

    async def processToolUse(self, toolName, toolUseContent):
        """Process tool usage using MCP"""
        tool_name = toolName.lower()
        
        logger.info(f"Processing tool use: {tool_name}")
        
        # Process the tool
        result = await handle_bedrock_tool_call(tool_name, toolUseContent)
        
        return result


async def websocket_handler(websocket, url, headers=None):
    """Handle WebSocket connections from the frontend with authentication."""
    # Validate the WebSocket connection using Cognito
    is_valid, claims = cognito.validate_websocket_request(url, headers) if not RUNNING_IN_DEV_MODE else True, {}

    if not is_valid:
        # Log the failure with more detail
        logger.warning(f"Authentication failed for URL: {url}")

        # Send an authentication error and close the connection
        try:
            await websocket.send(
                json.dumps({"error": "Authentication failed", "status": "unauthorized"})
            )
        except:
            pass
        return

    # Log authenticated user
    user_id = claims.get("sub") if claims else "unknown"
    logger.info(f"Authenticated WebSocket connection for user: {user_id}")

    # Send authentication success message
    try:
        await websocket.send(
            json.dumps(
                {
                    "event": {
                        "connectionStatus": {
                            "status": "authenticated",
                            "message": "Connection authenticated successfully",
                        }
                    }
                }
            )
        )
    except:
        logger.error("Failed to send authentication success message")

    # Create a new stream manager for this connection
    stream_manager = BedrockStreamManager(
        model_id="amazon.nova-sonic-v1:0", region="us-east-1"
    )

    # Initialize the Bedrock stream
    await stream_manager.initialize_stream()

    # Start a task to forward responses from Bedrock to the WebSocket
    forward_task = asyncio.create_task(forward_responses(websocket, stream_manager))

    try:
        async for message in websocket:
            try:
                data = json.loads(message)

                if "event" in data:
                    event_type = list(data["event"].keys())[0]

                    # Store prompt name and content names if provided
                    if event_type == "promptStart":
                        stream_manager.prompt_name = data["event"]["promptStart"][
                            "promptName"
                        ]                 
                        await stream_manager.handle_prompt_start_with_tools(data) # add the tool config
                        continue 
                    elif (
                        event_type == "contentStart"
                        and data["event"]["contentStart"].get("type") == "AUDIO"
                    ):
                        stream_manager.audio_content_name = data["event"][
                            "contentStart"
                        ]["contentName"]

                    # Handle audio input separately
                    if event_type == "audioInput":
                        # Extract audio data
                        prompt_name = data["event"]["audioInput"]["promptName"]
                        content_name = data["event"]["audioInput"]["contentName"]
                        audio_base64 = data["event"]["audioInput"]["content"]

                        # Add to the audio queue
                        stream_manager.add_audio_chunk(
                            prompt_name, content_name, audio_base64
                        )
                    else:
                        # Send other events directly to Bedrock
                        await stream_manager.send_raw_event(data)
            except json.JSONDecodeError:
                logger.error("Invalid JSON received from WebSocket")
            except Exception as e:
                logger.error(f"Error processing WebSocket message: {e}", exc_info=True)

    except websockets.exceptions.ConnectionClosed:
        logger.info("WebSocket connection closed")
    finally:
        # Clean up the asyncio task
        forward_task.cancel()


async def forward_responses(websocket, stream_manager):
    """Forward responses from Bedrock to the WebSocket."""
    try:
        while True:
            # Get next response from the output queue
            response = await stream_manager.output_queue.get()

            # Send to WebSocket
            try:
                await websocket.send(json.dumps(response))
            except websockets.exceptions.ConnectionClosed:
                break
    except asyncio.CancelledError:
        # Task was cancelled
        pass
    except Exception as e:
        logger.error(f"Error forwarding responses: {e}")


async def authenticated_handler(websocket, path=None):
    """Simplified handler that handles both path format and attributes"""
    # Debug info
    logger.info(f"New WebSocket connection with path: {path}")

    # Try to get path from various attributes
    if hasattr(websocket, "request") and hasattr(websocket.request, "path"):
        path = websocket.request.path
        logger.info(f"Using path from websocket.request.path: {path}")

    # Get headers
    headers = None
    if hasattr(websocket, "request_headers"):
        headers = websocket.request_headers
    elif hasattr(websocket, "request") and hasattr(websocket.request, "headers"):
        headers = websocket.request.headers

    # Validate token directly from path
    # First try to extract and validate the token directly
    token = cognito.extract_token_from_url(path) if not RUNNING_IN_DEV_MODE else True

    if token:
        is_valid, _ = cognito.validate_token(token) if not RUNNING_IN_DEV_MODE else True, None

        if not is_valid:
            # Failed authentication
            logger.warning(f"Authentication failed for token from path: {path}")

            try:
                await websocket.send(
                    json.dumps(
                        {"error": "Authentication failed", "status": "unauthorized"}
                    )
                )
            except Exception as e:
                logger.error(f"Error sending auth failure message: {e}")
            return

        # Token is valid, proceed with websocket handler
        logger.info("Authenticated user")
        await websocket_handler(websocket, path, headers)
    else:
        # No token found
        logger.warning(f"No token found in path: {path}")

        try:
            await websocket.send(
                json.dumps(
                    {
                        "error": "Authentication failed - no token provided",
                        "status": "unauthorized",
                    }
                )
            )
        except Exception as e:
            logger.error(f"Error sending auth failure message: {e}")


async def main():
    """Main function to run the WebSocket server and MCP server."""
    mcp_port = int(os.environ.get("MCP_PORT", 8000)) # communicate with MCP on port 80, localhost
    
    # Start MCP server and wait for it to be ready
    logger.info(f"Starting MCP server on localhost:{mcp_port}")
    mcp_task = asyncio.create_task(start_mcp_server(host="127.0.0.1", port=mcp_port))
    
    # Wait for MCP server to be ready
    await asyncio.sleep(2)
    
    # Verify MCP server is working
    try:
        tools = await mcp_server.get_tools()
        tools_list = list(tools.values())  # Convert dict to list for len()
        logger.info(f"MCP server ready with {len(tools_list)} tools: {list(tools.keys())}")
    except Exception as e:
        logger.error(f"MCP server failed to start: {e}")
        mcp_task.cancel()
        raise
    
    # Now start WebSocket server
    port = int(os.environ.get("PORT", 80))
    host = "0.0.0.0"
    
    logger.info(f"Starting WebSocket server on {host}:{port}")
    
    try:
        async with websockets.serve(authenticated_handler, host, port):
            logger.info(f"All services running - WebSocket: {port}, MCP: {mcp_port}")
            await asyncio.Future()  
    except Exception as e:
        logger.error(f"Server startup error: {e}", exc_info=True)
        raise
    finally:
        logger.info("Shutting down...")
        mcp_task.cancel()
        try:
            await mcp_task
        except asyncio.CancelledError:
            pass

if __name__ == "__main__":
    # Run the main function
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
