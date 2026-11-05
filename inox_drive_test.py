
import json
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

BASE_DIR = Path(__file__).resolve().parent
CREDENTIALS_PATH = BASE_DIR / "credentials.json"
TOKEN_PATH = BASE_DIR / "token.json"
CONFIG_PATH = BASE_DIR / "config.json"

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

TARGET_FOLDERS = [
    "Movies",
    "Animation",
    "Video song",
    "Web_Series"
]


def get_credentials():
    creds = None

    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(
            str(TOKEN_PATH), SCOPES
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_PATH.exists():
                raise FileNotFoundError(
                    "credentials.json not found. "
                    "Download your own OAuth Desktop credentials "
                    "from Google Cloud Console."
                )

            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_PATH), SCOPES
            )
            creds = flow.run_local_server(port=0)

        TOKEN_PATH.write_text(
            creds.to_json(), encoding="utf-8"
        )

    return creds


def find_folders(service, folder_name):
    results = []
    page_token = None

    while True:
        response = service.files().list(
            q=(
                f"name = '{folder_name}' "
                "and mimeType = 'application/vnd.google-apps.folder' "
                "and trashed = false"
            ),
            spaces="drive",
            pageSize=1000,
            pageToken=page_token,
            fields="nextPageToken,files(id,name)"
        ).execute()

        results.extend(response.get("files", []))
        page_token = response.get("nextPageToken")

        if not page_token:
            break

    return results


def choose_folder(service, folder_name):
    folders = find_folders(service, folder_name)

    if not folders:
        print(f"\nNo folder named '{folder_name}' found.")
        return None

    print(f"\nSelect your {folder_name} folder:")

    for index, folder in enumerate(folders, start=1):
        print(f"{index}. {folder['name']}")

    while True:
        choice = input("Enter folder number: ").strip()

        if choice.isdigit():
            number = int(choice)

            if 1 <= number <= len(folders):
                return folders[number - 1]["id"]

        print("Invalid selection. Try again.")


def main():
    try:
        print("\n================================")
        print("       INOX-TUI FIRST SETUP")
        print("================================\n")

        print("Connecting to Google Drive...")
        creds = get_credentials()

        service = build(
            "drive",
            "v3",
            credentials=creds,
            cache_discovery=False
        )

        print("\nGoogle Drive connected successfully!")

        folders = {}

        for name in TARGET_FOLDERS:
            folder_id = choose_folder(service, name)

            if not folder_id:
                print(
                    f"\nSetup stopped: '{name}' folder was not selected."
                )
                return

            folders[name] = folder_id

        config = {"folders": folders}

        CONFIG_PATH.write_text(
            json.dumps(config, indent=4),
            encoding="utf-8"
        )

        print("\n================================")
        print("       SETUP COMPLETED!")
        print("================================")
        print("Your config.json has been created.")
        print("You can now run: py inox_tui.py\n")

    except Exception as error:
        print("\nSetup error:", error)


if __name__ == "__main__":
    main()
