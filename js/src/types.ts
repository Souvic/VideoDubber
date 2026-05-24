export interface TranslationJobParams {
  fileUrl: string;
  targetLanguage: string;
  numSpeakers?: string;
  projectName?: string;
  filetype?: string;
  originalLanguage?: string;
  selectedVoices: string[];
  speakers?: string[];
  audioshift?: string;
  translator?: string;
  hasSubtitleFile?: boolean;
  subtitleLanguageType?: string;
  glossaryId?: string;
  bg1?: string;
  bg2?: string;
  voiceCloning?: boolean;
}

export interface JobStatus {
  pid: string;
  status: string;
  httpStatus: number;
  raw: Record<string, unknown>;
  outputUrls: Record<string, unknown>;
  availableMinutes?: number;
  isComplete: boolean;
  isProcessing: boolean;
  translatedMediaUrl?: string;
}

export interface VideoDubberClientOptions {
  apiKey: string;
  baseUrl?: string;
  timeoutMs?: number;
  rateLimitMaxRetries?: number;
  rateLimitBackoffBase?: number;
  partnerMinInterval?: number;
  verbose?: boolean;
  debug?: boolean;
  fetch?: typeof fetch;
}

export interface WaitForJobOptions {
  pollInterval?: number;
  maxWait?: number;
}

export interface CreateJobResponse {
  status: string;
  pid: string;
  project_path?: string;
  [key: string]: unknown;
}

export function toJobPayload(params: TranslationJobParams): Record<string, unknown> {
  return {
    file_url: params.fileUrl,
    filetype: params.filetype ?? "mp4",
    OriginalLanguage: params.originalLanguage ?? "unknown",
    TargetLanguage: params.targetLanguage,
    NumSpeakers: params.numSpeakers ?? "1",
    projectname: params.projectName ?? "API Project",
    selectedvoices: params.selectedVoices,
    speakers: params.speakers ?? ["Speaker 1"],
    audioshift: params.audioshift ?? "0",
    translator: params.translator ?? "auto",
    has_subtitle_file: String(params.hasSubtitleFile ?? false).toLowerCase(),
    subtitle_language_type: params.subtitleLanguageType ?? "source",
    glossary_id: params.glossaryId ?? "",
    bg1: params.bg1 ?? "Auto (Not recommended)",
    bg2: params.bg2 ?? "0",
    voice_cloning: params.voiceCloning ?? false,
  };
}

export function parseJobStatus(
  pid: string,
  httpStatus: number,
  data: Record<string, unknown>,
): JobStatus {
  const status = String(data.status ?? "unknown");
  const outputUrls = (data.output_urls as Record<string, unknown>) ?? {};
  const translatedMediaUrl =
    typeof outputUrls.translated_media === "string"
      ? outputUrls.translated_media
      : undefined;

  return {
    pid,
    status,
    httpStatus,
    raw: data,
    outputUrls,
    availableMinutes:
      typeof data.available_minutes === "number"
        ? data.available_minutes
        : undefined,
    isComplete: status === "complete",
    isProcessing: ["processing", "Need", "Taken_up"].includes(status),
    translatedMediaUrl,
  };
}
