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

import { WebSocketEventManager } from "./websocketEvents.js";
import { getCognitoAuth } from "./cognito.js";

// Global variables
let wsManager;
let sessionTime = 0;
let sessionTimer;
let isRecording = false;
let conversationData = [];
let currentMessageId = 1;
let cognitoAuth;
let systemPrompt = ""; // Store system prompt content
let uiInitialized = false; // Track if UI has been initialized

// Initialize on page load
document.addEventListener("DOMContentLoaded", async () => {
  try {
    // Attempt authentication
    const isAuthenticated = await doCognitoAuthentication();

    if (isAuthenticated) {
      // Create HTML structure if not already created
      if (!uiInitialized) {
        createHtmlStructure();
        uiInitialized = true;
      }

      // Load saved system prompt
      loadSystemPrompt();

      // Initialize the app
      initializeApp();
    } else {
      // Just waiting for redirect to Cognito login
      if (!uiInitialized) {
        createMinimalAuthUI();
        updateStatus("Authenticating...", "authenticating");
      }
    }
  } catch (error) {
    console.error("Error during authentication:", error);
    if (!uiInitialized) {
      createMinimalAuthUI();
      updateStatus("Authentication Error", "error");
    }
  }
});

// Create minimal UI during authentication
function createMinimalAuthUI() {
  document.body.innerHTML = `
    <div id="app">
      <div id="status" class="authenticating">Authenticating...</div>
    </div>
  `;
}

// Load system prompt from localStorage if available
function loadSystemPrompt() {
  console.log("Loading system prompt...");
  const savedPrompt = localStorage.getItem("systemPrompt");
  if (savedPrompt) {
    console.log("Loaded prompt from localStorage");
    systemPrompt = savedPrompt;
    const promptTextarea = document.getElementById("system-prompt-textarea");
    if (promptTextarea) {
      promptTextarea.value = systemPrompt;
    }
  } else {
    // Default system prompt
    console.log("No saved prompt found, fetching default...");
    fetch("system_prompt.txt")
      .then((response) => response.text())
      .then((text) => {
        console.log("Loaded default prompt from file");
        systemPrompt = text;
        const promptTextarea = document.getElementById(
          "system-prompt-textarea"
        );
        if (promptTextarea) {
          promptTextarea.value = systemPrompt;
        }
      })
      .catch((error) => {
        console.error("Error loading system prompt:", error);
        systemPrompt =
          "You're Telly, AnyTelco's customer support voice assistant.";
        const promptTextarea = document.getElementById(
          "system-prompt-textarea"
        );
        if (promptTextarea) {
          promptTextarea.value = systemPrompt;
        }
      });
  }
}

// Save system prompt to localStorage
function saveSystemPrompt() {
  const promptTextarea = document.getElementById("system-prompt-textarea");
  if (promptTextarea) {
    systemPrompt = promptTextarea.value;
    localStorage.setItem("systemPrompt", systemPrompt);

    // Show save confirmation
    showSaveConfirmation();
  }
}

// Show save confirmation
function showSaveConfirmation() {
  const saveConfirmationElement = document.getElementById("save-confirmation");
  if (saveConfirmationElement) {
    saveConfirmationElement.textContent = "Saved!";
    saveConfirmationElement.style.display = "block";

    // Hide after 2 seconds
    setTimeout(() => {
      saveConfirmationElement.style.display = "none";
    }, 2000);
  }
}

// Handle authentication process
async function doCognitoAuthentication() {
  // Bypass authentication in development mode
  if (import.meta.env.DEV) {
    console.log("Running in local development mode, bypassing authentication.");
    return true;
  }

  cognitoAuth = getCognitoAuth();
  const isAuthenticated = await cognitoAuth.handleAuth();
  return isAuthenticated;
}

// Logout function
function handleLogout() {
  if (cognitoAuth) {
    cognitoAuth.logout();
  }
}

// Initialize the application
function initializeApp() {
  // Give the DOM a moment to fully render
  setTimeout(() => {
    // Set up event listeners for main controls
    const startButton = document.getElementById("start");
    const stopButton = document.getElementById("stop");

    if (startButton) {
      startButton.addEventListener("click", startStreaming);
    } else {
      console.error("Start button not found");
    }

    if (stopButton) {
      stopButton.addEventListener("click", stopStreaming);
    } else {
      console.error("Stop button not found");
    }

    // Set up system prompt editor listeners
    const showPromptButton = document.getElementById("show-prompt-button");
    const savePromptButton = document.getElementById("save-prompt-button");
    const logoutButton = document.getElementById("logout-button");

    if (showPromptButton) {
      showPromptButton.addEventListener("click", togglePromptEditor);
    }

    if (savePromptButton) {
      savePromptButton.addEventListener("click", saveSystemPrompt);
    }

    if (logoutButton) {
      logoutButton.addEventListener("click", handleLogout);
    }

    // Initialize UI components
    updateStatus("Disconnected", "disconnected");
    updateTimerDisplay();

    console.log("App initialization complete");
  }, 100); // Small delay to ensure DOM is ready
}

// Toggle prompt editor visibility
function togglePromptEditor() {
  const editorContainer = document.getElementById("system-prompt-container");
  const toggleButton = document.getElementById("show-prompt-button");

  if (!editorContainer) {
    console.error("Editor container not found");
    return;
  }

  const isVisible = editorContainer.style.display !== "none";

  if (isVisible) {
    editorContainer.style.display = "none";
    if (toggleButton) toggleButton.textContent = "Show Prompt";
  } else {
    editorContainer.style.display = "block";
    if (toggleButton) toggleButton.textContent = "Hide Prompt";
  }
}

// Update status indicator
function updateStatus(message, status) {
  const statusElement = document.getElementById("status");
  if (statusElement) {
    statusElement.textContent = message;
    statusElement.className = status;
  } else {
    console.error("Status element not found");
  }
}

// Format time display
function formatTime(seconds) {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs < 10 ? "0" + secs : secs}`;
}

// Update the timer display
function updateTimerDisplay() {
  const timerElement = document.getElementById("timer");
  if (timerElement) {
    timerElement.textContent = formatTime(sessionTime);
  } else {
    console.error("Timer element not found");
  }
}

// Start streaming audio
async function startStreaming() {
  const startButton = document.getElementById("start");
  const stopButton = document.getElementById("stop");

  if (startButton) startButton.disabled = true;
  if (stopButton) stopButton.disabled = false;

  isRecording = true;
  updateStatus("Connected", "connected");

  // Create WebSocket manager without fallback
  wsManager = new WebSocketEventManager();

  // Add custom handlers
  wsManager.onUpdateTranscript = updateTranscript;
  wsManager.onUpdateStatus = updateStatus;
  wsManager.onAudioReceived = handleAudioReceived;

  // Pass the current system prompt to the WebSocketEventManager
  wsManager.setSystemPrompt(systemPrompt);
  console.log("System prompt passed to WebSocketManager");

  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1, // Mono
        sampleRate: 16000, // 16kHz
        sampleSize: 16, // 16-bit
        echoCancellation: true, // Enable echo cancellation
        noiseSuppression: true, // Enable noise suppression
        autoGainControl: true, // Enable automatic gain control
      },
    });

    // Create AudioContext for processing
    const audioContext = new AudioContext({
      sampleRate: 16000,
      latencyHint: "interactive",
    });

    // Create MediaStreamSource
    const source = audioContext.createMediaStreamSource(stream);

    // Create ScriptProcessor for raw PCM data
    const processor = audioContext.createScriptProcessor(1024, 1, 1);

    source.connect(processor);
    processor.connect(audioContext.destination);

    // Variables for user speech detection
    let userIsSpeaking = false;
    let silenceTimer = null;
    let speakingStarted = false;
    const SILENCE_THRESHOLD = 0.01;
    const SPEECH_THRESHOLD = 0.015; // Slightly higher threshold to confirm speech
    const SILENCE_DURATION = 1000; // 1 second of silence to mark end of speech
    const MIN_SPEECH_SAMPLES = 5; // Need multiple samples to confirm speech

    // Counter to confirm speech
    let speechSampleCount = 0;

    processor.onaudioprocess = (e) => {
      const inputData = e.inputBuffer.getChannelData(0);

      // Convert Float32Array to Int16Array
      const pcmData = new Int16Array(inputData.length);
      for (let i = 0; i < inputData.length; i++) {
        // Convert float to 16-bit integer
        const s = Math.max(-1, Math.min(1, inputData[i]));
        pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }

      // Calculate audio level for this chunk
      const audioLevel = Math.max(...Array.from(inputData).map(Math.abs));

      // Speech detection logic
      if (audioLevel > SPEECH_THRESHOLD) {
        // Potential speech detected
        speechSampleCount++;

        // If we have enough speech samples, confirm the user is speaking
        if (speechSampleCount >= MIN_SPEECH_SAMPLES && !userIsSpeaking) {
          userIsSpeaking = true;
          if (wsManager && !speakingStarted) {
            wsManager.startUserTalking();
            speakingStarted = true;
          }
        }

        // Reset silence timer if active
        if (silenceTimer) {
          clearTimeout(silenceTimer);
          silenceTimer = null;
        }
      } else if (audioLevel < SILENCE_THRESHOLD && userIsSpeaking) {
        // Potential silence detected
        speechSampleCount = 0;

        // Start silence timer if not already running
        if (!silenceTimer) {
          silenceTimer = setTimeout(() => {
            // After SILENCE_DURATION, mark user as stopped talking
            userIsSpeaking = false;
            speakingStarted = false;
            if (wsManager) {
              wsManager.stopUserTalking();
            }
            silenceTimer = null;
          }, SILENCE_DURATION);
        }
      } else {
        // Reset speech counter during ambiguous audio levels
        speechSampleCount = 0;
      }

      // Convert to base64
      const base64data = btoa(
        String.fromCharCode.apply(null, new Uint8Array(pcmData.buffer))
      );

      // Send to WebSocket
      if (wsManager) {
        wsManager.sendAudioChunk(base64data);
      }
    };

    // Store cleanup functions
    window.audioCleanup = () => {
      // Ensure we stop tracking user speech on cleanup
      if (wsManager && userIsSpeaking) {
        wsManager.stopUserTalking();
      }

      if (silenceTimer) {
        clearTimeout(silenceTimer);
      }

      processor.disconnect();
      source.disconnect();
      stream.getTracks().forEach((track) => track.stop());
    };

    // Start session timer
    startSessionTimer();
  } catch (error) {
    console.error("Error accessing microphone:", error);
    updateStatus(`Error: ${error.message}`, "error");
  }
}

// Stop streaming audio
function stopStreaming() {
  const startButton = document.getElementById("start");
  const stopButton = document.getElementById("stop");

  // Cleanup audio processing
  if (window.audioCleanup) {
    window.audioCleanup();
  }

  if (wsManager) {
    wsManager.cleanup();
  }

  // Clear timer
  if (sessionTimer) {
    clearInterval(sessionTimer);
  }

  // Update UI
  if (startButton) startButton.disabled = false;
  if (stopButton) stopButton.disabled = true;

  isRecording = false;
  updateStatus("Disconnected", "disconnected");
}

// Update transcript with the conversation history
async function updateTranscript(history) {
  if (!history || history.length === 0) return;

  const chatContainer = document.getElementById("chat-container");
  if (!chatContainer) {
    console.error("Chat container not found");
    return;
  }

  // Clear the container
  chatContainer.innerHTML = "";

  // Add all messages to the chat container
  for (let i = 0; i < history.length; i++) {
    const item = history[i];

    // Skip if no role or message or if it's a system message
    if (!item.role || !item.message || item.role.toLowerCase() === "system") {
      continue;
    }

    // Create message element
    const messageElement = document.createElement("div");
    let messageClass = "";

    if (item.role.toLowerCase() === "user") {
      messageClass = "user";
    } else if (item.role.toLowerCase() === "assistant") {
      messageClass = "assistant";
    }

    messageElement.className = `message ${messageClass}`;

    // Create message content
    const contentElement = document.createElement("div");
    contentElement.className = "message-content";

    // For assistant messages, extract emotion tag if present
    let messageText = item.message;
    if (item.role.toLowerCase() === "assistant") {
      const match = messageText.match(/^\[(.*?)\](.*)/);
      if (match) {
        // Extract emotion and message
        const emotion = match[1];
        const text = match[2];

        // Add emotion as a prefix
        messageText = `[${emotion}]${text}`;
      }
    }

    contentElement.textContent = messageText;

    // Assemble message (no timestamp)
    messageElement.appendChild(contentElement);

    // Add to chat container
    chatContainer.appendChild(messageElement);
  }

  // Scroll to the bottom
  chatContainer.scrollTop = chatContainer.scrollHeight;
}

// Start the session timer
function startSessionTimer() {
  sessionTime = 0;

  sessionTimer = setInterval(() => {
    // Update session time
    sessionTime++;

    // Update the timer display
    updateTimerDisplay();
  }, 1000);
}

// Handle audio received from the websocket
function handleAudioReceived(audioData) {
  // In a real implementation, the WebSocketEventManager already takes care of audio playback
  // console.log("Audio data received, length:", audioData.length);
}

// Creates the HTML structure for the interface
function createHtmlStructure() {
  document.body.innerHTML = `
    <div id="app">
      <div class="header">
        <h1>Call Center Assistant Playground</h1>
        <div class="header-controls">
          <div class="timer-container">
            <div class="timer-icon">🕐</div>
            <span id="timer">0:00</span>
          </div>
          <div id="status" class="disconnected">Disconnected</div>
          <div class="button-container">
            <button id="logout-button" class="button">Logout</button>
            <button id="show-prompt-button" class="button">Show Prompt</button>
            <button id="start" class="button">Start Session</button>
            <button id="stop" class="button" disabled>Stop Session</button>
          </div>
        </div>
      </div>

      <!-- System Prompt Editor (initially hidden) -->
      <div id="system-prompt-container" style="display: none;">
        <h2>System Prompt Editor</h2>
        <div id="save-confirmation" style="display: none;">Saved!</div>
        <div class="editor-container">
          <textarea
            id="system-prompt-textarea"
            class="system-prompt-textarea"
            placeholder="Enter system prompt here..."
          ></textarea>
          <div class="prompt-controls">
            <button id="save-prompt-button" class="button">Save Prompt</button>
          </div>
        </div>
      </div>

      <div id="chat-container"></div>

      <div id="controls">
        <!-- Controls moved to header area -->
      </div>

      <div class="footer">
        <div>Voice Chat Interface v1.0</div>
      </div>
    </div>
  `;

  // Ensure audio context is resumed after user interaction
  document.addEventListener(
    "click",
    () => {
      if (
        wsManager &&
        wsManager.audioContext &&
        wsManager.audioContext.state === "suspended"
      ) {
        wsManager.audioContext.resume();
      }
    },
    { once: true }
  );
}
