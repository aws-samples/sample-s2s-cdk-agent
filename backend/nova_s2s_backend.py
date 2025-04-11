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
import websockets
import json
import warnings
import uuid
import os
import logging
import time


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

import knowledge_base_lookup
import retrieve_user_profile

# Configure logging
LOGLEVEL = os.environ.get("LOGLEVEL", "INFO").upper()
logging.basicConfig(level=LOGLEVEL, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

# Suppress warnings
warnings.filterwarnings("ignore")


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

        self.last_credential_refresh = time.time()

        """Initialize the Bedrock client."""
        config = Config(
            endpoint_uri=f"https://bedrock-runtime.{self.region}.amazonaws.com",
            region=self.region,
            aws_credentials_identity_resolver=EnvironmentCredentialsResolver(),
            http_auth_scheme_resolver=HTTPAuthSchemeResolver(),
            http_auth_schemes={"aws.auth#sigv4": SigV4AuthScheme()},
        )
        self.bedrock_client = BedrockRuntimeClient(config=config)

    def _ensure_fresh_client(self):
        """Check if credentials need refresh and reinitialize client if needed."""
        # Refresh client every 25 minutes to ensure fresh credentials
        if time.time() - self.last_credential_refresh > 1500:  # 25 minutes in seconds
            logger.info("Refreshing Bedrock client with new credentials")
            self._initialize_client()

    async def initialize_stream(self):

        self._ensure_fresh_client()

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

                                    # Process the tool use
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

                                    tool_result_event = {
                                        "event": {
                                            "toolResult": {
                                                "promptName": self.prompt_name,
                                                "contentName": toolContent,
                                                "content": content_json_string,
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
        """Return the tool result"""
        tool = toolName.lower()
        results = {}

        if tool == "lookup":
            # Extract query from toolUseContent
            if isinstance(toolUseContent, dict) and "content" in toolUseContent:
                # Parse the JSON string in the content field
                query_json = json.loads(toolUseContent.get("content"))
                query = query_json.get("query", "")
                logger.info(f"Extracted KB lookup query")

                # Call the knowledge base lookup
                results = knowledge_base_lookup.main(query)

        elif tool == "userprofilesearch":
            if isinstance(toolUseContent, dict) and "content" in toolUseContent:
                # Parse the JSON string in the content field
                phone_number_json = json.loads(toolUseContent.get("content"))
                phone_number = phone_number_json.get("phone_number", "")
                logger.info(f"Extracted phone number.")

                results = retrieve_user_profile.main(phone_number)

        return results


async def websocket_handler(websocket, url, headers=None):
    """Handle WebSocket connections from the frontend with authentication."""
    # Validate the WebSocket connection using Cognito
    is_valid, claims = cognito.validate_websocket_request(url, headers)

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
    token = cognito.extract_token_from_url(path)

    if token:
        is_valid, claims = cognito.validate_token(token)

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
    """Main function to run the WebSocket server."""
    # Get port from environment variable or use default
    port = int(os.environ.get("PORT", 80))

    # Use 0.0.0.0 to listen on all interfaces (required for containers)
    host = "0.0.0.0"

    # Start WebSocket server with the simplified handler
    # The handler now works with legacy and newer websockets versions
    logger.info(f"Starting WebSocket server on {host}:{port}")

    try:
        async with websockets.serve(authenticated_handler, host, port):
            logger.info(f"WebSocket server started {host}:{port}")

            # Keep the server running forever
            await asyncio.Future()
    except Exception as e:
        logger.error(f"Server startup error: {e}", exc_info=True)


if __name__ == "__main__":
    # Run the main function
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
