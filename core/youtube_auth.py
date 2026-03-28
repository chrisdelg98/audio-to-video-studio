"""YouTube OAuth helpers for Audio to Video Studio.

This module handles:
- OAuth login with Google
- Token persistence in config/youtube_token.json
- Channel identity lookup for status display
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.utils import get_app_dir, get_bundle_dir

SCOPES = ["https://www.googleapis.com/auth/youtube"]

_CATEGORY_ID_TO_NAME = {
    "1": "Film & Animation",
    "2": "Autos & Vehicles",
    "10": "Music",
    "15": "Pets & Animals",
    "17": "Sports",
    "19": "Travel & Events",
    "20": "Gaming",
    "22": "People & Blogs",
    "23": "Comedy",
    "24": "Entertainment",
    "25": "News & Politics",
    "26": "Howto & Style",
    "27": "Education",
    "28": "Science & Technology",
}
_CATEGORY_NAME_TO_ID = {v: k for k, v in _CATEGORY_ID_TO_NAME.items()}


class YouTubeAuthError(RuntimeError):
    """Raised when YouTube authentication setup or API calls fail."""


@dataclass
class YouTubeChannelInfo:
    """Basic connected channel identity used by the UI status label."""

    channel_id: str
    title: str


class YouTubeAuthService:
    """Encapsulates YouTube OAuth and authenticated API client creation."""

    def __init__(self) -> None:
        app_dir = get_app_dir()
        bundle_dir = get_bundle_dir()
        self._token_path = app_dir / "config" / "youtube_token.json"
        self._client_secret_candidates = [
            app_dir / "config" / "youtube_client_secret.json",
            app_dir.parent / "config" / "youtube_client_secret.json",
            Path.cwd() / "config" / "youtube_client_secret.json",
            bundle_dir / "config" / "youtube_client_secret.json",
        ]

    @property
    def client_secret_path(self) -> Path:
        """Return the first existing client secret path or the preferred writable path."""
        for p in self._client_secret_candidates:
            if p.is_file():
                return p
        # Preferred location for the user to drop credentials in dev and production.
        return self._client_secret_candidates[0]

    @property
    def token_path(self) -> Path:
        return self._token_path

    def _import_google_modules(self) -> dict[str, Any]:
        """Import Google modules lazily and return references.

        Import is delayed so the app can still start even if optional dependencies
        are not installed yet.
        """
        try:
            request_mod = importlib.import_module("google.auth.transport.requests")
            credentials_mod = importlib.import_module("google.oauth2.credentials")
            flow_mod = importlib.import_module("google_auth_oauthlib.flow")
            discovery_mod = importlib.import_module("googleapiclient.discovery")
        except Exception as exc:  # pragma: no cover - import errors vary by env
            raise YouTubeAuthError(
                "Faltan dependencias de YouTube API. Instala requirements.txt y reinicia la app."
            ) from exc

        return {
            "Request": request_mod.Request,
            "Credentials": credentials_mod.Credentials,
            "InstalledAppFlow": flow_mod.InstalledAppFlow,
            "build": discovery_mod.build,
        }

    def _load_credentials(self) -> Any | None:
        """Load stored credentials if present and still refreshable/valid."""
        if not self._token_path.is_file():
            return None

        gm = self._import_google_modules()
        Credentials = gm["Credentials"]
        Request = gm["Request"]

        creds = Credentials.from_authorized_user_file(str(self._token_path), SCOPES)
        if creds and creds.valid:
            return creds

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            self._save_credentials(creds)
            return creds

        return None

    def _save_credentials(self, creds: Any) -> None:
        self._token_path.parent.mkdir(parents=True, exist_ok=True)
        self._token_path.write_text(creds.to_json(), encoding="utf-8")

    def authenticate_interactive(self) -> None:
        """Run OAuth login flow and persist credentials to disk."""
        gm = self._import_google_modules()
        InstalledAppFlow = gm["InstalledAppFlow"]

        client_secret = self.client_secret_path
        if not client_secret.is_file():
            raise YouTubeAuthError(
                "No se encontro youtube_client_secret.json. "
                "Colocalo en config/ junto al ejecutable o vuelve a compilar incluyendo ese archivo."
            )

        flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), SCOPES)
        creds = flow.run_local_server(port=0, open_browser=True)
        self._save_credentials(creds)

    def has_stored_credentials(self) -> bool:
        """Return True if a token file exists (not necessarily valid)."""
        return self._token_path.is_file()

    def get_authorized_service(self) -> Any:
        """Return an authenticated YouTube API client.

        Raises:
            YouTubeAuthError: if there are no valid credentials.
        """
        creds = self._load_credentials()
        if creds is None:
            raise YouTubeAuthError(
                "No hay una sesion de YouTube activa. Pulsa 'Conectar canal'."
            )

        gm = self._import_google_modules()
        build = gm["build"]
        return build("youtube", "v3", credentials=creds, cache_discovery=False)

    def get_channel_info(self) -> YouTubeChannelInfo:
        """Return basic identity of the authenticated channel."""
        try:
            youtube = self.get_authorized_service()
            resp = youtube.channels().list(part="snippet", mine=True, maxResults=1).execute()
        except Exception as exc:
            raise YouTubeAuthError(f"No se pudo consultar el canal autenticado: {exc}") from exc

        items = resp.get("items", [])
        if not items:
            raise YouTubeAuthError("La cuenta autenticada no devolvio un canal valido.")

        item = items[0]
        snippet = item.get("snippet", {})
        return YouTubeChannelInfo(
            channel_id=item.get("id", ""),
            title=snippet.get("title", "Canal sin nombre"),
        )

    def list_private_unscheduled_drafts(self, limit: int = 200) -> list[dict[str, Any]]:
        """List private videos without publishAt (YouTube drafts ready to schedule)."""
        if limit <= 0:
            return []

        try:
            youtube = self.get_authorized_service()
        except Exception as exc:
            raise YouTubeAuthError(f"No se pudo preparar cliente YouTube: {exc}") from exc

        rows: list[dict[str, Any]] = []

        # videos.list does not support mine=True. We must traverse the channel uploads playlist.
        try:
            ch_resp = youtube.channels().list(
                part="contentDetails",
                mine=True,
                maxResults=1,
            ).execute()
            ch_items = ch_resp.get("items", [])
            if not ch_items:
                return rows
            uploads_playlist_id = (
                ch_items[0]
                .get("contentDetails", {})
                .get("relatedPlaylists", {})
                .get("uploads", "")
            )
            if not uploads_playlist_id:
                return rows
        except Exception as exc:
            raise YouTubeAuthError(f"No se pudo resolver el canal autenticado: {exc}") from exc

        page_token: str | None = None

        try:
            while len(rows) < limit:
                pl_resp = youtube.playlistItems().list(
                    part="contentDetails",
                    playlistId=uploads_playlist_id,
                    maxResults=50,
                    pageToken=page_token,
                ).execute()

                video_ids = [
                    it.get("contentDetails", {}).get("videoId", "")
                    for it in pl_resp.get("items", [])
                ]
                video_ids = [vid for vid in video_ids if vid]

                if not video_ids:
                    page_token = pl_resp.get("nextPageToken")
                    if not page_token:
                        break
                    continue

                resp = youtube.videos().list(
                    part="id,snippet,status",
                    id=",".join(video_ids),
                    maxResults=50,
                ).execute()

                for item in resp.get("items", []):
                    status = item.get("status", {})
                    snippet = item.get("snippet", {})

                    # User workflow: only private videos not yet scheduled.
                    if status.get("privacyStatus") != "private":
                        continue
                    if status.get("publishAt"):
                        continue

                    video_id = item.get("id", "")
                    category_id = str(snippet.get("categoryId", ""))
                    category_name = _CATEGORY_ID_TO_NAME.get(category_id, "Music")
                    made_for_kids = bool(status.get("madeForKids", False))

                    rows.append({
                        "video_id": video_id,
                        "path": video_id or "(sin-id)",
                        "title": snippet.get("title", "Sin titulo"),
                        "category": category_name,
                        "kids": "Si" if made_for_kids else "No",
                        "schedule": "",
                        "description": snippet.get("description", ""),
                        "tags": ", ".join(snippet.get("tags", []) or []),
                        "playlist_id": "",
                        "playlist_title": "",
                    })

                    if len(rows) >= limit:
                        break

                if len(rows) >= limit:
                    break

                page_token = pl_resp.get("nextPageToken")
                if not page_token:
                    break
        except Exception as exc:
            raise YouTubeAuthError(f"No se pudo listar borradores de YouTube: {exc}") from exc

        return rows

    def category_name_to_id(self, category_name: str) -> str:
        """Map category display name to YouTube category id (default Music=10)."""
        return _CATEGORY_NAME_TO_ID.get((category_name or "").strip(), "10")

    def update_video_metadata_and_schedule(
        self,
        *,
        video_id: str,
        title: str,
        description: str,
        tags: list[str],
        category_name: str,
        made_for_kids: bool,
        publish_at_utc: str,
    ) -> None:
        """Update video metadata and schedule publication time.

        Args:
            publish_at_utc: RFC3339 timestamp in UTC, e.g. 2026-03-27T18:00:00Z.
        """
        if not video_id.strip():
            raise YouTubeAuthError("Video sin ID; no se puede actualizar.")

        try:
            youtube = self.get_authorized_service()
            body = {
                "id": video_id,
                "snippet": {
                    "title": title,
                    "description": description,
                    "categoryId": self.category_name_to_id(category_name),
                },
                "status": {
                    "privacyStatus": "private",
                    "publishAt": publish_at_utc,
                    "selfDeclaredMadeForKids": bool(made_for_kids),
                },
            }
            if tags:
                body["snippet"]["tags"] = tags

            youtube.videos().update(part="snippet,status", body=body).execute()
        except Exception as exc:
            raise YouTubeAuthError(f"Error actualizando video {video_id}: {exc}") from exc

    def list_my_playlists(self, limit: int = 200) -> list[dict[str, str]]:
        """List playlists from authenticated channel (id + title)."""
        if limit <= 0:
            return []

        try:
            youtube = self.get_authorized_service()
        except Exception as exc:
            raise YouTubeAuthError(f"No se pudo preparar cliente YouTube: {exc}") from exc

        rows: list[dict[str, str]] = []
        page_token: str | None = None

        try:
            while len(rows) < limit:
                resp = youtube.playlists().list(
                    part="id,snippet",
                    mine=True,
                    maxResults=50,
                    pageToken=page_token,
                ).execute()

                for item in resp.get("items", []):
                    pid = str(item.get("id", "") or "").strip()
                    title = str(item.get("snippet", {}).get("title", "") or "").strip()
                    if not pid:
                        continue
                    rows.append({"id": pid, "title": title or pid})
                    if len(rows) >= limit:
                        break

                if len(rows) >= limit:
                    break

                page_token = resp.get("nextPageToken")
                if not page_token:
                    break
        except Exception as exc:
            raise YouTubeAuthError(f"No se pudo listar playlists: {exc}") from exc

        rows.sort(key=lambda x: (x.get("title", "") or "").lower())
        return rows

    def add_video_to_playlist(self, *, video_id: str, playlist_id: str) -> None:
        """Insert a video into the given playlist."""
        video_id = (video_id or "").strip()
        playlist_id = (playlist_id or "").strip()
        if not video_id:
            raise YouTubeAuthError("Video sin ID; no se puede agregar a playlist.")
        if not playlist_id:
            raise YouTubeAuthError("Playlist sin ID; no se puede agregar video.")

        try:
            youtube = self.get_authorized_service()
            youtube.playlistItems().insert(
                part="snippet",
                body={
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {
                            "kind": "youtube#video",
                            "videoId": video_id,
                        },
                    }
                },
            ).execute()
        except Exception as exc:
            raise YouTubeAuthError(
                f"Error agregando video {video_id} a playlist {playlist_id}: {exc}"
            ) from exc

    def clear_token(self) -> None:
        """Optional helper to force re-authentication."""
        if self._token_path.is_file():
            self._token_path.unlink(missing_ok=True)
