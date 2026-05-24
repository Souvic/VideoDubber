export class RateLimitError extends Error {
  readonly retryAfter?: number;
  readonly statusCode: number;
  readonly body: unknown;

  constructor(
    message: string,
    options: {
      retryAfter?: number;
      statusCode?: number;
      body?: unknown;
    } = {},
  ) {
    super(message);
    this.name = "RateLimitError";
    this.retryAfter = options.retryAfter;
    this.statusCode = options.statusCode ?? 429;
    this.body = options.body;
  }
}

export class ApiError extends Error {
  readonly statusCode: number;
  readonly body: unknown;

  constructor(statusCode: number, body: unknown) {
    super(`HTTP ${statusCode}`);
    this.name = "ApiError";
    this.statusCode = statusCode;
    this.body = body;
  }
}

export class JobFailedError extends Error {
  readonly pid: string;
  readonly raw: Record<string, unknown>;

  constructor(pid: string, raw: Record<string, unknown>) {
    super(`Job ${pid} failed: ${JSON.stringify(raw)}`);
    this.name = "JobFailedError";
    this.pid = pid;
    this.raw = raw;
  }
}

export class JobTimeoutError extends Error {
  readonly pid: string;
  readonly last: Record<string, unknown> | null;

  constructor(pid: string, maxWait: number, last: Record<string, unknown> | null) {
    super(`Job ${pid} did not complete within ${maxWait}s`);
    this.name = "JobTimeoutError";
    this.pid = pid;
    this.last = last;
  }
}
