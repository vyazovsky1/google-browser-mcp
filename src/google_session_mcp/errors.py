"""Shared exception types."""

from __future__ import annotations


class SessionExpiredError(RuntimeError):
    """Raised when the persisted browser session is no longer authenticated."""


class NotLoggedInError(RuntimeError):
    """Raised when no usable profile/session exists yet (login never ran)."""


class GoogleError(RuntimeError):
    """Base class for Google service operation failures."""


class DriveError(GoogleError):
    """Drive-specific operation failure."""


class CalendarError(GoogleError):
    """Calendar-specific operation failure."""


class GmailError(GoogleError):
    """Gmail-specific operation failure."""


class FileNotFoundError(DriveError):  # noqa: A001
    """Raised when a Drive file id does not exist or is inaccessible (HTTP 404)."""


class AccessDeniedError(DriveError):
    """Raised when the session may not access the file (HTTP 403)."""
