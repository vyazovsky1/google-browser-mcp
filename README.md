# google-browser-mcp

A Model Context Protocol (MCP) server that gives Claude access to **Google Drive, Calendar, and Gmail** by reusing a browser session you authenticate once — with **no OAuth2 client credentials and no GCP project**.

Works on corporate Workspace tenants that enforce Context-Aware Access: a one-time `login` opens a visible browser for the full SSO / 2SV / device-trust flow, and the persisted Playwright profile *is* the token. At runtime the server reuses that profile **headless and silent** (`--headless=new`), so no window ever appears.

## Tools

### Drive

| Tool | What it does |
|------|--------------|
| `drive_search(query, filters?, limit?)` | Search Drive; returns `id`, `name`, `mimeType`, `owner`, `folder`, `modified`, `export_format`. |
| `drive_fetch(file_id, dest_dir?, export_format?, mime_type?, modified?, name?)` | Download a file locally, auto-exporting Google-native docs (Doc→pdf/docx/txt, Sheet→xlsx, Slides→pdf). Caches each fetch; re-fetches only when the file is gone or `modified` changed. |

### Calendar

| Tool | What it does |
|------|--------------|
| `calendar_list_events(start, end)` | List events in a date range; returns `id`, `title`, `start`, `end`, `all_day`, `has_video_conf`, `rsvp`. |
| `calendar_get_event(event_id)` | Full event details: `title`, `when`, `meet_link`, `phone`, `organizer`, `attendees`, `description`. Use the `id` from `calendar_list_events`. |
| `calendar_create_event(title, start, end, description?)` | Create an event. `start`/`end` are ISO datetime strings (`"2026-07-01T14:00:00"`) or date strings for all-day events (`"2026-07-01"`). |
| `calendar_delete_event(event_id)` | Delete an event by id. |

### Gmail

| Tool | What it does |
|------|--------------|
| `gmail_search(query, max_results?)` | Search Gmail (same operators as the search bar, e.g. `from:alice is:unread`); returns `id`, `subject`, `sender`, `snippet`, `date`, `unread`. |
| `gmail_get_thread(thread_id)` | Fetch all messages in a thread; returns `subject`, `from_name`, `from_email`, `date`, `body`. Use the `id` from `gmail_search`. |
| `gmail_send(to, subject, body)` | Compose and send an email. **Sends immediately** — confirm recipients before calling. |
| `gmail_save_draft(to, subject, body)` | Save a draft without sending. |

## Setup (one time)

```powershell
cd C:\Dev\google-drive-wrap
pip install -e .
python -m playwright install chromium
```

### Authenticate once

```powershell
google-browser-mcp login
# or without the script on PATH:
python -m google_session_mcp.cli login
```

A visible Chromium opens. Complete the full corporate SSO, confirm you can see Drive / Calendar / Gmail, then press Enter in the terminal.

## Configuration

| Env var | Default | Purpose |
|---------|---------|---------|
| `GOOGLE_MCP_PROFILE` | `%LOCALAPPDATA%\google-session-mcp\profile` | Persistent browser profile (the session jar). |
| `GOOGLE_MCP_DOWNLOAD_DIR` | `%USERPROFILE%\Downloads\google-session-mcp` | Default destination for Drive fetches. |

`--profile <dir>` on any command overrides `GOOGLE_MCP_PROFILE`.

## Verify it works

```powershell
# Drive smoke test (search + fetch)
google-browser-mcp selftest --query report

# Calendar
google-browser-mcp calendar-list --start 2026-06-01 --end 2026-06-30
google-browser-mcp calendar-get --id <id-from-list>

# Gmail
google-browser-mcp gmail-search --query "in:inbox"
google-browser-mcp gmail-get --id <thread-id-from-search>
```

## Register with Claude Code

```powershell
claude mcp add google-browser -s user -- google-browser-mcp serve
# or, if the script isn't on PATH:
claude mcp add google-browser -s user -- python -m google_session_mcp.cli serve
```

To use a specific profile (e.g. a work account):

```powershell
claude mcp add google-browser -s user -- google-browser-mcp --profile C:\path\to\profile serve
```

## Register with Claude Desktop

```json
{
  "mcpServers": {
    "google-browser": {
      "command": "google-browser-mcp",
      "args": ["serve"]
    }
  }
}
```

## Notes & limitations

- **Session expiry** surfaces as a clear error; re-run `google-browser-mcp login` to refresh.
- **One profile at a time** — the CLI and the MCP server cannot share the same profile simultaneously (Chrome allows only one instance per profile). Stop the MCP server before using the CLI.
- **Single account** per server instance; use `--profile` to switch accounts.
- **Gmail send** sends real email immediately — no undo.
- **Calendar writes** (create/delete) interact with the Calendar UI via Playwright; the Save/Delete button selectors may need updating if Google changes the UI.
- The persisted profile grants access to your Google account. Keep it local and private (excluded by `.gitignore`).

## License

MIT — see [LICENSE](LICENSE).
