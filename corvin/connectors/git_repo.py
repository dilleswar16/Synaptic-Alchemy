"""
Git repository connector.

Fetches source files from Azure DevOps or GitHub repos via REST API.
Used by the code analysis toolset to read application source code during
investigation when the AI detects a code-related issue (null refs, missing
DB entries, exception stack traces, etc.).

Security:
  - PAT tokens are stored AES-256-GCM encrypted in the DB (git_token_encrypted)
  - Decrypted only at call time, never logged or persisted in plaintext
  - Only file content is read — no write/push operations
"""
from __future__ import annotations

import base64
import logging
import re
from typing import Any
from urllib.parse import quote

import httpx

from corvin.connectors.crypto import decrypt

_log = logging.getLogger(__name__)

# Max file size we'll read (128 KB) — skip binaries / large generated files
_MAX_FILE_BYTES = 128 * 1024
# Max total chars of code context injected into the LLM (avoid token blow-up)
_MAX_CODE_CONTEXT_CHARS = 30_000


class GitRepoConnector:
    """Read-only connector to fetch source files from a Git repository."""

    def __init__(
        self,
        provider: str,         # "azure_devops" or "github"
        repo_url: str,         # full repo URL
        branch: str,           # branch name (e.g. "main")
        token_encrypted: str,  # AES-256-GCM encrypted PAT
    ) -> None:
        self.provider = provider
        self.repo_url = repo_url.rstrip("/")
        self.branch = branch
        self._token = decrypt(token_encrypted)

    # ── Public API ────────────────────────────────────────────────────────────

    def get_file(self, path: str) -> str | None:
        """Fetch a single file's content by path. Returns None if not found or too large."""
        if self.provider == "azure_devops":
            return self._ado_get_file(path)
        elif self.provider == "github":
            return self._github_get_file(path)
        else:
            _log.warning("Unsupported git provider: %s", self.provider)
            return None

    def search_files(self, query: str, extensions: list[str] | None = None) -> list[dict[str, str]]:
        """
        Search for files matching a query string (class name, function name, etc.)

        Returns list of {"path": ..., "snippet": ...} dicts.
        For Azure DevOps uses the Search API; for GitHub uses code search.
        """
        if self.provider == "azure_devops":
            return self._ado_search(query, extensions)
        elif self.provider == "github":
            return self._github_search(query, extensions)
        return []

    def list_directory(self, path: str = "/") -> list[dict[str, str]]:
        """List files/folders in a directory. Returns [{"path": ..., "type": "file"|"folder"}]."""
        if self.provider == "azure_devops":
            return self._ado_list_dir(path)
        elif self.provider == "github":
            return self._github_list_dir(path)
        return []

    # ── Azure DevOps implementation ──────────────────────────────────────────

    def _ado_base_url(self) -> str:
        """Extract API base from repo URL like https://dev.azure.com/org/project/_git/repo."""
        # Pattern: https://dev.azure.com/{org}/{project}/_git/{repo}
        m = re.match(
            r"(https://dev\.azure\.com/[^/]+/[^/]+)/_git/([^/]+)",
            self.repo_url,
        )
        if not m:
            raise ValueError(f"Cannot parse Azure DevOps repo URL: {self.repo_url}")
        return m.group(1), m.group(2)

    def _ado_headers(self) -> dict[str, str]:
        b64 = base64.b64encode(f":{self._token}".encode()).decode()
        return {"Authorization": f"Basic {b64}"}

    def _ado_get_file(self, path: str) -> str | None:
        project_url, repo_name = self._ado_base_url()
        url = (
            f"{project_url}/_apis/git/repositories/{quote(repo_name)}"
            f"/items?path={quote(path)}&versionDescriptor.version={quote(self.branch)}"
            f"&api-version=7.0"
        )
        try:
            resp = httpx.get(url, headers=self._ado_headers(), timeout=15)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            content = resp.text
            if len(content) > _MAX_FILE_BYTES:
                return f"[File too large: {len(content)} bytes — skipped]"
            return content
        except Exception as exc:
            _log.warning("ADO file fetch failed for %s: %s", path, exc)
            return None

    def _ado_search(self, query: str, extensions: list[str] | None = None) -> list[dict[str, str]]:
        """Use Azure DevOps Search API (POST https://almsearch.dev.azure.com/{org}/{project}/_apis/search/codesearchresults)."""
        m = re.match(
            r"https://dev\.azure\.com/([^/]+)/([^/]+)/_git/([^/]+)",
            self.repo_url,
        )
        if not m:
            return []
        org, project, repo = m.group(1), m.group(2), m.group(3)

        search_url = f"https://almsearch.dev.azure.com/{org}/{project}/_apis/search/codesearchresults?api-version=7.0"
        filters: dict[str, list[str]] = {"Repository": [repo], "Branch": [self.branch]}
        if extensions:
            filters["CodeElement"] = extensions

        payload = {
            "searchText": query,
            "$top": 10,
            "filters": filters,
        }
        try:
            resp = httpx.post(search_url, headers=self._ado_headers(), json=payload, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            results: list[dict[str, str]] = []
            for hit in data.get("results", [])[:10]:
                path = hit.get("path", "")
                # Get snippet from matches
                matches = hit.get("matches", {}).get("content", [])
                snippet = matches[0].get("charOffset", "") if matches else ""
                results.append({"path": path, "snippet": snippet[:500]})
            return results
        except Exception as exc:
            _log.warning("ADO code search failed: %s", exc)
            return []

    def _ado_list_dir(self, path: str) -> list[dict[str, str]]:
        project_url, repo_name = self._ado_base_url()
        url = (
            f"{project_url}/_apis/git/repositories/{quote(repo_name)}"
            f"/items?scopePath={quote(path)}&recursionLevel=OneLevel"
            f"&versionDescriptor.version={quote(self.branch)}&api-version=7.0"
        )
        try:
            resp = httpx.get(url, headers=self._ado_headers(), timeout=15)
            resp.raise_for_status()
            items = resp.json().get("value", [])
            return [
                {"path": item["path"], "type": "folder" if item.get("isFolder") else "file"}
                for item in items
                if item["path"] != path  # exclude self
            ]
        except Exception as exc:
            _log.warning("ADO list dir failed for %s: %s", path, exc)
            return []

    # ── GitHub implementation ─────────────────────────────────────────────────

    def _github_owner_repo(self) -> tuple[str, str]:
        """Extract owner/repo from URL like https://github.com/owner/repo."""
        m = re.match(r"https://github\.com/([^/]+)/([^/]+?)(?:\.git)?$", self.repo_url)
        if not m:
            raise ValueError(f"Cannot parse GitHub repo URL: {self.repo_url}")
        return m.group(1), m.group(2)

    def _github_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github.v3+json",
        }

    def _github_get_file(self, path: str) -> str | None:
        owner, repo = self._github_owner_repo()
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{quote(path)}?ref={quote(self.branch)}"
        try:
            resp = httpx.get(url, headers=self._github_headers(), timeout=15)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
            if data.get("size", 0) > _MAX_FILE_BYTES:
                return f"[File too large: {data['size']} bytes — skipped]"
            content_b64 = data.get("content", "")
            return base64.b64decode(content_b64).decode("utf-8", errors="replace")
        except Exception as exc:
            _log.warning("GitHub file fetch failed for %s: %s", path, exc)
            return None

    def _github_search(self, query: str, extensions: list[str] | None = None) -> list[dict[str, str]]:
        owner, repo = self._github_owner_repo()
        q = f"{query} repo:{owner}/{repo}"
        if extensions:
            q += " " + " ".join(f"extension:{ext.lstrip('.')}" for ext in extensions)

        url = f"https://api.github.com/search/code?q={quote(q)}&per_page=10"
        try:
            resp = httpx.get(url, headers=self._github_headers(), timeout=20)
            resp.raise_for_status()
            data = resp.json()
            results: list[dict[str, str]] = []
            for item in data.get("items", [])[:10]:
                results.append({"path": item.get("path", ""), "snippet": item.get("name", "")})
            return results
        except Exception as exc:
            _log.warning("GitHub code search failed: %s", exc)
            return []

    def _github_list_dir(self, path: str) -> list[dict[str, str]]:
        owner, repo = self._github_owner_repo()
        clean_path = path.strip("/") or ""
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{quote(clean_path)}?ref={quote(self.branch)}"
        try:
            resp = httpx.get(url, headers=self._github_headers(), timeout=15)
            resp.raise_for_status()
            items = resp.json()
            if not isinstance(items, list):
                return []
            return [
                {"path": item["path"], "type": "folder" if item["type"] == "dir" else "file"}
                for item in items
            ]
        except Exception as exc:
            _log.warning("GitHub list dir failed for %s: %s", path, exc)
            return []


def get_connector_for_service(service_name: str) -> GitRepoConnector | None:
    """
    Look up the git config for a service's application and return a connector.
    Returns None if no git config is configured for the service.
    """
    from corvin.storage.db import get_session
    from corvin.storage.models import ApplicationServiceRow, ApplicationRow

    with get_session() as db:
        svc = db.query(ApplicationServiceRow).filter(
            ApplicationServiceRow.service_name == service_name
        ).first()
        if not svc:
            return None

        app = db.query(ApplicationRow).filter(ApplicationRow.id == svc.application_id).first()
        if not app or not app.git_repo_url or not app.git_token_encrypted:
            return None

        return GitRepoConnector(
            provider=app.git_provider or "azure_devops",
            repo_url=app.git_repo_url,
            branch=app.git_branch or "main",
            token_encrypted=app.git_token_encrypted,
        )
