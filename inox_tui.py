
import asyncio
import json
import os
import shutil
import subprocess
import threading
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Header,
    Footer,
    Static,
    Button,
    Input,
    ListView,
    ListItem,
    Label,
)

# ==========================================
# INOX-TUI CONFIGURATION
# ==========================================

BASE_DIR = Path(__file__).resolve().parent
TOKEN_PATH = BASE_DIR / "token.json"
CONFIG_PATH = BASE_DIR / "config.json"

PORT = 8080
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

REQUIRED_FOLDERS = [
    "Movies",
    "Animation",
    "Video song",
    "Web_Series",
]

SERVICE = None
SERVICE_LOCK = threading.Lock()


# ==========================================
# CONFIGURATION
# ==========================================

def load_folders():
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            "config.json not found.\n"
            "Run 'py inox_drive_test.py' to configure Google Drive."
        )

    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as file:
            config = json.load(file)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            "config.json contains invalid JSON."
        ) from error

    folders = config.get("folders", {})

    if not isinstance(folders, dict):
        raise RuntimeError(
            "The 'folders' section in config.json is invalid."
        )

    for name in REQUIRED_FOLDERS:
        folder_id = folders.get(name)

        if (
            not isinstance(folder_id, str)
            or not folder_id.strip()
            or folder_id.startswith("YOUR_")
        ):
            raise RuntimeError(
                f"Google Drive folder ID missing for: {name}"
            )

    return folders


# ==========================================
# GOOGLE DRIVE CONNECTION
# ==========================================

def get_drive_service():
    global SERVICE

    with SERVICE_LOCK:
        if SERVICE is not None:
            return SERVICE

        if not TOKEN_PATH.exists():
            raise RuntimeError(
                "token.json not found. "
                "Run 'py inox_drive_test.py' first."
            )

        try:
            creds = Credentials.from_authorized_user_file(
                str(TOKEN_PATH),
                SCOPES,
            )

            if creds.expired and creds.refresh_token:
                creds.refresh(Request())

                TOKEN_PATH.write_text(
                    creds.to_json(),
                    encoding="utf-8",
                )

            if not creds.valid:
                raise RuntimeError(
                    "Google login is invalid. "
                    "Run 'py inox_drive_test.py' again."
                )

            SERVICE = build(
                "drive",
                "v3",
                credentials=creds,
                cache_discovery=False,
            )

            return SERVICE

        except Exception as error:
            raise RuntimeError(
                f"Google Drive connection failed: {error}"
            ) from error


def fetch_drive_files(category):
    service = get_drive_service()
    all_folders = load_folders()

    if category == "all":
        folders = all_folders
    else:
        if category not in all_folders:
            raise RuntimeError(
                f"Unknown category: {category}"
            )

        folders = {category: all_folders[category]}

    videos = []

    for category_name, folder_id in folders.items():
        page_token = None

        while True:
            result = service.files().list(
                q=(
                    f"'{folder_id}' in parents "
                    "and trashed = false "
                    "and mimeType contains 'video/'"
                ),
                pageSize=1000,
                orderBy="name",
                pageToken=page_token,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                fields=(
                    "nextPageToken,"
                    "files(id,name,mimeType,size,modifiedTime)"
                ),
            ).execute()

            for video in result.get("files", []):
                video["category"] = category_name
                videos.append(video)

            page_token = result.get("nextPageToken")

            if not page_token:
                break

    return videos


# ==========================================
# VLC PLAYER
# ==========================================

def find_vlc():
    vlc_path = shutil.which("vlc")

    if vlc_path:
        return vlc_path

    possible_paths = [
        r"C:\Program Files\VideoLAN\VLC\vlc.exe",
        r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
    ]

    for path in possible_paths:
        if os.path.isfile(path):
            return path

    return None


def play_video(video):
    vlc = find_vlc()

    if not vlc:
        raise RuntimeError(
            "VLC Media Player was not found. "
            "Please install VLC."
        )

    stream_url = (
        f"http://127.0.0.1:{PORT}/"
        f"?id={video['id']}"
    )

    subprocess.Popen(
        [vlc, stream_url],
        close_fds=True,
    )


# ==========================================
# VIDEO LIST ITEM
# ==========================================

class VideoItem(ListItem):

    def __init__(self, video):
        super().__init__(
            Label(
                f"{video['name']}  [{video['category']}]"
            )
        )

        self.video = video


# ==========================================
# MAIN INOX APPLICATION
# ==========================================

class InoxApp(App):

    TITLE = "INOX-TUI"
    SUB_TITLE = "Your Personal Video Library"

    CSS = """
    Screen {
        background: #101522;
    }

    #main {
        height: 1fr;
    }

    #sidebar {
        width: 27;
        border: round #43516d;
        padding: 1;
    }

    #content {
        width: 1fr;
        padding: 1;
    }

    #heading {
        height: 3;
        content-align: center middle;
        text-style: bold;
    }

    #videos {
        height: 1fr;
        border: round #43516d;
    }

    #status {
        height: 2;
        color: #8bd5ca;
        padding: 0 1;
    }

    Button {
        width: 1fr;
        margin: 0 0 1 0;
    }

    Input {
        margin-bottom: 1;
    }
    """

    current_files = []
    current_category = "all"

    def compose(self) -> ComposeResult:
        yield Header()

        with Horizontal(id="main"):

            with Vertical(id="sidebar"):
                yield Static("       INOX", id="heading")

                yield Button("Home / All Videos", id="home")
                yield Button("Movies", id="movies")
                yield Button("Animation", id="animation")
                yield Button("Video Song", id="video_song")
                yield Button("Web Series", id="web_series")

                yield Static("")
                yield Static("Select a category")

            with Vertical(id="content"):
                yield Static("WELCOME TO INOX", id="heading")

                yield Input(
                    placeholder="Search videos...",
                    id="search",
                )

                yield ListView(id="videos")

                yield Static(
                    "Connecting to Google Drive...",
                    id="status",
                )

        yield Footer()

    async def on_mount(self):
        await self.load_category("all")

    async def on_button_pressed(self, event):
        categories = {
            "home": "all",
            "movies": "Movies",
            "animation": "Animation",
            "video_song": "Video song",
            "web_series": "Web_Series",
        }

        category = categories.get(event.button.id)

        if category:
            self.query_one("#search", Input).value = ""
            await self.load_category(category)

    async def load_category(self, category):
        self.current_category = category

        status = self.query_one("#status", Static)
        status.update("Loading videos from Google Drive...")

        try:
            files = await asyncio.to_thread(
                fetch_drive_files,
                category,
            )

            self.current_files = files

            await self.display_files(files)

            category_name = (
                "All Videos" if category == "all"
                else category
            )

            status.update(
                f"{category_name}: {len(files)} videos found"
            )

        except Exception as error:
            self.current_files = []
            await self.display_files([])

            status.update(f"Error: {error}")

    async def display_files(self, files):
        video_list = self.query_one("#videos", ListView)

        await video_list.clear()

        for video in files:
            await video_list.append(VideoItem(video))

        if not files:
            await video_list.append(
                ListItem(Label("No videos found."))
            )

    async def on_input_submitted(self, event):
        if event.input.id != "search":
            return

        search_text = event.value.strip().lower()

        filtered = [
            video for video in self.current_files
            if search_text in video["name"].lower()
        ]

        await self.display_files(filtered)

        self.query_one("#status", Static).update(
            f"Search results: {len(filtered)} videos"
        )

    async def on_list_view_selected(self, event):
        if not isinstance(event.item, VideoItem):
            return

        video = event.item.video

        try:
            play_video(video)

            self.query_one("#status", Static).update(
                f"Playing: {video['name']}"
            )

        except Exception as error:
            self.query_one("#status", Static).update(
                f"Playback error: {error}"
            )


# ==========================================
# START APPLICATION
# ==========================================

if __name__ == "__main__":
    try:
        InoxApp().run()

    except KeyboardInterrupt:
        pass

    except Exception as error:
        print("\nINOX-TUI error:", error)
        input("\nPress Enter to exit...")
