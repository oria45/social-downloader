# Social Downloader

Paste a TikTok, Instagram, Facebook, YouTube, or Twitter/X link, pick a quality, and it downloads straight to your computer. Nothing is kept on the server after the download completes.

## Running it

1. Clone or download this repo.
2. Double-click the launcher for your OS:
   - **Mac**: `social-downloader.command`
   - **Windows**: `social-downloader.bat`
3. Your browser opens to `http://localhost:8765` once the server is ready.

### First run vs. later runs

The first run installs everything it needs (Python, Node.js, ffmpeg if missing, plus the backend/frontend dependencies), so it can take a few minutes. Every run after that is fast — it only reinstalls dependencies if `requirements.txt` changed, and only rebuilds the frontend if its source changed.

**Windows note:** if the launcher had to install Python, Node.js, or ffmpeg, it will tell you to close the window and run it again. This is a Windows limitation, not a bug — a freshly opened terminal is needed to pick up the newly installed tools' PATH entries.

### If dependencies can't install automatically

- **Mac**: the launcher installs [Homebrew](https://brew.sh) itself if it's missing, then uses it for everything else.
- **Windows**: the launcher uses [winget](https://learn.microsoft.com/windows/package-manager/winget/), which ships with Windows 10 (1709+) and Windows 11. If `winget` isn't available, install these manually and re-run the launcher:
  - [Python](https://www.python.org/downloads/)
  - [Node.js](https://nodejs.org/)
  - [ffmpeg](https://www.gyan.dev/ffmpeg/builds/)

## Stopping it

Close the terminal window, or press `Ctrl+C` in it.
