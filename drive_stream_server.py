
import re
import threading
import requests

from pathlib import Path
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# ==========================================
# INOX STREAM SERVER CONFIGURATION
# ==========================================

PORT = 8080

BASE_DIR = Path(__file__).resolve().parent
TOKEN_PATH = BASE_DIR / "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly"
]

credentials_lock = threading.Lock()


# ==========================================
# GOOGLE AUTHENTICATION
# ==========================================

def get_credentials():

    with credentials_lock:

        if not TOKEN_PATH.exists():
            raise RuntimeError(
                "token.json not found. "
                "Run py inox_drive_test.py first."
            )

        creds = Credentials.from_authorized_user_file(
            str(TOKEN_PATH),
            SCOPES
        )

        if creds.expired and creds.refresh_token:

            creds.refresh(Request())

            TOKEN_PATH.write_text(
                creds.to_json(),
                encoding="utf-8"
            )

        if not creds.valid:
            raise RuntimeError(
                "Google login expired. "
                "Run py inox_drive_test.py again."
            )

        return creds


# ==========================================
# GOOGLE DRIVE METADATA
# ==========================================

@lru_cache(maxsize=256)
def get_metadata(file_id):

    service = build(
        "drive",
        "v3",
        credentials=get_credentials(),
        cache_discovery=False
    )

    metadata = service.files().get(
        fileId=file_id,
        supportsAllDrives=True,
        fields="id,name,size,mimeType"
    ).execute()

    return metadata


# ==========================================
# STREAMING SERVER
# ==========================================

class DriveHandler(BaseHTTPRequestHandler):

    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def get_file_id(self):

        return parse_qs(
            urlparse(self.path).query
        ).get("id", [None])[0]

    def do_HEAD(self):
        self.handle_stream(head_only=True)

    def do_GET(self):
        self.handle_stream(head_only=False)

    def handle_stream(self, head_only=False):

        file_id = self.get_file_id()

        if not file_id:
            self.send_error(
                400,
                "Missing Google Drive file ID"
            )
            return

        upstream = None

        try:

            metadata = get_metadata(file_id)

            file_size = int(metadata["size"])

            mime_type = metadata.get(
                "mimeType",
                "application/octet-stream"
            )

            headers = {
                "Authorization": (
                    f"Bearer {get_credentials().token}"
                )
            }

            range_header = self.headers.get("Range")

            start = 0
            end = file_size - 1

            if range_header:

                match = re.fullmatch(
                    r"bytes=(\d*)-(\d*)",
                    range_header.strip()
                )

                if (
                    not match
                    or (
                        not match.group(1)
                        and not match.group(2)
                    )
                    or "," in range_header
                ):
                    self.send_error(
                        400,
                        "Invalid Range header"
                    )
                    return

                first, last = match.groups()

                if first:

                    start = int(first)

                    end = (
                        int(last)
                        if last
                        else file_size - 1
                    )

                else:

                    suffix = int(last)

                    if suffix <= 0:
                        self.send_error(
                            416,
                            "Invalid Range"
                        )
                        return

                    start = max(
                        0,
                        file_size - suffix
                    )

                    end = file_size - 1

                if (
                    file_size == 0
                    or start >= file_size
                    or start > end
                ):

                    self.send_response(416)

                    self.send_header(
                        "Content-Range",
                        f"bytes */{file_size}"
                    )

                    self.send_header(
                        "Content-Length",
                        "0"
                    )

                    self.end_headers()
                    return

                end = min(
                    end,
                    file_size - 1
                )

                headers["Range"] = (
                    f"bytes={start}-{end}"
                )

            # HEAD request: return metadata without
            # downloading video content.
            if head_only:

                status = 206 if range_header else 200

                self.send_response(status)

                self.send_header(
                    "Content-Type",
                    mime_type
                )

                self.send_header(
                    "Content-Length",
                    str(end - start + 1)
                )

                self.send_header(
                    "Accept-Ranges",
                    "bytes"
                )

                if range_header:

                    self.send_header(
                        "Content-Range",
                        f"bytes {start}-{end}/{file_size}"
                    )

                self.end_headers()
                return

            # ==================================
            # PROGRESSIVE GOOGLE DRIVE STREAMING
            # ==================================

            upstream = requests.get(
                (
                    "https://www.googleapis.com/"
                    f"drive/v3/files/{file_id}"
                ),
                params={
                    "alt": "media"
                },
                headers=headers,
                stream=True,
                timeout=(20, 120)
            )

            if upstream.status_code not in (200, 206):

                self.send_error(
                    502,
                    "Google Drive streaming failed. "
                    f"HTTP {upstream.status_code}"
                )

                return

            self.send_response(
                upstream.status_code
            )

            self.send_header(
                "Content-Type",
                upstream.headers.get(
                    "Content-Type",
                    mime_type
                )
            )

            self.send_header(
                "Accept-Ranges",
                "bytes"
            )

            for header in (
                "Content-Length",
                "Content-Range"
            ):

                value = upstream.headers.get(header)

                if value:
                    self.send_header(
                        header,
                        value
                    )

            self.send_header(
                "Cache-Control",
                "no-store"
            )

            self.end_headers()

            # Send video progressively to VLC.
            for chunk in upstream.iter_content(
                chunk_size=256 * 1024
            ):

                if chunk:

                    self.wfile.write(chunk)
                    self.wfile.flush()

        except (
            BrokenPipeError,
            ConnectionResetError
        ):
            # VLC closed or restarted the stream.
            pass

        except Exception as error:

            print(
                "\nStreaming error:",
                error
            )

            # Avoid attempting a second HTTP response
            # after streaming headers have been sent.

            if not self.wfile.closed:
                try:
                    self.close_connection = True
                except Exception:
                    pass

        finally:

            if upstream is not None:
                upstream.close()


# ==========================================
# START SERVER
# ==========================================

def main():

    print("\n======================================")
    print("       INOX DRIVE STREAM SERVER")
    print("======================================\n")

    # Verify authentication before starting.
    get_credentials()

    server = ThreadingHTTPServer(
        ("127.0.0.1", PORT),
        DriveHandler
    )

    server.daemon_threads = True

    print(
        f"Streaming server: http://127.0.0.1:{PORT}"
    )

    print("Google Drive streaming enabled.")
    print("VLC seeking support enabled.")
    print("Press Ctrl+C to stop the server.\n")

    try:

        server.serve_forever()

    except KeyboardInterrupt:

        print("\nStopping INOX streaming server...")

    finally:

        server.shutdown()
        server.server_close()

        print("Server stopped.")


if __name__ == "__main__":

    try:
        main()

    except KeyboardInterrupt:
        pass

    except Exception as error:

        print("\nSERVER ERROR:")
        print(error)

        input("\nPress Enter to exit...")
