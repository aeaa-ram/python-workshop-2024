"""Microsoft Graph API client — PLACEHOLDER.

Handles authentication and file access for the SharePoint ingestion layer.
Nothing here performs network calls yet; every method documents the real
Graph endpoint it will use so the implementation is a fill-in exercise.

Required environment variables (see .env.example):
    MSGRAPH_TENANT_ID       Azure AD tenant
    MSGRAPH_CLIENT_ID       App registration (client credentials flow)
    MSGRAPH_CLIENT_SECRET   App secret (store in GitLab CI/CD variables,
                            never in the repo)
    SHAREPOINT_SITE_ID      Target site to watch for legacy files
    SHAREPOINT_DRIVE_ID     Document library holding engineering tools

Planned dependency: ``msal`` for token acquisition + ``requests``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


class GraphNotConfiguredError(Exception):
    pass


@dataclass
class DriveItem:
    item_id: str
    name: str
    web_url: str
    last_modified: str
    size: int


class GraphClient:
    """Thin wrapper over Microsoft Graph for SharePoint file sync."""

    GRAPH_BASE = "https://graph.microsoft.com/v1.0"

    def __init__(self) -> None:
        self.tenant_id = os.getenv("MSGRAPH_TENANT_ID", "")
        self.client_id = os.getenv("MSGRAPH_CLIENT_ID", "")
        self.client_secret = os.getenv("MSGRAPH_CLIENT_SECRET", "")
        self.site_id = os.getenv("SHAREPOINT_SITE_ID", "")
        self.drive_id = os.getenv("SHAREPOINT_DRIVE_ID", "")

    def _require_config(self) -> None:
        missing = [
            name
            for name, value in (
                ("MSGRAPH_TENANT_ID", self.tenant_id),
                ("MSGRAPH_CLIENT_ID", self.client_id),
                ("MSGRAPH_CLIENT_SECRET", self.client_secret),
            )
            if not value
        ]
        if missing:
            raise GraphNotConfiguredError(
                f"Missing environment variables: {missing}. "
                "See .env.example."
            )

    def acquire_token(self) -> str:
        """TODO: client-credentials flow via msal.

        POST https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token
        scope=https://graph.microsoft.com/.default
        """
        self._require_config()
        raise NotImplementedError("msal token acquisition not wired up yet")

    def list_drive_files(self, folder_path: str = "/") -> list[DriveItem]:
        """TODO: GET /sites/{site-id}/drives/{drive-id}/root:{path}:/children

        Filter client-side to the ingestible extensions
        (.mcdx, .xlsx, .xlsm, .csv, .py, .ipynb).
        """
        raise NotImplementedError

    def download_file(self, item_id: str, dest_path: str) -> str:
        """TODO: GET /drives/{drive-id}/items/{item-id}/content

        Downloads into the ingestion inbox, returns the local path that
        The Grinder should pick up.
        """
        raise NotImplementedError

    def get_delta(self, delta_token: str | None = None) -> dict:
        """TODO: GET /drives/{drive-id}/root/delta[?token=...]

        Incremental sync — cheaper than webhooks for bulk backfill; store
        the returned deltaLink between runs.
        """
        raise NotImplementedError
