
import json
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# ==========================================
# INOX-TUI FIRST-TIME SETUP
# ==========================================

BASE_DIR = Path(__file__).resolve().parent

CREDENTIALS_PATH = BASE_DIR / "credentials.json"
TOKEN_PATH = BASE_DIR / "token.json"
CONFIG_PATH = BASE_DIR / "config.json"

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly"
]

TARGET_FOLDERS = [
    "Movies",
    "Animation",
    "Video song",
    "Web_Series",
]


# ==========================================
# GOOGLE AUTHENTICATION
# ==========================================

def get_credentials():

    creds = None

    if TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(
                str(TOKEN_PATH),
                SCOPES
            )
        except Exception:
            print("Existing login could not be loaded.")
            creds = None

    if creds and creds.expired and creds.refresh_token:
        try:
            print("Refreshing Google login...")
            creds.refresh(Request())

        except Exception:
            print("Login refresh failed. Please sign in again.")
            creds = None

    if not creds or not creds.valid:

        if not CREDENTIALS_PATH.exists():
            raise FileNotFoundError(
                "credentials.json not found.\n"
                "Download your own OAuth Desktop credentials "
                "from Google Cloud Console and place them "
                "inside the INOX-TUI folder."
            )

        print("Opening Google sign-in...")

        flow = InstalledAppFlow.from_client_secrets_file(
            str(CREDENTIALS_PATH),
            SCOPES
        )

        creds = flow.run_local_server(port=0)

    TOKEN_PATH.write_text(
        creds.to_json(),
        encoding="utf-8"
    )

    return creds


# ==========================================
# GOOGLE DRIVE CONNECTION
# ==========================================

def get_drive_service():

    creds = get_credentials()

    return build(
        "drive",
        "v3",
        credentials=creds,
        cache_discovery=False
    )


# ==========================================
# FIND GOOGLE DRIVE FOLDERS
# ==========================================

def find_folders(service, folder_name):

    results = []
    page_token = None

    while True:

        response = service.files().list(
            q=(
                f"name = '{folder_name}' "
                "and mimeType = "
                "'application/vnd.google-apps.folder' "
                "and trashed = false"
            ),
            spaces="drive",
            corpora="allDrives",
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
            pageSize=1000,
            pageToken=page_token,
            orderBy="name",
            fields=(
                "nextPageToken,"
                "incompleteSearch,"
                "files(id,name,driveId,parents)"
            )
        ).execute()

        results.extend(response.get("files", []))

        if response.get("incompleteSearch"):
            print(
                "Warning: Google Drive reported an incomplete search."
            )

        page_token = response.get("nextPageToken")

        if not page_token:
            break

    return results


# ==========================================
# SELECT A FOLDER
# ==========================================

def choose_folder(service, folder_name):

    folders = find_folders(service, folder_name)

    if not folders:
        print(f"\nFolder '{folder_name}' was not found.")
        print("Check its name and Google Drive access.")
        return None

    print(f"\nSelect your {folder_name} folder:")

    for index, folder in enumerate(folders, start=1):

        location = (
            "Shared Drive"
            if folder.get("driveId")
            else "My Drive / Shared with me"
        )

        print(
            f"{index}. {folder['name']} "
            f"({location})"
        )

    while True:

        choice = input(
            "Enter folder number: "
        ).strip()

        if choice.isdigit():

            number = int(choice)

            if 1 <= number <= len(folders):
                return folders[number - 1]["id"]

        print("Invalid selection. Please try again.")


# ==========================================
# SAVE CONFIGURATION
# ==========================================

def save_configuration(folders):

    config = {
        "folders": folders
    }

    CONFIG_PATH.write_text(
        json.dumps(config, indent=4),
        encoding="utf-8"
    )

    print("\nConfiguration saved successfully.")


# ==========================================
# MAIN SETUP
# ==========================================

def main():

    print("\n================================")
    print("       INOX-TUI FIRST SETUP")
    print("================================\n")

    print("Connecting to Google Drive...")

    service = get_drive_service()

    # Verify that Google Drive can be accessed.
    service.about().get(
        fields="user"
    ).execute()

    print("\nGoogle Drive connected successfully!")

    folders = {}

    for name in TARGET_FOLDERS:

        folder_id = choose_folder(
            service,
            name
        )

        if not folder_id:

            print(
                f"\nSetup stopped: "
                f"'{name}' folder was not selected."
            )

            return

        folders[name] = folder_id

    save_configuration(folders)

    print("\n================================")
    print("       SETUP COMPLETED!")
    print("================================")

    print("\nYour personal config.json is ready.")
    print("Your Google login is saved locally.")
    print("\nNext steps:")
    print("1. Run: py drive_stream_server.py")
    print("2. Open another terminal.")
    print("3. Run: py inox_tui.py")

    print("\nEnjoy INOX-TUI!\n")


# ==========================================
# START SETUP
# ==========================================

if __name__ == "__main__":

    try:
        main()

    except KeyboardInterrupt:
        print("\nSetup cancelled.")

    except Exception as error:
        print("\nSETUP ERROR:")
        print(error)

    input("\nPress Enter to exit...")
