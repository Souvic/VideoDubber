#!/usr/bin/env node

import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { DEFAULT_BASE_URL } from "./constants.js";
import { VideoDubberClient } from "./client.js";
import { ApiError, RateLimitError } from "./errors.js";
import { formatApiError } from "./format-api-error.js";
import { TranslationJobParams } from "./types.js";

interface CliOptions {
  fileUrl: string;
  apiKey: string;
  baseUrl: string;
  originalLanguage: string;
  targetLanguage: string;
  numSpeakers: string;
  projectName: string;
  voices: string[];
  speakers: string[];
  voiceCloning: boolean;
  filetype: string;
  audioshift: string;
  translator: string;
  glossaryId: string;
  bg1: string;
  pollInterval: number;
  maxWait: number;
  output?: string;
  json: boolean;
  quiet: boolean;
  debug: boolean;
}

function inferFiletype(fileUrl: string): string {
  const pathname = fileUrl.split("?")[0] ?? fileUrl;
  const ext = path.extname(pathname).replace(/^\./, "").toLowerCase();
  return ext || "mp4";
}

function parseArgs(argv: string[]): CliOptions {
  const options: Partial<CliOptions> & { voices: string[]; speakers: string[] } = {
    voices: [],
    speakers: [],
    apiKey: process.env.VIDEODUBBER_API_KEY ?? "",
    baseUrl: process.env.VIDEODUBBER_API_BASE ?? DEFAULT_BASE_URL,
    originalLanguage: "unknown",
    numSpeakers: "1",
    projectName: "API Project",
    voiceCloning: false,
    filetype: "",
    audioshift: "0",
    translator: "auto",
    glossaryId: "",
    bg1: "Auto (Not recommended)",
    pollInterval: 15,
    maxWait: 3600,
    json: false,
    quiet: false,
    debug: false,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const next = argv[i + 1];

    switch (arg) {
      case "--file-url":
        options.fileUrl = next;
        i += 1;
        break;
      case "--api-key":
        options.apiKey = next ?? "";
        i += 1;
        break;
      case "--base-url":
        options.baseUrl = next ?? DEFAULT_BASE_URL;
        i += 1;
        break;
      case "--original-language":
        options.originalLanguage = next ?? "unknown";
        i += 1;
        break;
      case "--target-language":
        options.targetLanguage = next ?? "";
        i += 1;
        break;
      case "--num-speakers":
        options.numSpeakers = next ?? "1";
        i += 1;
        break;
      case "--project-name":
        options.projectName = next ?? "API Project";
        i += 1;
        break;
      case "--voice":
        options.voices.push(next ?? "");
        i += 1;
        break;
      case "--speaker":
        options.speakers.push(next ?? "");
        i += 1;
        break;
      case "--voice-cloning":
        options.voiceCloning = true;
        break;
      case "--filetype":
        options.filetype = next ?? "";
        i += 1;
        break;
      case "--audioshift":
        options.audioshift = next ?? "0";
        i += 1;
        break;
      case "--translator":
        options.translator = next ?? "auto";
        i += 1;
        break;
      case "--glossary-id":
        options.glossaryId = next ?? "";
        i += 1;
        break;
      case "--bg1":
        options.bg1 = next ?? "Auto (Not recommended)";
        i += 1;
        break;
      case "--poll-interval":
        options.pollInterval = Number(next ?? 15);
        i += 1;
        break;
      case "--max-wait":
        options.maxWait = Number(next ?? 3600);
        i += 1;
        break;
      case "--output":
        options.output = next;
        i += 1;
        break;
      case "--json":
        options.json = true;
        break;
      case "--quiet":
        options.quiet = true;
        break;
      case "--debug":
        options.debug = true;
        break;
      case "-h":
      case "--help":
        printHelp();
        process.exit(0);
        break;
      default:
        throw new Error(`Unknown argument: ${arg}`);
    }
  }

  if (!options.fileUrl) {
    throw new Error("--file-url is required");
  }
  if (!options.targetLanguage) {
    throw new Error("--target-language is required");
  }
  if (!options.voices.length) {
    throw new Error("At least one --voice is required");
  }
  if (!options.apiKey) {
    throw new Error("Set --api-key or VIDEODUBBER_API_KEY");
  }

  const speakers =
    options.speakers.length > 0
      ? options.speakers
      : options.voices.map((_, index) => `Speaker ${index + 1}`);

  if (speakers.length !== options.voices.length) {
    throw new Error("Provide the same number of --voice and --speaker values");
  }

  return {
    ...(options as CliOptions),
    speakers,
    filetype: options.filetype || inferFiletype(options.fileUrl),
  };
}

function printHelp(): void {
  console.log(`Translate video/audio with the VideoDubber API.

Usage:
  videodubber --file-url URL --target-language LANG --voice NAME [options]

Environment:
  VIDEODUBBER_API_KEY   API key (required unless --api-key)
  VIDEODUBBER_API_BASE  Override base URL (default: ${DEFAULT_BASE_URL})
`);
}

async function downloadFile(url: string, dest: string, quiet: boolean): Promise<void> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Download failed: HTTP ${response.status}`);
  }
  await mkdir(path.dirname(dest), { recursive: true });
  const buffer = Buffer.from(await response.arrayBuffer());
  await writeFile(dest, buffer);
  if (!quiet) {
    console.error(`Saved ${dest} (${(buffer.length / (1024 * 1024)).toFixed(1)} MiB)`);
  }
}

export async function runCli(argv: string[] = process.argv.slice(2)): Promise<number> {
  const args = parseArgs(argv);
  const params: TranslationJobParams = {
    fileUrl: args.fileUrl,
    targetLanguage: args.targetLanguage,
    originalLanguage: args.originalLanguage,
    numSpeakers: args.numSpeakers,
    projectName: args.projectName,
    filetype: args.filetype,
    selectedVoices: args.voices,
    speakers: args.speakers,
    audioshift: args.audioshift,
    translator: args.translator,
    glossaryId: args.glossaryId,
    bg1: args.bg1,
    voiceCloning: args.voiceCloning,
  };

  const client = new VideoDubberClient({
    apiKey: args.apiKey,
    baseUrl: args.baseUrl,
    verbose: !args.quiet,
    debug: args.debug,
  });

  try {
    if (!args.quiet) {
      console.error(
        `VideoDubber translate: ${args.originalLanguage} → ${args.targetLanguage}`,
      );
    }

    const status = await client.translateFromUrl(params, {
      pollInterval: args.pollInterval,
      maxWait: args.maxWait,
    });

    if (args.json) {
      console.log(JSON.stringify(status.raw, null, 2));
    } else if (!args.quiet) {
      console.log(`status=${status.status} pid=${status.pid}`);
      if (status.translatedMediaUrl) {
        console.log(`translated_media=${status.translatedMediaUrl}`);
      }
      if (status.availableMinutes !== undefined) {
        console.log(`available_minutes=${status.availableMinutes}`);
      }
    }

    if (args.output && status.translatedMediaUrl) {
      await downloadFile(status.translatedMediaUrl, args.output, args.quiet);
      if (!args.quiet && !args.json) {
        console.log(`saved=${args.output}`);
      }
    }

    if (!args.quiet) {
      console.error("Done.");
    }

    return status.isComplete ? 0 : 1;
  } catch (error) {
    if (error instanceof RateLimitError) {
      const suffix =
        error.retryAfter !== undefined ? ` (retry after ~${error.retryAfter}s)` : "";
      console.error(`rate limit: ${error.message}${suffix}`);
      return 1;
    }
    if (error instanceof ApiError) {
      console.error(formatApiError(error.body));
      return 1;
    }
    console.error(`error: ${error instanceof Error ? error.message : String(error)}`);
    return 1;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  runCli().then((code) => {
    process.exit(code);
  });
}
