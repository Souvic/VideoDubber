"""Command-line interface for the VideoDubber API client."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

import requests

from videodubber.client import (
    DEFAULT_BASE_URL,
    DEFAULT_PARTNER_POLL_INTERVAL,
    ApiError,
    RateLimitError,
    TranslationJobParams,
    VideoDubberClient,
    _log,
    format_api_error,
)

CLI_EPILOG = """
Environment variables
---------------------

- VIDEODUBBER_API_KEY — API key (required unless --api-key)
- VIDEODUBBER_API_BASE — override base URL (default: https://api.videodubber.ai)

Example
-------

    export VIDEODUBBER_API_KEY="your-uuid-key"
    videodubber \\
        --file-url "https://example.com/video.mp4" \\
        --original-language English \\
        --target-language Spanish \\
        --voice Elvira \\
        --output ./translated.mp4
"""


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
        epilog=CLI_EPILOG,
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
