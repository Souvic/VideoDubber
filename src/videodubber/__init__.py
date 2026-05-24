"""Python client for the VideoDubber video translation API."""

from videodubber._version import __version__
from videodubber.client import (
    DEFAULT_BASE_URL,
    DEFAULT_PARTNER_POLL_INTERVAL,
    ApiError,
    JobStatus,
    RateLimitError,
    TranslationJobParams,
    VideoDubberClient,
    format_api_error,
)

__all__ = [
    "__version__",
    "DEFAULT_BASE_URL",
    "DEFAULT_PARTNER_POLL_INTERVAL",
    "ApiError",
    "JobStatus",
    "RateLimitError",
    "TranslationJobParams",
    "VideoDubberClient",
    "format_api_error",
]
