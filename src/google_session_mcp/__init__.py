"""Browser-session Google Workspace MCP server.

Reuses a persisted Playwright Chromium profile (authenticated once via corporate
SSO) to access Google Drive, Calendar, and Gmail headless and silently —
with no OAuth2 client credentials and no GCP project.
"""

__version__ = "0.2.0"
