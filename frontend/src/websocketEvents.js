/**
 * Copyright 2025 Amazon.com, Inc. and its affiliates. All Rights Reserved.
 *
 * Licensed under the Amazon Software License (the "License").
 * You may not use this file except in compliance with the License.
 * A copy of the License is located at
 *
 *   http://aws.amazon.com/asl/
 *
 * or in the "license" file accompanying this file. This file is distributed
 * on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
 * express or implied. See the License for the specific language governing
 * permissions and limitations under the License.
 */

import AudioPlayer from "./lib/play/AudioPlayer";
import ChatHistoryManager from "./lib/util/ChatHistoryManager.js";
import { getCognitoAuth } from "./cognito.js";

const audioPlayer = new AudioPlayer();

export class WebSocketEventManager {
  constructor(fallbackWsUrl) {
    this.cognitoAuth = getCognitoAuth();

    this.wsUrl = this.cognitoAuth.getWebSocketUrl();

    this.promptName = null;
    this.audioContentName = null;
    this.audioContext = new (window.AudioContext ||
      window.webkitAudioContext)();
    this.currentAudioConfig = null;
    this.isProcessing = false;
    this.seenChunks = new Set();
    this.customSystemPrompt = null;

    // Message handling properties
    this.messageBuffer = {};

    this.chat = { history: [] };
    this.chatRef = { current: this.chat };

    this.chatHistoryManager = ChatHistoryManager.getInstance(
      this.chatRef,
      (newChat) => {
        this.chat = { ...newChat };
        this.chatRef.current = this.chat;
        // Call the update transcript callback if defined
        if (this.onUpdateTranscript) {
          this.onUpdateTranscript(this.chat.history);
        }
      }
    );

    this.connect();
  }

  // Set custom system prompt
  setSystemPrompt(prompt) {
    if (prompt && prompt.trim()) {
      this.customSystemPrompt = prompt.trim();
      console.log("Custom system prompt set");
    }
  }

  // Callback handlers that can be set from main.js
  onUpdateTranscript = null;
  onUpdateStatus = null;
  onAudioReceived = null;

  connect() {
    if (this.socket) {
      this.socket.close();
    }
    this.socket = new WebSocket(this.wsUrl);
    this.setupSocketListeners();
  }

  setupSocketListeners() {
    this.socket.onopen = () => {
      console.log("WebSocket Connected");
      this.updateStatus("Connected", "connected");
      this.isProcessing = true;
      this.startSession();
      audioPlayer.start();
    };

    this.socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this.handleMessage(data);
      } catch (e) {
        console.error("Error parsing message:", e, "Raw data:", event.data);
      }
    };

    this.socket.onerror = (error) => {
      console.error("WebSocket Error:", error);
      this.updateStatus("Connection error", "error");
      this.isProcessing = false;
    };

    this.socket.onclose = (event) => {
      console.log("WebSocket Disconnected", event);
      this.updateStatus("Disconnected", "disconnected");
      this.isProcessing = false;
      audioPlayer.stop();
      if (this.isProcessing) {
        console.log("Attempting to reconnect...");
        setTimeout(() => this.connect(), 1000);
      }
    };
  }

  async sendEvent(event) {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      console.error(
        "WebSocket is not open. Current state:",
        this.socket?.readyState
      );
      return;
    }

    try {
      this.socket.send(JSON.stringify(event));
    } catch (error) {
      console.error("Error sending event:", error);
      this.updateStatus("Error sending message", "error");
    }
  }

  handleMessage(data) {
    if (!data.event) {
      console.error("Received message without event:", data);
      return;
    }

    const event = data.event;
    console.log("Event received:", Object.keys(event)[0]);

    try {
      // Handle session events
      if (event.sessionStart) {
        console.log("Session start received");
      }
      // Handle prompt events
      else if (event.promptStart) {
        console.log("Prompt start received");
        this.promptName = event.promptStart.promptName;
      }
      // Handle content start
      else if (event.contentStart) {
        console.log("Content start received:", event.contentStart.type);
        if (event.contentStart.type === "AUDIO") {
          this.currentAudioConfig = event.contentStart.audioOutputConfiguration;
          this.audioBuffer = [];
        } else if (event.contentStart.type === "TEXT") {
          // Reset message buffer for new text content
          this.messageBuffer = {};
        }
      }
      // Handle text output
      else if (event.textOutput) {
        console.log("Text output received");
        const role = event.textOutput.role;
        let content = event.textOutput.content;

        // Process speculative content if needed
        if (role === "ASSISTANT" && content.startsWith("Speculative: ")) {
          content = content.slice(13);
        }

        // Skip duplicate chunks
        if (this.seenChunks.has(content)) {
          console.log("Skipping duplicate chunk");
          return;
        }
        this.seenChunks.add(content);

        // Buffer text by role
        if (!this.messageBuffer[role]) {
          this.messageBuffer[role] = content;
        } else {
          // Append to existing content
          this.messageBuffer[role] += content;
        }
      }
      // Handle audio output
      else if (event.audioOutput) {
        console.log("Audio output received");
        if (this.currentAudioConfig) {
          const audioData = this.base64ToFloat32Array(
            event.audioOutput.content
          );
          audioPlayer.playAudio(audioData);

          if (this.onAudioReceived) {
            this.onAudioReceived(audioData);
          }
        }
      }
      // Handle content end
      else if (event.contentEnd) {
        console.log("Content end received:", event.contentEnd.type);
        const contentType = event.contentEnd.type;

        if (event.contentEnd.stopReason === "INTERRUPTED") {
          console.log("Content was interrupted by user");
          // Use the existing bargeIn method
          audioPlayer.bargeIn();

          // You might want to update the UI to show the interruption
          this.updateStatus("User interrupted", "interrupted");
        }

        if (contentType === "TEXT") {
          // Process buffered text messages
          for (const [role, message] of Object.entries(this.messageBuffer)) {
            if (message && message.trim()) {
              this.chatHistoryManager.addTextMessage({
                role: role,
                message: message,
              });
            }
          }
          this.messageBuffer = {};
        }
      }
      // Handle tool use events
      else if (event.toolUse) {
        console.log("Tool use event received:", event.toolUse.toolName);
      }
      // Handle prompt end
      else if (event.promptEnd) {
        console.log("Prompt end received");
      }
      // Handle session end
      else if (event.sessionEnd) {
        console.log("Session end received");
      } else {
        console.warn("Unknown event type received:", Object.keys(event)[0]);
      }
    } catch (error) {
      console.error("Error processing message:", error);
      console.error("Event data:", event);
    }
  }

  updateStatus(message, className) {
    // Call the update status callback if defined
    if (this.onUpdateStatus) {
      this.onUpdateStatus(message, className);
    } else {
      const statusDiv = document.getElementById("status");
      if (statusDiv) {
        statusDiv.textContent = message;
        statusDiv.className = `status ${className}`;
      }
    }
  }

  base64ToFloat32Array(base64String) {
    const binaryString = window.atob(base64String);
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }

    const int16Array = new Int16Array(bytes.buffer);
    const float32Array = new Float32Array(int16Array.length);
    for (let i = 0; i < int16Array.length; i++) {
      float32Array[i] = int16Array[i] / 32768.0;
    }

    return float32Array;
  }

  startSession() {
    console.log("Starting session...");
    const sessionStartEvent = {
      event: {
        sessionStart: {
          inferenceConfiguration: {
            maxTokens: 1024,
            topP: 0.95,
            temperature: 0.7,
          },
        },
      },
    };
    this.sendEvent(sessionStartEvent);
    this.startPrompt();
  }

  startPrompt() {
    this.promptName = crypto.randomUUID();
    const promptStartEvent = {
      event: {
        promptStart: {
          promptName: this.promptName,
          textOutputConfiguration: {
            mediaType: "text/plain",
          },
          audioOutputConfiguration: {
            mediaType: "audio/lpcm",
            sampleRateHertz: 24000,
            sampleSizeBits: 16,
            channelCount: 1,
            voiceId: "tiffany", // Match the voice ID in your backend
            encoding: "base64",
            audioType: "SPEECH",
          },
          toolUseOutputConfiguration: {
            mediaType: "application/json",
          },
        },
      },
    };

    this.sendEvent(promptStartEvent);
    this.sendSystemPrompt();
  }

  sendSystemPrompt() {
    const systemContentName = crypto.randomUUID();
    const contentStartEvent = {
      event: {
        contentStart: {
          promptName: this.promptName,
          contentName: systemContentName,
          type: "TEXT",
          interactive: true,
          textInputConfiguration: {
            mediaType: "text/plain",
          },
        },
      },
    };
    this.sendEvent(contentStartEvent);

    // System prompt - use custom prompt if available, otherwise default
    const defaultPrompt = `
You're Telly, AnyTelco's customer support voice assistant. Your job is to assist customers with their problems relating to AnyTelco products and services.
Keep your responses short, generally two or three sentences for chatty scenarios.
You may start each of your sentences with emotions in square brackets such as [amused], [neutral] or any other stage direction such as [joyful]. Only use a single pair of square brackets for indicating a stage command.

IMPORTANT: For any specific information about AnyTelco products, services, plans, pricing, technical issues, or account details that is not provided in the account information retrieved from useProfileSearch, you MUST use the knowledge base lookup.
DO NOT make up information about AnyTelco offerings or policies. Only use your general knowledge for common concepts unrelated to AnyTelco specifics. If you are not very sure about an answer, do a knowledge base lookup.

## Boundaries and Focus
- Be conversational and authentic rather than following rigid scripts
- Listen actively to understand the customer's specific situation
- ALWAYS use the knowledge base lookups to provide accurate information about AnyTelco
- DO NOT MAKE UP any information about AnyTelco products, services, or policies
- Only use your own knowledge for general concepts unrelated to AnyTelco specifics
- If information is not in the retrieved Account Information and not in the knowledge base, acknowledge that you need to check and offer to look it up When to Use Knowledge Base Lookups For ALL of the following scenarios:
 - ANY questions about AnyTelco plans, pricing, or promotions
 - ANY cancellation or retention conversations
 - ANY bundle opportunities or additional services
 - ANY technical issues, service questions, or troubleshooting
 - ANY coverage or outage information Always preface responses to these topics with a knowledge base lookup rather than generating information from your general knowledge. Use your knowledge base lookup extremely liberally.

## Conversation Structure
1. First, Greet the customer warmly and briefly identify yourself
2. Next, collect customer phone number to retrieve their account and cell plan information.
3. Once you retrieve customer's account and cell plan information, ask what you can help the customer with.
    `;
    const systemPrompt = this.customSystemPrompt || defaultPrompt;

    console.log(
      "Sending system prompt:",
      systemPrompt.substring(0, 100) + "..."
    );

    const textInputEvent = {
      event: {
        textInput: {
          promptName: this.promptName,
          contentName: systemContentName,
          content: systemPrompt,
          role: "SYSTEM",
        },
      },
    };
    this.sendEvent(textInputEvent);

    const contentEndEvent = {
      event: {
        contentEnd: {
          promptName: this.promptName,
          contentName: systemContentName,
        },
      },
    };
    this.sendEvent(contentEndEvent);

    this.startAudioContent();
  }

  startAudioContent() {
    this.audioContentName = crypto.randomUUID();
    const contentStartEvent = {
      event: {
        contentStart: {
          promptName: this.promptName,
          contentName: this.audioContentName,
          type: "AUDIO",
          role: "USER",
          interactive: true,
          audioInputConfiguration: {
            mediaType: "audio/lpcm",
            sampleRateHertz: 16000,
            sampleSizeBits: 16,
            channelCount: 1,
            audioType: "SPEECH",
            encoding: "base64",
          },
        },
      },
    };
    this.sendEvent(contentStartEvent);
  }

  sendAudioChunk(base64AudioData) {
    if (!this.promptName || !this.audioContentName) {
      console.error(
        "Cannot send audio chunk - missing promptName or audioContentName"
      );
      return;
    }

    const audioInputEvent = {
      event: {
        audioInput: {
          promptName: this.promptName,
          contentName: this.audioContentName,
          content: base64AudioData,
          role: "USER",
        },
      },
    };
    this.sendEvent(audioInputEvent);
  }

  endContent() {
    const contentEndEvent = {
      event: {
        contentEnd: {
          promptName: this.promptName,
          contentName: this.audioContentName,
        },
      },
    };
    this.sendEvent(contentEndEvent);
  }

  endPrompt() {
    const promptEndEvent = {
      event: {
        promptEnd: {
          promptName: this.promptName,
        },
      },
    };
    this.sendEvent(promptEndEvent);
  }

  endSession() {
    const sessionEndEvent = {
      event: {
        sessionEnd: {},
      },
    };
    this.sendEvent(sessionEndEvent);
    this.socket.close();
  }

  cleanup() {
    this.isProcessing = false;
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      try {
        if (this.audioContentName && this.promptName) {
          this.endContent();
          this.endPrompt();
        }
        this.endSession();
      } catch (error) {
        console.error("Error during cleanup:", error);
      }
    }
    this.chatHistoryManager.endConversation();
  }

  // Keep just the basic methods for speech detection
  startUserTalking() {
    console.log("User started talking");
  }

  stopUserTalking() {
    console.log("User stopped talking");
  }
}
