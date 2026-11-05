
import os
import re
import json
import threading
import requests
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from pathlib import Path
from functools import lru_cache

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

PORT = 8080
BASE_DIR = Path(__file__).resolve().parent
TOKEN_PATH = BASE_DIR / "token.json"
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

credentials_lock = threading.Lock()
metadata_cache = {}


def get_credentials():
    with credentials_lock:
        creds = Credentials.from_authorized_user_file(
            str(TOKEN_PATH), SCOPES
        )

        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")

        if not creds.valid:
            raise RuntimeError("Google login expired. Run the connection test again.")

        return creds


def get_metadata(file_id):
    if file_id not in metadata_cache:
        service = build(
            "drive", "v3",
            credentials=get_credentials(),
            cache_discovery=False
        )

        metadata_cache[file_id] = service.files().get(
            fileId=file_id,
            supportsAllDrives=True,
            fields="id,name,size,mimeType"
        ).execute()

    return metadata_cache[file_id]


class DriveHandler(BaseHTTPRequestHandler):

    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def get_file_id(self):
        return parse_qs(urlparse(self.path).query).get("id", [None])[0]

    def do_HEAD(self):
        self.handle_stream(head_only=True)

    def do_GET(self):
        self.handle_stream(head_only=False)

    def handle_stream(self, head_only=False):
        file_id = self.get_file_id()

        if not file_id:
            self.send_error(400, "Missing Google Drive file ID")
            return

        upstream = None

        try:
            metadata = get_metadata(file_id)
            file_size = int(metadata["size"])
            mime_type = metadata.get("mimeType", "video/mp4")

            headers = {
                "Authorization": f"Bearer {get_credentials().token}"
            }

            range_header = self.headers.get("Range")

            # Validate a single byte range.
            if range_header:
                match = re.fullmatch(
                    r"bytes=(\d*)-(\d*)", range_header.strip()
                )

                if not match or (not match.group(1) and not match.group(2)):
                    self.send_error(400, "Invalid Range header")
                    return

                first, last = match.groups()

                if first:
                    start = int(first)
                    end = int(last) if last else file_size - 1
                else:
                    suffix = int(last)
                    start = max(0, file_size - suffix)
                    end = file_size - 1

                if start >= file_size or start > end:
                    self.send_response(416)
                    self.send_header(
                        "Content-Range", f"bytes */{file_size}"
                    )
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return

                end = min(end, file_size - 1)
                headers["Range"] = f"bytes={start}-{end}"

            if head_only:
                self.send_response(200)
                self.send_header("Content-Type", mime_type)
                self.send_header("Content-Length", str(file_size))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                return

            # Progressive streaming: do not load the entire video into RAM.
            upstream = requests.get(
                f"https://www.googleapis.com/drive/v3/files/{file_id}",
                params={"alt": "media"},
                headers=headers,
                stream=True,
                timeout=(20, 120)
            )

            if upstream.status_code not in (200, 206):
                self.send_error(
                    502, f"Google Drive error: HTTP {upstream.status_code}"
                )
                return

            self.send_response(upstream.status_code)
            self.send_header(
                "Content-Type",
                upstream.headers.get("Content-Type", mime_type)
            )
            self.send_header("Accept-Ranges", "bytes")

            for header in ("Content-Length", "Content-Range"):
                value = upstream.headers.get(header)
                if value:
                    self.send_header(header, value)

            self.send_header("Cache-Control", "no-store")
            self.end_headers()

            # Transfer small chunks progressively to VLC.
            for chunk in upstream.iter_content(chunk_size=256 * 1024):
                if chunk:
                    self.wfile.write(chunk)
                    self.wfile.flush()

        except (BrokenPipeError, ConnectionResetError):
            pass

        except Exception as error:
            print("Streaming error:", error)

        finally:
            if upstream is not None:
                upstream.close()


def main():
    if not TOKEN_PATH.exists():
        print("token.json not found. Run inox_drive_test.py first.")
        return

    # Verify Google authentication before starting.
    get_credentials()

    server = ThreadingHTTPServer(
        ("127.0.0.1", PORT), DriveHandler
    )

    print("\n======================================")
    print("       INOX DRIVE STREAM SERVER")
    print("======================================")
    print(f"Running at: http://127.0.0.1:{PORT}")
    print("Direct Google Drive streaming enabled.")
    print("Press Ctrl+C to stop.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
