import {
  DEFAULT_BASE_URL,
  DEFAULT_PARTNER_POLL_INTERVAL,
  DEFAULT_RATE_LIMIT_BACKOFF_BASE,
  DEFAULT_RATE_LIMIT_MAX_RETRIES,
  PARTNER_MIN_REQUEST_INTERVAL,
} from "./constants.js";
import { ApiError, JobFailedError, JobTimeoutError, RateLimitError } from "./errors.js";
import {
  CreateJobResponse,
  JobStatus,
  parseJobStatus,
  toJobPayload,
  TranslationJobParams,
  VideoDubberClientOptions,
  WaitForJobOptions,
} from "./types.js";

function sleep(seconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, seconds * 1000));
}

function joinUrl(baseUrl: string, path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return new URL(normalizedPath, `${baseUrl.replace(/\/$/, "")}/`).toString();
}

export class VideoDubberClient {
  private readonly apiKey: string;
  private readonly baseUrl: string;
  private readonly timeoutMs: number;
  private readonly rateLimitMaxRetries: number;
  private readonly rateLimitBackoffBase: number;
  private readonly partnerMinInterval: number;
  private readonly verbose: boolean;
  private readonly debug: boolean;
  private readonly fetchFn: typeof fetch;
  private lastPartnerRequestAt = 0;

  constructor(options: VideoDubberClientOptions) {
    if (!options.apiKey) {
      throw new Error("apiKey is required");
    }
    this.apiKey = options.apiKey;
    this.baseUrl = (options.baseUrl ?? DEFAULT_BASE_URL).replace(/\/$/, "");
    this.timeoutMs = options.timeoutMs ?? 120_000;
    this.rateLimitMaxRetries =
      options.rateLimitMaxRetries ?? DEFAULT_RATE_LIMIT_MAX_RETRIES;
    this.rateLimitBackoffBase =
      options.rateLimitBackoffBase ?? DEFAULT_RATE_LIMIT_BACKOFF_BASE;
    this.partnerMinInterval =
      options.partnerMinInterval ?? PARTNER_MIN_REQUEST_INTERVAL;
    this.verbose = options.verbose ?? true;
    this.debug = options.debug ?? false;
    this.fetchFn = options.fetch ?? fetch;
  }

  private progress(message: string): void {
    if (this.verbose) {
      console.error(message);
    }
  }

  private debugStatusRaw(status: JobStatus): void {
    if (!this.debug) {
      return;
    }
    this.progress("  raw status JSON:");
    for (const line of JSON.stringify(status.raw, null, 2).split("\n")) {
      this.progress(`    ${line}`);
    }
  }

  private async throttleBeforeRequest(path: string): Promise<void> {
    if (!path.includes("/api/p/")) {
      return;
    }
    const elapsed = (performance.now() - this.lastPartnerRequestAt) / 1000;
    if (elapsed < this.partnerMinInterval) {
      await sleep(this.partnerMinInterval - elapsed);
    }
  }

  private markRequestSent(path: string): void {
    if (path.includes("/api/p/")) {
      this.lastPartnerRequestAt = performance.now();
    }
  }

  private async parseRetryAfter(
    response: Response,
    attempt: number,
  ): Promise<number> {
    const header = response.headers.get("Retry-After");
    if (header) {
      const parsed = Number(header);
      if (!Number.isNaN(parsed)) {
        return Math.max(parsed, 0.5);
      }
    }
    try {
      const body = (await response.clone().json()) as Record<string, unknown>;
      for (const key of ["retry_after", "retryAfter", "Retry-After"]) {
        const value = body[key];
        if (value !== undefined) {
          return Math.max(Number(value), 0.5);
        }
      }
    } catch {
      // ignore JSON parse errors
    }
    return Math.min(this.rateLimitBackoffBase * 2 ** attempt, 120);
  }

  private async request(
    method: string,
    path: string,
    jsonBody?: Record<string, unknown>,
  ): Promise<Response> {
    const url = joinUrl(this.baseUrl, path);
    let lastResponse: Response | null = null;

    for (let attempt = 0; attempt <= this.rateLimitMaxRetries; attempt += 1) {
      await this.throttleBeforeRequest(path);
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), this.timeoutMs);

      try {
        lastResponse = await this.fetchFn(url, {
          method,
          headers: {
            "x-api-key": this.apiKey,
            ...(jsonBody ? { "Content-Type": "application/json" } : {}),
          },
          body: jsonBody ? JSON.stringify(jsonBody) : undefined,
          signal: controller.signal,
        });
      } finally {
        clearTimeout(timeout);
      }

      this.markRequestSent(path);

      if (lastResponse.status !== 429) {
        return lastResponse;
      }
      if (attempt >= this.rateLimitMaxRetries) {
        break;
      }

      const wait = await this.parseRetryAfter(lastResponse, attempt);
      this.progress(
        `Rate limited on ${method} ${path}; retrying in ${wait.toFixed(1)}s ` +
          `(attempt ${attempt + 1}/${this.rateLimitMaxRetries})`,
      );
      await sleep(wait);
    }

    if (!lastResponse) {
      throw new RateLimitError(`Rate limited on ${method} ${path}`);
    }

    throw new RateLimitError(
      `Rate limited on ${method} ${path} after ${this.rateLimitMaxRetries} retries`,
      {
        retryAfter: await this.parseRetryAfter(
          lastResponse,
          this.rateLimitMaxRetries,
        ),
        statusCode: 429,
        body: await lastResponse.text(),
      },
    );
  }

  private async raiseApiError(response: Response): Promise<never> {
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      body = await response.text();
    }
    if (response.status === 429) {
      throw new RateLimitError(`HTTP 429: ${JSON.stringify(body)}`, {
        statusCode: 429,
        body,
      });
    }
    throw new ApiError(response.status, body);
  }

  async health(): Promise<Record<string, unknown>> {
    const response = await this.fetchFn(joinUrl(this.baseUrl, "/"), {
      headers: { "x-api-key": this.apiKey },
      signal: AbortSignal.timeout(this.timeoutMs),
    });
    if (!response.ok) {
      await this.raiseApiError(response);
    }
    return (await response.json()) as Record<string, unknown>;
  }

  async createJobFromUrl(
    params: TranslationJobParams,
  ): Promise<CreateJobResponse> {
    if (!params.fileUrl) {
      throw new Error("fileUrl is required");
    }
    if (!params.selectedVoices?.length) {
      throw new Error(
        "selectedVoices is required (voice display names for target language)",
      );
    }

    this.progress("Submitting job (POST /api/p/jobs) …");
    this.progress(`  source: ${params.fileUrl}`);
    this.progress(
      `  ${params.originalLanguage ?? "unknown"} → ${params.targetLanguage}, ` +
        `voices=${JSON.stringify(params.selectedVoices)}`,
    );

    const response = await this.request("POST", "/api/p/jobs", toJobPayload(params));
    if (response.status >= 400) {
      await this.raiseApiError(response);
    }

    const data = (await response.json()) as CreateJobResponse;
    const pid = String(data.pid ?? "?");
    this.progress(
      `Job accepted — pid=${pid} (server is downloading media and starting job0)`,
    );
    return data;
  }

  async getJobStatus(pid: string): Promise<JobStatus> {
    const response = await this.request("GET", `/api/p/jobs/${pid}/status`);
    let data: Record<string, unknown> = {};
    try {
      data = (await response.json()) as Record<string, unknown>;
    } catch {
      data = {};
    }
    return parseJobStatus(pid, response.status, data);
  }

  async waitForJob(
    pid: string,
    options: WaitForJobOptions = {},
  ): Promise<JobStatus> {
    const pollInterval = Math.max(
      options.pollInterval ?? DEFAULT_PARTNER_POLL_INTERVAL,
      this.partnerMinInterval,
    );
    const maxWait = options.maxWait ?? 3600;
    const deadline = Date.now() + maxWait * 1000;
    const started = Date.now();
    let pollNum = 0;
    let last: JobStatus | null = null;

    this.progress(
      `Waiting for job ${pid} — polling every ${pollInterval.toFixed(0)}s ` +
        `(timeout ${maxWait.toFixed(0)}s)`,
    );

    while (Date.now() < deadline) {
      pollNum += 1;
      last = await this.getJobStatus(pid);
      const elapsed = (Date.now() - started) / 1000;
      const extra =
        last.availableMinutes !== undefined
          ? `, available_minutes=${last.availableMinutes.toFixed(1)}`
          : "";
      this.progress(
        `  [${elapsed.toFixed(0)}s] poll #${pollNum}: status=${last.status}${extra}`,
      );
      this.debugStatusRaw(last);

      if (last.isComplete) {
        this.progress(`Job ${pid} complete in ${elapsed.toFixed(0)}s`);
        if (last.translatedMediaUrl) {
          this.progress(`  translated_media=${last.translatedMediaUrl}`);
        }
        return last;
      }
      if (last.status === "failed") {
        throw new JobFailedError(pid, last.raw);
      }
      if (!last.isProcessing && last.httpStatus >= 500) {
        throw new Error(`Job ${pid} error: ${JSON.stringify(last.raw)}`);
      }
      await sleep(pollInterval);
    }

    throw new JobTimeoutError(pid, maxWait, last?.raw ?? null);
  }

  async translateFromUrl(
    params: TranslationJobParams,
    options: WaitForJobOptions = {},
  ): Promise<JobStatus> {
    const created = await this.createJobFromUrl(params);
    return this.waitForJob(String(created.pid), options);
  }
}
