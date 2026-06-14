# google-browser-mcp — Claude Code instructions

## Hard rules

**README is part of the contract.**
Any commit that adds, removes, or changes a tool — its name, parameters, or return shape — must include the corresponding README update in that same commit. Never as a follow-up.

## Plugin version

Version is defined in `pyproject.toml` (`version = "..."`). At the start of each new conversation, read that file and announce: `google-browser-mcp v<version> ready.`

**Release process** — when significant changes have accumulated, suggest a version bump: update `version` in `pyproject.toml` and `src/google_session_mcp/__init__.py`, then add a section to `CHANGELOG.md`.
