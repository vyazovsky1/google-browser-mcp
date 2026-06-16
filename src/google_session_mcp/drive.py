"""Drive operations: search (page-nav + DOM extraction) and fetch.

  * search    -> navigate the headless page to drive.google.com/drive/search?q=...
                 and extract the result rows from the rendered DOM.
  * export    -> docs.google.com/.../export?format=...   (Google-native docs)
  * download  -> drive.google.com/uc?id=...&export=download   (binary files)
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from . import config
from .errors import (
    AccessDeniedError,
    DriveError,
    FileNotFoundError,
    SessionExpiredError,
)

logger = logging.getLogger(__name__)

SEARCH_URL = "https://drive.google.com/drive/search?q={q}"
GOOGLE_NATIVE: dict[str, tuple[str, str]] = {
    "application/vnd.google-apps.document": (
        "pdf",
        "https://docs.google.com/document/d/{id}/export?format={fmt}",
    ),
    "application/vnd.google-apps.spreadsheet": (
        "xlsx",
        "https://docs.google.com/spreadsheets/d/{id}/export?format={fmt}",
    ),
    "application/vnd.google-apps.presentation": (
        "pdf",
        "https://docs.google.com/presentation/d/{id}/export/{fmt}",
    ),
}

_DEFAULT_EXPORT_TMPL = GOOGLE_NATIVE["application/vnd.google-apps.document"][1]


def build_query(query: str, filters: dict[str, Any] | None = None) -> str:
    parts: list[str] = []
    if query and query.strip():
        parts.append(query.strip())
    for key, value in (filters or {}).items():
        if value is None or value == "":
            continue
        parts.append(f"{key}:{value}")
    return " ".join(parts)


def search_url(query: str, filters: dict[str, Any] | None = None) -> str:
    return SEARCH_URL.format(q=quote(build_query(query, filters)))


def looks_like_login_page(body: bytes, headers: dict) -> bool:
    ctype = (headers.get("content-type", "") or "").lower()
    if "text/html" not in ctype:
        return False
    head = body[:4000].decode("utf-8", "ignore").lower()
    return any(m in head for m in ("sign in", "accounts.google.com", "couldn't sign you in"))


DEFAULT_SEARCH_LIMIT = 20

# Ordered longest-first so "Shared folder" matches before "Folder".
_DOM_MIME_PAIRS = [
    (" Google Docs", "application/vnd.google-apps.document"),
    (" Google Sheets", "application/vnd.google-apps.spreadsheet"),
    (" Google Slides", "application/vnd.google-apps.presentation"),
    (" Google Forms", "application/vnd.google-apps.form"),
    (" Google Drawings", "application/vnd.google-apps.drawing"),
    (" Shared folder", "application/vnd.google-apps.folder"),
    (" Folder", "application/vnd.google-apps.folder"),
    (" PDF", "application/pdf"),
    (" Microsoft Word", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    (" Microsoft Excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    (" Microsoft PowerPoint", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
]

_DOM_EXTRACT_JS = (
    "() => {"
    "const PAIRS=" + json.dumps(_DOM_MIME_PAIRS) + ";"
    "const seen=new Set(),results=[];"
    "document.querySelectorAll('tr[data-id]').forEach(tr=>{"
    "  const id=tr.getAttribute('data-id');"
    "  if(seen.has(id))return; seen.add(id);"
    "  const el=tr.querySelector('[aria-label]');"
    "  const label=el?el.getAttribute('aria-label'):'';"
    "  let name=label,mime='';"
    "  for(const [s,m] of PAIRS){"
    "    const i=label.indexOf(s);"
    "    if(i>0){name=label.substring(0,i).trim();mime=m;break;}"
    "  }"
    "  results.push({id,name:name||'(untitled)',mimeType:mime});"
    "});"
    "return results;}"
)


def _dom_item_to_result(item: dict) -> dict[str, Any]:
    mime = item.get("mimeType", "")
    native = GOOGLE_NATIVE.get(mime)
    return {
        "id": item["id"],
        "name": item["name"] or "(untitled)",
        "mimeType": mime,
        "owner": None,
        "folder": None,
        "modified": None,
        "export_format": native[0] if native else None,
    }


async def search(
    session,
    query: str,
    filters: dict[str, Any] | None = None,
    *,
    limit: int = DEFAULT_SEARCH_LIMIT,
    settle_ms: int = 6000,
) -> list[dict[str, Any]]:
    limit = max(1, int(limit))
    url = search_url(query, filters)
    logger.debug("search: navigating to %s", url)
    async with session.lock:
        page = await session.page()

        await page.goto(url, wait_until="domcontentloaded")
        logger.debug("search: landed on %s (title=%r)", page.url, await page.title())
        # Check the URL *host* — not a substring of the whole URL. A login
        # redirect embeds the original drive.google.com URL in its `continue=`
        # query param, so a naive "drive.google.com in url" test is fooled.
        host = urlparse(page.url).netloc
        if host != "drive.google.com":
            raise SessionExpiredError(
                f"Drive redirected to {host}. "
                "Run `google-browser-mcp login` and retry."
            )
        await page.wait_for_timeout(settle_ms)

        seen_ids: set[str] = set()
        rows: list[dict[str, Any]] = []

        def _collect(items: list) -> None:
            for item in items:
                if item["id"] not in seen_ids:
                    seen_ids.add(item["id"])
                    rows.append(_dom_item_to_result(item))

        _collect(await page.evaluate(_DOM_EXTRACT_JS))
        logger.debug("search: %d rows after initial extract", len(rows))

        stagnant = 0
        while len(rows) < limit and stagnant < 3:
            before = len(rows)
            await page.mouse.move(640, 400)
            await page.mouse.wheel(0, 6000)
            await page.wait_for_timeout(1500)
            _collect(await page.evaluate(_DOM_EXTRACT_JS))
            logger.debug("search: %d rows after scroll (stagnant=%d)", len(rows), stagnant)
            stagnant = stagnant + 1 if len(rows) <= before else 0

        logger.debug("search: returning %d rows", min(len(rows), limit))
        return rows[:limit]


METADATA_FILENAME = ".drive_metadata.json"


def _metadata_path(dest: Path) -> Path:
    return dest / METADATA_FILENAME


def _load_metadata(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_metadata(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _cache_key(file_id: str, fmt: str | None) -> str:
    return f"{file_id}:{fmt or 'raw'}"


def _is_fresh(record: Any, dest: Path, modified: str | None) -> bool:
    if not isinstance(record, dict):
        return False
    file = record.get("file")
    if not file or not (dest / file).exists():
        return False
    if modified is not None and record.get("modified") != modified:
        return False
    return True


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(tz=timezone.utc).isoformat()


_CD_FILENAME = re.compile(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)\"?", re.IGNORECASE)


def _filename_from_headers(headers: dict, fallback: str) -> str:
    cd = headers.get("content-disposition", "") or ""
    m = _CD_FILENAME.search(cd)
    if m:
        return Path(m.group(1)).name
    return fallback


_CD_FILENAME_EXT = re.compile(r"filename\*=(?:UTF-8'')?([^;]+)", re.IGNORECASE)


def _original_name_from_headers(headers: dict) -> str | None:
    from urllib.parse import unquote
    cd = headers.get("content-disposition", "") or ""
    m = _CD_FILENAME_EXT.search(cd)
    if not m:
        return None
    return unquote(m.group(1).strip().strip('"')) or None


def _resolve_export(mime_type: str | None, export_format: str | None):
    if mime_type and mime_type in GOOGLE_NATIVE:
        default_fmt, tmpl = GOOGLE_NATIVE[mime_type]
        return True, (export_format or default_fmt), tmpl
    if export_format:
        return True, export_format, _DEFAULT_EXPORT_TMPL
    return False, None, None


FETCH_TIMEOUT_MS = 180_000


async def fetch(
    session,
    file_id: str,
    dest_dir: str | None = None,
    export_format: str | None = None,
    mime_type: str | None = None,
    modified: str | None = None,
    name: str | None = None,
    *,
    timeout_ms: int = FETCH_TIMEOUT_MS,
) -> dict[str, Any]:
    dest = Path(dest_dir).expanduser() if dest_dir else config.download_dir()
    dest.mkdir(parents=True, exist_ok=True)

    is_export, fmt, tmpl = _resolve_export(mime_type, export_format)

    if is_export:
        url = tmpl.format(id=file_id, fmt=fmt)
        fallback_name = f"{file_id}.{fmt}"
    else:
        url = f"https://drive.google.com/uc?id={file_id}&export=download"
        fallback_name = file_id

    meta_path = _metadata_path(dest)
    manifest = _load_metadata(meta_path)
    key = _cache_key(file_id, fmt)
    record = manifest.get(key)
    if _is_fresh(record, dest, modified):
        return {
            "path": str(dest / record["file"]),
            "bytes": record.get("bytes"),
            "format": record.get("format"),
            "exported": fmt is not None,
            "id": record.get("id", file_id),
            "url": record.get("url", url),
            "name": record.get("name"),
            "modified": record.get("modified"),
            "fetched_at": record.get("fetched_at"),
            "cached": True,
        }

    ctx = await session.context()
    resp = await ctx.request.get(url, timeout=timeout_ms)
    body = await resp.body()
    headers = dict(resp.headers)

    if looks_like_login_page(body, headers):
        raise SessionExpiredError(
            "Got a login page instead of file content. "
            "Run `google-browser-mcp login` and retry."
        )
    if resp.status == 404:
        raise FileNotFoundError(
            f"No Drive file with id '{file_id}' (HTTP 404)."
        )
    if resp.status == 403:
        raise AccessDeniedError(
            f"Access denied to file '{file_id}' (HTTP 403)."
        )
    if not resp.ok or len(body) <= 256:
        raise DriveError(
            f"Fetch failed for '{file_id}': HTTP {resp.status}, {len(body)} bytes."
        )

    cached_file = _filename_from_headers(headers, fallback_name)
    out = dest / cached_file
    out.write_bytes(body)

    original_name = name or _original_name_from_headers(headers)
    fetched_at = _now_iso()
    record = {
        "id": file_id,
        "url": url,
        "modified": modified,
        "fetched_at": fetched_at,
        "name": original_name,
        "file": cached_file,
        "bytes": len(body),
        "format": fmt,
    }
    manifest[key] = {k: v for k, v in record.items() if v is not None}
    _save_metadata(meta_path, manifest)

    return {
        "path": str(out),
        "bytes": len(body),
        "format": fmt,
        "exported": is_export,
        "id": file_id,
        "url": url,
        "name": original_name,
        "modified": modified,
        "fetched_at": fetched_at,
        "cached": False,
    }
