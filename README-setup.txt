INOX Google Drive Player v1 — setup

WHAT THIS VERSION DOES
- Keeps GitHub Pages as the website host.
- Reads the movie catalogue from movies.json.
- Opens a Google Drive preview player in a clean INOX overlay.
- Does not add third-party ad scripts, Server 1/Server 2 choices, or external streaming mirrors.

IMPORTANT
Google Drive's preview player is the playback provider. Google controls supported formats, playback availability, seeking, bandwidth/quota limits and any Drive interface shown inside the player. This is not a guaranteed direct MP4 URL or a replacement for a dedicated streaming host.

SETUP
1. In your GitHub repository, replace index.html with the index.html from this package.
2. Add movies.json to the same folder as index.html (the repository root).
3. Edit movies.json. Replace the example entry with your own movie entries.
4. For each movie:
   - name: movie title
   - category: Movies, Animation, Video song, or Web_Series
   - driveUrl: Google Drive share link OR raw file ID
   - poster: public poster image URL (can be blank)
5. In Google Drive, keep General access as "Anyone with the link" and role as Viewer.
6. Commit the changes. Wait for GitHub Pages to publish, then open the website and refresh.

MOVIES.JSON FORMAT
{
  "videos": [
    {
      "name": "Movie Name",
      "category": "Movies",
      "driveUrl": "https://drive.google.com/file/d/GOOGLE_FILE_ID/view?usp=sharing",
      "poster": "https://your-public-poster-image-url"
    }
  ]
}

The example entry in the supplied movies.json is a placeholder and must be replaced. Do not put Google OAuth credentials, token.json, or private account details in this public repository.
