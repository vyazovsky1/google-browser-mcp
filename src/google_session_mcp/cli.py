"""Command-line entry point for google-browser-mcp."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

# Windows consoles default to cp1252 which can't encode characters like the
# narrow no-break space ( ) used in Gmail date strings. Force UTF-8.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path

from . import calendar, config, drive, gmail
from .browser import BrowserSession
from .errors import GoogleError, NotLoggedInError, SessionExpiredError
from .login import run_login

def _print_drive_results(results: list[dict], limit: int = 20) -> None:
    print(f"{len(results)} result(s):")
    for r in results[:limit]:
        hint = f"  export_format={r['export_format']}" if r.get("export_format") else ""
        print(f"  - {r['name']}")
        print(f"      id={r['id']}  mime={r['mimeType']}{hint}")
        meta = [f"{k}={r[k]}" for k in ("owner", "folder", "modified") if r.get(k)]
        if meta:
            print(f"      {'  '.join(meta)}")


def _print_events(events: list[dict]) -> None:
    print(f"{len(events)} event(s):")
    for e in events:
        all_day = " (all-day)" if e.get("all_day") else ""
        vc      = " [video]" if e.get("has_video_conf") else ""
        rsvp    = f"  rsvp={e['rsvp']}" if e.get("rsvp") else ""
        print(f"  - {e['title']}{all_day}{vc}")
        print(f"      id={e.get('id')}")
        print(f"      {e.get('start', '')} -> {e.get('end', '')}{rsvp}")
        if e.get("description"):
            print(f"      {e['description'][:80]}")


def _print_threads(threads: list[dict]) -> None:
    print(f"{len(threads)} thread(s):")
    for t in threads:
        unread = " [UNREAD]" if t.get("unread") else ""
        print(f"  - {t['subject']}{unread}")
        print(f"      id={t['id']}  from={t['sender']}  date={t['date']}")
        if t.get("snippet"):
            print(f"      {t['snippet'][:80]}")


# ---------------------------------------------------------------------------
# async workers
# ---------------------------------------------------------------------------

async def _do_drive_search(profile, query, ftype, limit) -> int:
    session = BrowserSession(profile)
    try:
        filters = {"type": ftype} if ftype else None
        results = await drive.search(session, query, filters, limit=limit)
        _print_drive_results(results, limit=limit)
        return 0
    finally:
        await session.aclose()


async def _do_drive_fetch(profile, file_id, dest, fmt, mime, modified, name) -> int:
    session = BrowserSession(profile)
    try:
        info = await drive.fetch(session, file_id, dest_dir=dest,
                                 export_format=fmt, mime_type=mime,
                                 modified=modified, name=name)
        ok = Path(info["path"]).exists() and (info["bytes"] or 0) > 0
        origin = "from cache" if info.get("cached") else "downloaded"
        print(f"fetched ({origin}) -> {info}")
        print("VERIFIED: file exists on disk" if ok else "WARNING: file missing/empty")
        return 0 if ok else 1
    finally:
        await session.aclose()



async def _do_calendar_list(profile, start, end) -> int:
    session = BrowserSession(profile)
    try:
        events = await calendar.list_events(session, start, end)
        _print_events(events)
        return 0
    finally:
        await session.aclose()


async def _do_calendar_get(profile, event_id, start) -> int:
    session = BrowserSession(profile)
    try:
        result = await calendar.get_event(session, event_id, start)
        print(f"Title:       {result.get('title')}")
        print(f"When:        {result.get('when')}")
        print(f"Organizer:   {result.get('organizer')}")
        print(f"Meet link:   {result.get('meet_link')}")
        print(f"Phone:       {result.get('phone')}")
        print(f"Location:    {result.get('location')}")
        print(f"Description: {result.get('description')}")
        attendees = result.get('attendees') or []
        print(f"Attendees ({len(attendees)}): {', '.join(attendees)}")
        return 0
    finally:
        await session.aclose()


async def _do_calendar_create(profile, title, start, end, description) -> int:
    session = BrowserSession(profile)
    try:
        result = await calendar.create_event(session, title, start, end, description or "")
        print(f"Created: {result}")
        return 0
    finally:
        await session.aclose()


async def _do_gmail_search(profile, query, limit) -> int:
    session = BrowserSession(profile)
    try:
        threads = await gmail.search(session, query, max_results=limit)
        _print_threads(threads)
        return 0
    finally:
        await session.aclose()


async def _do_gmail_get(profile, thread_id) -> int:
    session = BrowserSession(profile)
    try:
        messages = await gmail.get_thread(session, thread_id)
        print(f"{len(messages)} message(s) in thread:")
        for i, m in enumerate(messages, 1):
            print(f"\n  --- Message {i} ---")
            print(f"  From: {m.get('from_name')} <{m.get('from_email')}>")
            print(f"  Date: {m.get('date')}")
            print(f"  Subject: {m.get('subject')}")
            body = (m.get("body") or "").strip()
            print(f"  Body:\n{body[:500]}")
        return 0
    finally:
        await session.aclose()


async def _do_gmail_draft(profile, to, subject, body) -> int:
    session = BrowserSession(profile)
    try:
        result = await gmail.save_draft(session, to, subject, body)
        print(f"Draft saved: {result}")
        return 0
    finally:
        await session.aclose()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="google-browser-mcp",
        description="Browser-session Google Workspace MCP server (Drive, Calendar, Gmail).",
    )
    p.add_argument("--profile", help="persistent browser profile dir (overrides GOOGLE_MCP_PROFILE)")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("login", help="open a visible browser to authenticate once")
    sub.add_parser("serve", help="run the MCP stdio server (default)")

    # Drive
    sc = sub.add_parser("drive-search", help="search Drive and print results")
    sc.add_argument("--query", required=True)
    sc.add_argument("--type", dest="ftype")
    sc.add_argument("--limit", type=int, default=drive.DEFAULT_SEARCH_LIMIT)

    fc = sub.add_parser("drive-fetch", help="download one Drive file by id")
    fc.add_argument("--id", required=True)
    fc.add_argument("--dest")
    fc.add_argument("--format", dest="fmt")
    fc.add_argument("--mime")
    fc.add_argument("--modified")
    fc.add_argument("--name")

    # Calendar
    cl = sub.add_parser("calendar-list", help="list calendar events in a date range")
    cl.add_argument("--start", required=True, help="ISO date or datetime, e.g. 2026-06-01")
    cl.add_argument("--end",   required=True, help="ISO date or datetime, e.g. 2026-06-30")

    cg = sub.add_parser("calendar-get", help="get full event details (Meet link, attendees, etc.)")
    cg.add_argument("--id", required=True, dest="event_id", help="event id from calendar-list")
    cg.add_argument("--start", default=None, help="event start datetime from calendar-list (required for one-time events)")

    cc = sub.add_parser("calendar-create", help="create a calendar event")
    cc.add_argument("--title",       required=True)
    cc.add_argument("--start",       required=True, help="ISO datetime, e.g. 2026-07-01T12:00:00")
    cc.add_argument("--end",         required=True)
    cc.add_argument("--description", default="")

    # Gmail
    gs = sub.add_parser("gmail-search", help="search Gmail and list threads")
    gs.add_argument("--query", required=True)
    gs.add_argument("--limit", type=int, default=gmail.DEFAULT_RESULT_LIMIT)

    gg = sub.add_parser("gmail-get", help="fetch messages in a thread")
    gg.add_argument("--id", required=True, dest="thread_id", help="thread id from gmail-search")

    gd = sub.add_parser("gmail-draft", help="save an email as draft")
    gd.add_argument("--to",      required=True)
    gd.add_argument("--subject", required=True)
    gd.add_argument("--body",    required=True)

    args = p.parse_args(argv)
    profile = Path(args.profile).expanduser() if args.profile else None
    cmd = args.cmd or "serve"

    if profile is not None:
        os.environ[config.ENV_PROFILE] = str(profile)

    eff = profile or config.profile_dir()

    try:
        if cmd == "login":
            return run_login(profile)
        if cmd == "drive-search":
            return asyncio.run(_do_drive_search(eff, args.query, args.ftype, args.limit))
        if cmd == "drive-fetch":
            return asyncio.run(_do_drive_fetch(eff, args.id, args.dest, args.fmt,
                                               args.mime, args.modified, args.name))
        if cmd == "calendar-list":
            return asyncio.run(_do_calendar_list(eff, args.start, args.end))
        if cmd == "calendar-get":
            return asyncio.run(_do_calendar_get(eff, args.event_id, args.start))
        if cmd == "calendar-create":
            return asyncio.run(_do_calendar_create(eff, args.title, args.start,
                                                    args.end, args.description))
        if cmd == "gmail-search":
            return asyncio.run(_do_gmail_search(eff, args.query, args.limit))
        if cmd == "gmail-get":
            return asyncio.run(_do_gmail_get(eff, args.thread_id))
        if cmd == "gmail-draft":
            return asyncio.run(_do_gmail_draft(eff, args.to, args.subject, args.body))
    except (NotLoggedInError, SessionExpiredError, GoogleError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    from .server import run
    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
