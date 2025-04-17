import * as fs from "fs";
import express, { Request, Response } from "express";
import bodyParser from "body-parser";
import expressWs from "express-ws";
import * as https from "https";
import * as path from "path";
import { fromEnv } from "@aws-sdk/credential-providers";
import { NovaSonicBidirectionalStreamClient } from "./client";
import { Buffer } from "node:buffer";
import WebSocket from "ws";
import {
  Session,
  ActiveSession,
  SessionEventData,
  WebhookResponse,
} from "./types";
import { v4 as uuidv4 } from "uuid";

const app = express();
const wsInstance = expressWs(app);
app.use(bodyParser.json());

const AWS_PROFILE_NAME: string = process.env.AWS_PROFILE || "";
const bedrockClient = new NovaSonicBidirectionalStreamClient({
  requestHandlerConfig: {
    maxConcurrentStreams: 10,
  },
  clientConfig: {
    region: process.env.AWS_REGION || "us-east-1",
    credentials: fromEnv(),
  },
});

const useVonage: boolean = true;
const useJson: boolean = true;

/* Periodically check for and close inactive sessions (every minute).
 * Sessions with no activity for over 5 minutes will be force closed
 */
setInterval(() => {
  console.log("Running session cleanup check");
  const now = Date.now();

  bedrockClient.getActiveSessions().forEach((sessionId: string) => {
    const lastActivity = bedrockClient.getLastActivityTime(sessionId);

    const fiveMinsInMs = 5 * 60 * 1000;
    if (now - lastActivity > fiveMinsInMs) {
      console.log(`Closing inactive session ${sessionId} due to inactivity.`);
      try {
        bedrockClient.forceCloseSession(sessionId);
      } catch (error: unknown) {
        console.error(
          `Error force closing inactive session ${sessionId}:`,
          error
        );
      }
    }
  });
}, 60000);

// Track active websocket connections with their session IDs
const channelStreams = new Map<string, Session>(); // channelId -> Session
const channelClients = new Map<string, Set<WebSocket>>(); // channelId -> Set of connected clients
const clientChannels = new Map<WebSocket, string>(); // WebSocket -> channelId

wsInstance.getWss().on("connection", (ws: WebSocket) => {
  console.log("Websocket connection is open");
});

function setUpEventHandlersForChannel(session: Session, channelId: string) {
  function handleSessionEvent(
    session: Session,
    channelId: string,
    eventName: string,
    isError: boolean = false
  ) {
    session.onEvent(eventName, (data: SessionEventData) => {
      console[isError ? "error" : "debug"](eventName, data);

      // Broadcast to all clients in this channel
      const clients = channelClients.get(channelId) || new Set();
      const message = JSON.stringify({ event: { [eventName]: { ...data } } });

      clients.forEach((client) => {
        if (client.readyState === WebSocket.OPEN) {
          client.send(message);
        }
      });
    });
  }

  handleSessionEvent(session, channelId, "contentStart");
  handleSessionEvent(session, channelId, "textOutput");
  handleSessionEvent(session, channelId, "error", true);
  handleSessionEvent(session, channelId, "toolUse");
  handleSessionEvent(session, channelId, "toolResult");
  handleSessionEvent(session, channelId, "contentEnd");

  session.onEvent("streamComplete", () => {
    console.log("Stream completed for channel:", channelId);

    const clients = channelClients.get(channelId) || new Set();
    const message = JSON.stringify({ event: "streamComplete" });
    clients.forEach((client) => {
      if (client.readyState === WebSocket.OPEN) client.send(message);
    });
  });

  session.onEvent("audioOutput", (data: SessionEventData) => {
    // Process audio data as before
    let audioBuffer: Int16Array | null = null;
    const CHUNK_SIZE_BYTES = 640;
    const SAMPLES_PER_CHUNK = CHUNK_SIZE_BYTES / 2;

    const buffer = Buffer.from(data["content"], "base64");
    const newPcmSamples = new Int16Array(
      buffer.buffer,
      buffer.byteOffset,
      buffer.length / Int16Array.BYTES_PER_ELEMENT
    );

    const clients = channelClients.get(channelId) || new Set();

    if (useJson) {
      const message = JSON.stringify({ event: { audioOutput: { ...data } } });
      clients.forEach((client) => {
        if (client.readyState === WebSocket.OPEN) {
          client.send(message);
        }
      });
    }

    if (useVonage) {
      let combinedSamples: Int16Array;
      if (audioBuffer) {
        combinedSamples = new Int16Array(
          audioBuffer.length + newPcmSamples.length
        );
        combinedSamples.set(audioBuffer);
        combinedSamples.set(newPcmSamples, audioBuffer.length);
      } else {
        combinedSamples = newPcmSamples;
      }

      let offset = 0;
      while (offset + SAMPLES_PER_CHUNK <= combinedSamples.length) {
        const chunk = combinedSamples.slice(offset, offset + SAMPLES_PER_CHUNK);

        // Send to all clients in the channel
        clients.forEach((client) => {
          if (client.readyState === WebSocket.OPEN) {
            client.send(chunk);
          }
        });

        offset += SAMPLES_PER_CHUNK;
      }

      audioBuffer =
        offset < combinedSamples.length ? combinedSamples.slice(offset) : null;
    }
  });
}

wsInstance.app.ws("/socket", (ws: WebSocket, req: Request) => {
  // Get channel from query parameters or use a default
  const channelId = req.query.channel?.toString() || uuidv4();
  console.log(`Client requesting connection to channel: ${channelId}`);

  const sendError = (message: string, details: string) => {
    console.error("Error:", details);
    ws.send(JSON.stringify({ event: "error", data: { message, details } }));
  };

  const initializeOrJoinChannel = async () => {
    try {
      let session: Session;
      let isNewChannel = false;

      // Check if channel exists
      if (channelStreams.has(channelId)) {
        console.log(`Client joining existing channel: ${channelId}`);
        session = channelStreams.get(channelId)!;
      } else {
        // Create new session for this channel
        console.log(`Creating new channel: ${channelId}`);
        session = bedrockClient.createStreamSession(channelId);
        bedrockClient.initiateSession(channelId);
        channelStreams.set(channelId, session);
        channelClients.set(channelId, new Set());

        // Set up event handlers for the new session (only once per channel)
        setUpEventHandlersForChannel(session, channelId);

        // Initialize the session
        await session.setupPromptStart();
        await session.setupSystemPrompt(
          undefined,
          "You are Claude, an AI assistant having a voice conversation. Keep responses concise and conversational."
        );
        await session.setupStartAudio();

        isNewChannel = true;
      }

      // Add this client to the channel
      const clients = channelClients.get(channelId)!;
      clients.add(ws);
      clientChannels.set(ws, channelId);

      console.log(`Channel ${channelId} has ${clients.size} connected clients`);

      // Notify client that connection is successful
      ws.send(
        JSON.stringify({
          event: "sessionReady",
          message: `Connected to channel ${channelId}`,
          isNewChannel: isNewChannel,
        })
      );
    } catch (error) {
      sendError("Failed to initialize or join channel", String(error));
      ws.close();
    }
  };

  const handleMessage = async (msg: Buffer | string) => {
    const channelId = clientChannels.get(ws);
    if (!channelId) {
      sendError("Channel not found", "No active channel for this connection");
      return;
    }

    const session = channelStreams.get(channelId);
    if (!session) {
      sendError("Session not found", "No active session for this channel");
      return;
    }

    try {
      let audioBuffer: Buffer | undefined;
      try {
        const jsonMsg = JSON.parse(msg.toString());
        console.log("Event received of type:", jsonMsg.type);
        switch (jsonMsg.type) {
          case "promptStart":
            await session.setupPromptStart();
            break;
          case "systemPrompt":
            await session.setupSystemPrompt(undefined, jsonMsg.data);
            break;
          case "audioStart":
            await session.setupStartAudio();
            break;
          case "stopAudio":
            await session.endAudioContent();
            await session.endPrompt();
            console.log("Session cleanup complete");
            break;
          default:
            break;
        }
      } catch (e) {
        if (useVonage) {
          audioBuffer = Buffer.from(msg as Buffer);
          await session.streamAudio(audioBuffer);
        }
      } finally {
        if (useJson) {
          const msgJson = JSON.parse(msg.toString());
          audioBuffer = Buffer.from(msgJson.event.audioInput.content, "base64");
          await session.streamAudio(audioBuffer);
        }
      }
    } catch (error) {
      sendError("Error processing message", String(error));
    }
  };

  const handleClose = async () => {
    const channelId = clientChannels.get(ws);
    if (!channelId) {
      console.log("No channel to clean up for this connection");
      return;
    }

    const clients = channelClients.get(channelId);
    if (clients) {
      clients.delete(ws);
      console.log(
        `Client disconnected from channel ${channelId}, ${clients.size} clients remaining`
      );

      // If this was the last client, clean up the channel
      if (clients.size === 0) {
        console.log(
          `Last client left channel ${channelId}, cleaning up resources`
        );

        const session = channelStreams.get(channelId);
        if (session && bedrockClient.isSessionActive(channelId)) {
          try {
            await Promise.race([
              (async () => {
                await session.endAudioContent();
                await session.endPrompt();
                await session.close();
              })(),
              new Promise((_, reject) =>
                setTimeout(
                  () => reject(new Error("Session cleanup timeout")),
                  3000
                )
              ),
            ]);
            console.log(`Successfully cleaned up channel: ${channelId}`);
          } catch (error) {
            console.error(`Error cleaning up channel ${channelId}:`, error);
            try {
              bedrockClient.forceCloseSession(channelId);
              console.log(`Force closed session for channel: ${channelId}`);
            } catch (e) {
              console.error(
                `Failed to force close session for channel ${channelId}:`,
                e
              );
            }
          }
        }

        channelStreams.delete(channelId);
        channelClients.delete(channelId);
      }
    }
    clientChannels.delete(ws);
  };

  initializeOrJoinChannel();
  ws.on("message", handleMessage);
  ws.on("close", handleClose);
});

/* SERVER LOGIC */

const port: number = parseInt(process.env.PORT || "3000");
const server = app.listen(port, () =>
  console.log(`Original server listening on port ${port}`)
);

const httpsPort: number = 443;
const httpsServer = https.createServer(app).listen(httpsPort, () => {
  console.log(`HTTPS server listening on port ${httpsPort}`);
});

app.get("/health", (req: Request, res: Response) => {
  res.status(200).json({ status: "ok", timestamp: new Date().toISOString() });
});

// Gracefully shut down.
process.on("SIGINT", async () => {
  console.log("Shutting down servers...");

  const forceExitTimer = setTimeout(() => {
    console.error("Forcing server shutdown after timeout");
    process.exit(1);
  }, 5000);

  try {
    const sessionPromises: Promise<void>[] = [];

    for (const [channelId, session] of channelStreams.entries()) {
      console.log(`Closing session for channel ${channelId} during shutdown`);

      sessionPromises.push(
        bedrockClient.closeSession(channelId).catch((error: unknown) => {
          console.error(
            `Error closing session for channel ${channelId} during shutdown:`,
            error
          );
          bedrockClient.forceCloseSession(channelId);
        })
      );

      const clients = channelClients.get(channelId) || new Set();
      clients.forEach((ws) => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.close();
        }
      });
    }

    await Promise.all(sessionPromises);

    await Promise.all([
      new Promise((resolve) => server.close(resolve)),
      new Promise((resolve) => httpsServer.close(resolve)),
    ]);

    clearTimeout(forceExitTimer);
    console.log("Servers shut down");
    process.exit(0);
  } catch (error: unknown) {
    console.error("Error during server shutdown:", error);
    process.exit(1);
  }
});

// Add endpoint to list active channels
app.get("/channels", (req: Request, res: Response) => {
  const channels = [];
  for (const [channelId, clients] of channelClients.entries()) {
    channels.push({
      id: channelId,
      clientCount: clients.size,
      active: bedrockClient.isSessionActive(channelId),
    });
  }
  res.status(200).json({ channels });
});

/* VONAGE SERVER LOGIC */

if (useVonage) {
  app.get("/webhooks/answer", (req: Request, res: Response) => {
    const nccoResponse: WebhookResponse[] = [
      {
        action: "talk",
        text: "Please wait while we connect you to the echo server",
      },
      {
        action: "connect",
        from: "Vonage",
        endpoint: [
          {
            type: "websocket",
            uri: `wss://${req.hostname}/socket`,
            "content-type": "audio/l16;rate=16000",
          },
        ],
      },
    ];
    res.status(200).json(nccoResponse);
  });

  app.post("/webhooks/events", (req: Request, res: Response) => {
    console.log(req.body);
    res.sendStatus(200);
  });
}
