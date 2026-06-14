"""FastMCP stdio server exposing Drive, Calendar, and Gmail tools.

The persistent browser session is created lazily (first tool call) and torn
down on shutdown via the server lifespan, so startup is instant and a missing
login surfaces as a clear error on first use.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from . import calendar, drive, gmail
from .browser import BrowserSession


@asynccontextmanager
async def _lifespan(server: FastMCP):
    session = BrowserSession()
    try:
        yield {"session": session}
    finally:
        await session.aclose()


mcp = FastMCP("google-browser", lifespan=_lifespan)


def _session(ctx: Context) -> BrowserSession:
    return ctx.request_context.lifespan_context["session"]


# ---------------------------------------------------------------------------
# Drive tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def drive_search(
    ctx: Context,
    query: str,
    filters: dict[str, Any] | None = None,
    limit: int = drive.DEFAULT_SEARCH_LIMIT,
) -> list[dict[str, Any]]:
    """Search Google Drive and return matching file metadata.

    Args:
        query: Free-text search. May include Drive operators (e.g. ``type:pdf``).
        filters: Optional structured filters, e.g. ``{"type": "document", "owner": "me"}``.
        limit: Maximum number of results (default 20).

    Returns a list of files, each with: ``id``, ``name``, ``mimeType``, ``owner``,
    ``folder``, ``modified``, and ``export_format`` (hint for Google-native docs).
    """
    return await drive.search(_session(ctx), query, filters, limit=limit)


@mcp.tool()
async def drive_fetch(
    ctx: Context,
    file_id: str,
    dest_dir: str | None = None,
    export_format: str | None = None,
    mime_type: str | None = None,
    modified: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """Download a Drive file locally, auto-exporting Google-native docs.

    Fetches are cached in a ``.drive_metadata.json`` manifest. Re-fetching the
    same file returns the local copy if it is still on disk and the ``modified``
    date matches.

    Args:
        file_id: Drive file id (from ``drive_search``).
        dest_dir: Destination directory (defaults to configured download dir).
        export_format: Export format for Google-native docs (``txt``, ``pdf``,
            ``docx``, ``xlsx``). Use the ``export_format`` hint from search.
        mime_type: File mime type from search; helps pick the right export URL.
        modified: File ``modified`` date from search; triggers re-download when
            the cached copy's value differs.
        name: Original Drive document name (recorded in the manifest).

    Returns ``{path, bytes, format, exported, id, url, name, modified,
    fetched_at, cached}``.
    """
    return await drive.fetch(
        _session(ctx),
        file_id,
        dest_dir=dest_dir,
        export_format=export_format,
        mime_type=mime_type,
        modified=modified,
        name=name,
    )


# ---------------------------------------------------------------------------
# Calendar tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def calendar_list_events(
    ctx: Context,
    start: str,
    end: str,
) -> list[dict[str, Any]]:
    """List Google Calendar events between two dates.

    Args:
        start: Start of range as an ISO date or datetime string (e.g. ``"2026-06-01"``
            or ``"2026-06-01T00:00:00"``).
        end: End of range (same format).

    Returns a list of events, each with: ``id``, ``start``, ``end``, ``all_day``,
    ``title``, ``description``, ``has_video_conf``, and ``rsvp``.
    """
    return await calendar.list_events(_session(ctx), start, end)


@mcp.tool()
async def calendar_create_event(
    ctx: Context,
    title: str,
    start: str,
    end: str,
    description: str = "",
) -> dict[str, Any]:
    """Create a Google Calendar event.

    Args:
        title: Event title.
        start: Start time as an ISO datetime string (e.g. ``"2026-07-01T12:00:00"``).
            For all-day events, use a date-only string (``"2026-07-01"``).
        end: End time (same format as start).
        description: Optional event description / notes.

    Returns ``{status, title, start, end}`` on success.
    """
    return await calendar.create_event(_session(ctx), title, start, end, description)


@mcp.tool()
async def calendar_get_event(
    ctx: Context,
    event_id: str,
) -> dict[str, Any]:
    """Get full details for a calendar event: Meet link, attendees, description, phone.

    Args:
        event_id: The event id returned by ``calendar_list_events``
            (e.g. ``"1q199encm65hkthi6mvsl5edgm_20260615T140000Z"``).

    Returns: ``title``, ``when``, ``meet_link``, ``phone``, ``location``,
    ``organizer``, ``attendees`` (list of names), ``description``, ``raw_text``.
    """
    return await calendar.get_event(_session(ctx), event_id)


@mcp.tool()
async def calendar_delete_event(
    ctx: Context,
    event_id: str,
) -> dict[str, Any]:
    """Delete a Google Calendar event by id.

    Args:
        event_id: The event id returned by ``calendar_list_events``.

    Returns ``{status, id}`` on success.
    """
    return await calendar.delete_event(_session(ctx), event_id)


# ---------------------------------------------------------------------------
# Gmail tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def gmail_search(
    ctx: Context,
    query: str,
    max_results: int = gmail.DEFAULT_RESULT_LIMIT,
) -> list[dict[str, Any]]:
    """Search Gmail and return matching thread metadata.

    Args:
        query: Gmail search query (same operators as the Gmail search bar).
            Examples: ``"from:alice subject:report"``, ``"is:unread in:inbox"``.
        max_results: Maximum number of threads to return (default 20).

    Returns a list of threads, each with: ``id``, ``subject``, ``sender``,
    ``snippet``, ``date``, and ``unread``.
    """
    return await gmail.search(_session(ctx), query, max_results=max_results)


@mcp.tool()
async def gmail_get_thread(
    ctx: Context,
    thread_id: str,
) -> list[dict[str, Any]]:
    """Fetch all messages in a Gmail thread.

    Args:
        thread_id: The hex thread id returned by ``gmail_search``.

    Returns a list of messages, each with: ``subject``, ``from_name``,
    ``from_email``, ``date``, and ``body``.
    """
    return await gmail.get_thread(_session(ctx), thread_id)


@mcp.tool()
async def gmail_send(
    ctx: Context,
    to: str,
    subject: str,
    body: str,
) -> dict[str, Any]:
    """Compose and send an email via Gmail.

    Args:
        to: Recipient email address (one address; for multiple use comma-separated).
        subject: Email subject line.
        body: Plain-text email body.

    Returns ``{status, to, subject}`` on success.

    Warning: this sends a real email. Confirm recipients before calling.
    """
    return await gmail.send_email(_session(ctx), to, subject, body)


@mcp.tool()
async def gmail_save_draft(
    ctx: Context,
    to: str,
    subject: str,
    body: str,
) -> dict[str, Any]:
    """Save an email as a Gmail draft without sending.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Plain-text email body.

    Returns ``{status, to, subject}`` on success.
    """
    return await gmail.save_draft(_session(ctx), to, subject, body)


def run() -> None:
    mcp.run(transport="stdio")
