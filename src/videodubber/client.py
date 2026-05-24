"""VideoDubber REST API client library."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urljoin

import requests

DEFAULT_BASE_URL = "https://api.videodubber.ai"
PARTNER_MIN_REQUEST_INTERVAL = 12.0  # /api/p/* → limiter.limit("5/minute")
DEFAULT_PARTNER_POLL_INTERVAL = 15.0
DEFAULT_RATE_LIMIT_MAX_RETRIES = 8
DEFAULT_RATE_LIMIT_BACKOFF_BASE = 2.0


def _log(message: str, *, quiet: bool = False) -> None:
    if not quiet:
        print(message, file=sys.stderr, flush=True)


class RateLimitError(RuntimeError):
    """Raised when rate-limit retries are exhausted."""

    def __init__(
        self,
        message: str,
        *,
        retry_after: Optional[float] = None,
        status_code: int = 429,
        body: Any = None,
    ) -> None:
        super().__init__(message)
        self.retry_after = retry_after
        self.status_code = status_code
        self.body = body


class ApiError(RuntimeError):
    """Raised for HTTP API errors with a parsed JSON body."""

    def __init__(self, status_code: int, body: Any) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"HTTP {status_code}")


@dataclass
class TranslationJobParams:
    """
    Parameters for ``POST /api/p/jobs``.

    Required
    --------
    file_url : str
        Direct HTTP/HTTPS URL to the source file (max 20 GiB on paid accounts).
    target_language : str
        Display name, e.g. ``"Spanish"``, ``"French"``.
    num_speakers : str
        ``"1"``, ``"1 (female)"``, ``"Auto Detect"``, or ``"N"`` for N speakers.
    project_name : str
        Human-readable project label.
    filetype : str
        Media extension without dot: ``"mp4"``, ``"mp3"``, etc.
        Must not be ``"false"`` (YouTube URLs are not supported).
    selectedvoices : list[str]
        Voice display names for the target language, one per speaker (e.g. ``"Elvira"``).
    speakers : list[str]
        Speaker labels aligned with ``selectedvoices``.

    Optional
    --------
    original_language : str
        Source language name or ``"unknown"`` for auto-detect.
    audioshift, translator, has_subtitle_file, subtitle_language_type,
    glossary_id, bg1, bg2, voice_cloning
    """

    file_url: str
    target_language: str
    num_speakers: str = "1"
    project_name: str = "API Project"
    filetype: str = "mp4"
    original_language: str = "unknown"
    selectedvoices: list[str] = field(default_factory=list)
    speakers: list[str] = field(default_factory=lambda: ["Speaker 1"])
    audioshift: str = "0"
    translator: str = "auto"
    has_subtitle_file: bool = False
    subtitle_language_type: str = "source"
    glossary_id: str = ""
    bg1: str = "Auto (Not recommended)"
    bg2: str = "0"
    voice_cloning: bool = False

    def to_job_payload(self) -> dict[str, Any]:
        """JSON body for ``POST /api/p/jobs``."""
        return {
            "file_url": self.file_url,
            "filetype": self.filetype,
            "OriginalLanguage": self.original_language,
            "TargetLanguage": self.target_language,
            "NumSpeakers": self.num_speakers,
            "projectname": self.project_name,
            "selectedvoices": self.selectedvoices,
            "speakers": self.speakers,
            "audioshift": self.audioshift,
            "translator": self.translator,
            "has_subtitle_file": str(self.has_subtitle_file).lower(),
            "subtitle_language_type": self.subtitle_language_type,
            "glossary_id": self.glossary_id,
            "bg1": self.bg1,
            "bg2": self.bg2,
            "voice_cloning": self.voice_cloning,
        }


@dataclass
class JobStatus:
    """Parsed status from ``GET /api/p/jobs/<pid>/status``."""

    pid: str
    status: str
    http_status: int
    raw: dict[str, Any]
    output_urls: dict[str, Any] = field(default_factory=dict)
    available_minutes: Optional[float] = None

    @property
    def is_complete(self) -> bool:
        return self.status == "complete"

    @property
    def is_processing(self) -> bool:
        return self.status in ("processing", "Need", "Taken_up")

    @property
    def translated_media_url(self) -> Optional[str]:
        if self.output_urls:
            return self.output_urls.get("translated_media")
        return None


class VideoDubberClient:
    """
    Thin wrapper around VideoDubber REST endpoints.

    Parameters
    ----------
    api_key : str
        API key sent as ``x-api-key``.
    base_url : str
        API origin, default ``https://api.videodubber.ai`` (no trailing slash).
    timeout : int
        Per-request timeout in seconds.
    partner_min_interval : float
        Minimum seconds between ``/api/p/*`` requests (server: 5/min).
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = 120,
        *,
        rate_limit_max_retries: int = DEFAULT_RATE_LIMIT_MAX_RETRIES,
        rate_limit_backoff_base: float = DEFAULT_RATE_LIMIT_BACKOFF_BASE,
        partner_min_interval: float = PARTNER_MIN_REQUEST_INTERVAL,
        verbose: bool = True,
        debug: bool = False,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.rate_limit_max_retries = rate_limit_max_retries
        self.rate_limit_backoff_base = rate_limit_backoff_base
        self.partner_min_interval = partner_min_interval
        self.verbose = verbose
        self.debug = debug
        self._last_partner_request_at = 0.0
        self._session = requests.Session()
        self._session.headers.update({"x-api-key": api_key})

    def _progress(self, message: str) -> None:
        _log(message, quiet=not self.verbose)

    def _debug_status_raw(self, status: JobStatus) -> None:
        if not self.debug:
            return
        self._progress("  raw status JSON:")
        for line in json.dumps(status.raw, indent=2, default=str).splitlines():
            self._progress(f"    {line}")

    def _url(self, path: str) -> str:
        path = path if path.startswith("/") else f"/{path}"
        return urljoin(self.base_url + "/", path.lstrip("/"))

    def _throttle_before_request(self, path: str) -> None:
        if "/api/p/" not in path:
            return
        elapsed = time.monotonic() - self._last_partner_request_at
        if elapsed < self.partner_min_interval:
            time.sleep(self.partner_min_interval - elapsed)

    def _mark_request_sent(self, path: str) -> None:
        if "/api/p/" in path:
            self._last_partner_request_at = time.monotonic()

    @staticmethod
    def _parse_retry_after(response: requests.Response, attempt: int, backoff_base: float) -> float:
        header = response.headers.get("Retry-After")
        if header:
            try:
                return max(float(header), 0.5)
            except ValueError:
                pass
        try:
            body = response.json()
            for key in ("retry_after", "retryAfter", "Retry-After"):
                if key in body:
                    return max(float(body[key]), 0.5)
        except Exception:
            pass
        return min(backoff_base * (2**attempt), 120.0)

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[dict] = None,
    ) -> requests.Response:
        url = self._url(path)
        last_response: Optional[requests.Response] = None
        for attempt in range(self.rate_limit_max_retries + 1):
            self._throttle_before_request(path)
            response = self._session.request(
                method,
                url,
                json=json_body,
                timeout=self.timeout,
            )
            self._mark_request_sent(path)
            last_response = response
            if response.status_code != 429:
                return response
            if attempt >= self.rate_limit_max_retries:
                break
            wait = self._parse_retry_after(
                response, attempt, self.rate_limit_backoff_base
            )
            self._progress(
                f"Rate limited on {method} {path}; retrying in {wait:.1f}s "
                f"(attempt {attempt + 1}/{self.rate_limit_max_retries})"
            )
            time.sleep(wait)
        assert last_response is not None
        raise RateLimitError(
            f"Rate limited on {method} {path} after {self.rate_limit_max_retries} retries",
            retry_after=self._parse_retry_after(
                last_response, self.rate_limit_max_retries, self.rate_limit_backoff_base
            ),
            status_code=429,
            body=last_response.text,
        )

    @staticmethod
    def _raise_api_error(response: requests.Response) -> None:
        try:
            body = response.json()
        except Exception:
            body = response.text
        if response.status_code == 429:
            raise RateLimitError(
                f"HTTP 429: {body}",
                status_code=429,
                body=body,
            )
        raise ApiError(response.status_code, body)

    def health(self) -> dict[str, Any]:
        """``GET /`` — service health."""
        response = self._session.get(self._url("/"), timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def create_job_from_url(self, params: TranslationJobParams) -> dict[str, Any]:
        """
        ``POST /api/p/jobs``

        Creates a project, downloads ``params.file_url`` to the server, sets voices,
        and triggers job0. Returns ``{"status": "accepted", "pid": "...", ...}``.
        """
        if not params.file_url:
            raise ValueError("file_url is required")
        if not params.selectedvoices:
            raise ValueError("selectedvoices is required (voice display names for target language)")
        self._progress("Submitting job (POST /api/p/jobs) …")
        self._progress(f"  source: {params.file_url}")
        self._progress(
            f"  {params.original_language} → {params.target_language}, "
            f"voices={params.selectedvoices}"
        )
        response = self._request(
            "POST",
            "/api/p/jobs",
            json_body=params.to_job_payload(),
        )
        if response.status_code >= 400:
            self._raise_api_error(response)
        data = response.json()
        pid = data.get("pid", "?")
        self._progress(f"Job accepted — pid={pid} (server is downloading media and starting job0)")
        return data

    def get_job_status(self, pid: str) -> JobStatus:
        """``GET /api/p/jobs/<pid>/status``"""
        response = self._request("GET", f"/api/p/jobs/{pid}/status")
        data = response.json() if response.content else {}
        return JobStatus(
            pid=pid,
            status=str(data.get("status", "unknown")),
            http_status=response.status_code,
            raw=data,
            output_urls=data.get("output_urls") or {},
            available_minutes=data.get("available_minutes"),
        )

    def wait_for_job(
        self,
        pid: str,
        *,
        poll_interval: float = DEFAULT_PARTNER_POLL_INTERVAL,
        max_wait: float = 3600.0,
    ) -> JobStatus:
        """Poll partner status until complete, failed, or timeout."""
        poll_interval = max(poll_interval, self.partner_min_interval)
        deadline = time.time() + max_wait
        last: Optional[JobStatus] = None
        started = time.time()
        poll_num = 0
        self._progress(
            f"Waiting for job {pid} — polling every {poll_interval:.0f}s "
            f"(timeout {max_wait:.0f}s)"
        )
        while time.time() < deadline:
            poll_num += 1
            last = self.get_job_status(pid)
            elapsed = time.time() - started
            extra = ""
            if last.available_minutes is not None:
                extra = f", available_minutes={last.available_minutes:.1f}"
            self._progress(f"  [{elapsed:.0f}s] poll #{poll_num}: status={last.status}{extra}")
            self._debug_status_raw(last)
            if last.is_complete:
                self._progress(f"Job {pid} complete in {elapsed:.0f}s")
                if last.translated_media_url:
                    self._progress(f"  translated_media={last.translated_media_url}")
                return last
            if last.status == "failed":
                raise RuntimeError(f"Job {pid} failed: {json.dumps(last.raw)}")
            if not last.is_processing and last.http_status >= 500:
                raise RuntimeError(f"Job {pid} error: {json.dumps(last.raw)}")
            time.sleep(poll_interval)
        raise TimeoutError(
            f"Job {pid} did not complete within {max_wait}s; last={last.raw if last else None}"
        )

    def translate_from_url(
        self,
        params: TranslationJobParams,
        *,
        poll_interval: float = DEFAULT_PARTNER_POLL_INTERVAL,
        max_wait: float = 3600.0,
    ) -> JobStatus:
        """Submit a job and poll until complete."""
        created = self.create_job_from_url(params)
        pid = str(created["pid"])
        return self.wait_for_job(
            pid,
            poll_interval=poll_interval,
            max_wait=max_wait,
        )


def format_api_error(body: Any) -> str:
    """Format a VideoDubber API error body for human-readable CLI output."""
    if not isinstance(body, dict):
        return str(body)

    lines: list[str] = []
    error = body.get("error") or body.get("alert")
    if error:
        lines.append(f"error: {error}")

    received = body.get("received")
    if received is not None:
        lines.append(f"received: {received}")

    details = body.get("details") or []
    if details:
        if lines:
            lines.append("")
        for detail in details:
            lines.append(f"  - {detail}")

    accepted_langs = body.get("accepted_target_languages")
    if accepted_langs:
        if lines:
            lines.append("")
        lines.append(f"accepted target languages ({len(accepted_langs)}):")
        lines.append("")
        for lang in accepted_langs:
            lines.append(f"  - {lang}")

    accepted_voices = body.get("accepted_voices")
    if accepted_voices:
        target_language = body.get("target_language") or "target language"
        if lines:
            lines.append("")
        lines.append(
            f"accepted voices for {target_language} ({len(accepted_voices)}):"
        )
        by_gender: dict[str, list[str]] = {}
        other: list[str] = []
        for voice in accepted_voices:
            if isinstance(voice, dict):
                name = voice.get("name", "")
                gender = str(voice.get("gender") or "").upper()
                if gender in ("MALE", "FEMALE"):
                    by_gender.setdefault(gender, []).append(name)
                else:
                    other.append(name)
            else:
                other.append(str(voice))
        for gender_key, title in (("MALE", "male voices"), ("FEMALE", "female voices")):
            names = by_gender.get(gender_key, [])
            if names:
                lines.append("")
                lines.append(f"{title}:")
                for name in names:
                    lines.append(f"  - {name}")
        if other:
            lines.append("")
            lines.append("other voices:")
            for name in other:
                lines.append(f"  - {name}")

    if len(lines) == 1 and error:
        extra = {k: v for k, v in body.items() if k not in ("error", "alert")}
        if extra:
            lines.append("")
            lines.append(json.dumps(extra, indent=2))

    return "\n".join(lines)
