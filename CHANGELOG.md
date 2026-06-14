# Changelog

## v0.2.0 — 2026-06-13

### Added
- **Calendar tools**: `calendar_list_events`, `calendar_get_event` (Meet link, attendees, phone), `calendar_create_event`, `calendar_delete_event`
- **Gmail tools**: `gmail_search`, `gmail_get_thread`, `gmail_send`, `gmail_save_draft`
- CLI subcommands: `calendar-list`, `calendar-get`, `calendar-create`, `gmail-search`, `gmail-get`, `gmail-draft`
- Stale Chrome lockfile removal on browser start (fixes exit-code-21 crash after ungraceful shutdown)
- UTF-8 stdout reconfiguration on Windows to handle non-ASCII characters in Gmail dates

### Changed
- Package renamed `drive_session_mcp` → `google_session_mcp` (git mv — history preserved)
- Entry point renamed `drive-session-mcp` → `google-browser-mcp`
- Env vars renamed `DRIVE_MCP_*` → `GOOGLE_MCP_*`
- Profile/download dirs renamed `drive-session-mcp` → `google-session-mcp`

## v0.1.0 — 2026-06-01

### Added
- Initial release: `drive_search` and `drive_fetch` MCP tools
- Persistent Playwright Chromium session (`--headless=new`) reusing a corporate SSO profile
- Drive search via `SearchItems` RPC response interception
- Drive fetch/export for Google Docs, Sheets, Slides, and binary files
- Fetch cache via `.drive_metadata.json` manifest
- CLI: `login`, `serve`, `search`, `fetch`, `selftest`
