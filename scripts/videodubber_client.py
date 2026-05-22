#!/usr/bin/env python3
"""
VideoDubber API client
======================

Translate video or audio via https://api.videodubber.ai/ by submitting a
public media URL and polling for the result.

1. ``POST /api/p/jobs`` — server downloads ``file_url``, creates project, starts job0
2. ``GET /api/p/jobs/<pid>/status`` — poll until ``status`` is ``complete``

Authentication
--------------

Every API call requires::

    x-api-key: <your-api-key>

Create a key in the app under API settings, or via a logged-in session at
``GET/POST /api/p/api-key``.

Rate limits
-----------

**5 requests / minute** per ``x-api-key`` on ``/api/p/*`` endpoints. Default poll
interval is **15 s** (minimum **12 s**). The client throttles proactively and
retries HTTP 429.

Environment variables
---------------------

- ``VIDEODUBBER_API_KEY`` — API key (required unless ``--api-key``)
- ``VIDEODUBBER_API_BASE`` — override base URL (default: https://api.videodubber.ai)

Example
-------

.. code-block:: bash

    export VIDEODUBBER_API_KEY="your-uuid-key"
    python scripts/videodubber_client.py \\
        --file-url "https://example.com/video.mp4" \\
        --original-language English \\
        --target-language Spanish \\
        --voice Elvira \\
        --output ./translated.mp4
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
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


def _download_file(url: str, dest: Path, timeout: int = 300, *, quiet: bool = False) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    _log(f"Downloading translated media to {dest} …", quiet=quiet)
    downloaded = 0
    last_report_pct = -1
    with requests.get(url, stream=True, timeout=timeout) as response:
        response.raise_for_status()
        total = int(response.headers["Content-Length"]) if response.headers.get("Content-Length") else None
        with open(dest, "wb") as out:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    out.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = int(100 * downloaded / total)
                        if pct >= last_report_pct + 10 or pct == 100:
                            last_report_pct = pct
                            _log(
                                f"  Downloaded {downloaded / (1024 * 1024):.1f} / "
                                f"{total / (1024 * 1024):.1f} MiB ({pct}%)",
                                quiet=quiet,
                            )
    _log(f"Saved {dest} ({downloaded / (1024 * 1024):.1f} MiB)", quiet=quiet)


def _infer_filetype(file_url: str) -> str:
    path = file_url.split("?")[0]
    ext = Path(path).suffix.lstrip(".").lower()
    return ext or "mp4"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Translate video/audio with the VideoDubber API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--file-url",
        required=True,
        help="Public HTTP(S) URL to the source media (POST /api/p/jobs).",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("VIDEODUBBER_API_KEY", ""),
        help="API key (or set VIDEODUBBER_API_KEY).",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("VIDEODUBBER_API_BASE", DEFAULT_BASE_URL),
        help=f"API base URL (default: {DEFAULT_BASE_URL}).",
    )
    parser.add_argument(
        "--original-language",
        default="unknown",
        help='Source language name, e.g. "English", or "unknown" for auto-detect.',
    )
    parser.add_argument(
        "--target-language",
        required=True,
        help='Target language name, e.g. "Spanish", "French".',
    )
    parser.add_argument(
        "--num-speakers",
        default="1",
        help='NumSpeakers: "1", "1 (female)", "Auto Detect", or "2", "3", ...',
    )
    parser.add_argument(
        "--project-name",
        default="API Project",
        help="Project display name.",
    )
    parser.add_argument(
        "--voice",
        action="append",
        dest="voices",
        required=True,
        help='Voice display name per speaker for the target language (e.g. "Elvira"). Repeat for multiple speakers.',
    )
    parser.add_argument(
        "--speaker",
        action="append",
        dest="speakers",
        help='Speaker label per voice (default: "Speaker 1", "Speaker 2", ...).',
    )
    parser.add_argument(
        "--voice-cloning",
        action="store_true",
        help="Enable instant voice cloning.",
    )
    parser.add_argument(
        "--filetype",
        default="",
        help="File extension without dot (mp4, mp3, ...). Inferred from URL if omitted.",
    )
    parser.add_argument(
        "--audioshift",
        default="0",
        help="Audio offset in ms (string).",
    )
    parser.add_argument(
        "--translator",
        default="auto",
        help="Translator backend hint.",
    )
    parser.add_argument(
        "--glossary-id",
        default="",
        help="Optional DeepL glossary UUID.",
    )
    parser.add_argument(
        "--bg1",
        default="Auto (Not recommended)",
        help="Background sound option (bg1).",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_PARTNER_POLL_INTERVAL,
        help="Seconds between status polls (clamped to ≥12s).",
    )
    parser.add_argument(
        "--max-wait",
        type=float,
        default=3600.0,
        help="Maximum seconds to wait for job completion.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="If set, download translated media to this path when the job completes.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print final status JSON to stdout.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress messages (errors still print to stderr).",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print raw status JSON on every poll (for debugging).",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if not args.api_key:
        parser.error("Set --api-key or VIDEODUBBER_API_KEY")

    voices = args.voices
    speakers = args.speakers or [f"Speaker {i + 1}" for i in range(len(voices))]
    if len(speakers) != len(voices):
        parser.error("Provide the same number of --voice and --speaker values")

    params = TranslationJobParams(
        file_url=args.file_url,
        target_language=args.target_language,
        original_language=args.original_language,
        num_speakers=args.num_speakers,
        project_name=args.project_name,
        filetype=args.filetype or _infer_filetype(args.file_url),
        selectedvoices=voices,
        speakers=speakers,
        audioshift=args.audioshift,
        translator=args.translator,
        glossary_id=args.glossary_id,
        bg1=args.bg1,
        voice_cloning=args.voice_cloning,
    )

    client = VideoDubberClient(
        api_key=args.api_key,
        base_url=args.base_url,
        verbose=not args.quiet,
        debug=args.debug,
    )

    try:
        _log(
            f"VideoDubber translate: {args.original_language} → {args.target_language}",
            quiet=args.quiet,
        )
        status = client.translate_from_url(
            params,
            poll_interval=args.poll_interval,
            max_wait=args.max_wait,
        )

        if args.json:
            print(json.dumps(status.raw, indent=2))
        elif not args.quiet:
            print(f"status={status.status} pid={status.pid}")
            if status.translated_media_url:
                print(f"translated_media={status.translated_media_url}")
            if status.available_minutes is not None:
                print(f"available_minutes={status.available_minutes}")

        if args.output and status.translated_media_url:
            _download_file(status.translated_media_url, args.output, quiet=args.quiet)
            if not args.quiet and not args.json:
                print(f"saved={args.output}")

        if not args.quiet:
            _log("Done.", quiet=args.quiet)

        return 0 if status.is_complete else 1
    except RateLimitError as exc:
        print(
            f"rate limit: {exc}"
            + (f" (retry after ~{exc.retry_after}s)" if exc.retry_after else ""),
            file=sys.stderr,
        )
        return 1
    except ApiError as exc:
        print(format_api_error(exc.body), file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
