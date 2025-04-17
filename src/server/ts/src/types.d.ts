export interface InferenceConfig {
  readonly maxTokens: number;
  readonly topP: number;
  readonly temperature: number;
}

export type ContentType = "AUDIO" | "TEXT" | "TOOL";
export type AudioType = "SPEECH";
export type AudioMediaType = "audio/lpcm";
export type TextMediaType = "text/plain" | "application/json";

export interface AudioConfiguration {
  readonly audioType: AudioType;
  readonly mediaType: AudioMediaType;
  readonly sampleRateHertz: number;
  readonly sampleSizeBits: number;
  readonly channelCount: number;
  readonly encoding: string;
  readonly voiceId?: string;
}

export interface TextConfiguration {
  readonly mediaType: TextMediaType;
}

export interface ToolConfiguration {
  readonly toolUseId: string;
  readonly type: "TEXT";
  readonly textInputConfiguration: {
    readonly mediaType: "text/plain";
  };
}

interface WebhookResponse {
  action: string;
  text?: string;
  from?: string;
  endpoint?: Array<{
    type: string;
    uri: string;
    "content-type": string;
  }>;
}

interface SessionEventData {
  [key: string]: any;
}

interface Session {
  onEvent: (event: string, callback: (data: SessionEventData) => void) => void;
  setupPromptStart: () => Promise<void>;
  setupSystemPrompt: (
    textConfig?: { mediaType: string },
    systemPromptContent?: string
  ) => Promise<void>;
  setupStartAudio: () => Promise<void>;
  streamAudio: (buffer: Buffer) => Promise<void>;
  endAudioContent: () => Promise<void>;
  endPrompt: () => Promise<void>;
  close: () => Promise<void>;
}

interface ActiveSession {
  sessionId: string;
  session: Session;
}
