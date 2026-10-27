"""Import a YouTube video you own or have permission to use (via yt-dlp).

Deliberately limited: public YouTube links only, no cookies or logins, no playlists,
no live streams, and nothing that tries to get around any protection.
"""
from pathlib import Path
from urllib.parse import urlparse

MAX_SECONDS = 3 * 60 * 60          # refuse anything longer than 3 hours
MAX_BYTES = 4 * 1024 ** 3          # refuse anything bigger than 4 GB
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


class ImportError_(Exception):
    """A readable problem to show to the user."""


def check_url(url: str) -> str:
    """Return the cleaned URL, or raise ImportError_ if it is not a YouTube link."""
    url = url.strip()
    parts = urlparse(url)
    if parts.scheme != "https" or (parts.hostname or "").lower() not in YOUTUBE_HOSTS:
        raise ImportError_("Please paste a normal https YouTube link (youtube.com or youtu.be).")
    return url


def download(url: str, folder: Path, on_progress=None) -> dict:
    """Download to folder/source.mp4. Returns {"title", "uploader", "duration"}."""
    import yt_dlp  # imported here so the server starts fast

    def too_long(info, *, incomplete=False):
        if info.get("is_live"):
            return "Live streams are not supported."
        if (info.get("duration") or 0) > MAX_SECONDS:
            return "This video is longer than 3 hours."
        return None

    def hook(d):
        if on_progress and d.get("status") == "downloading" and d.get("total_bytes"):
            on_progress(int(100 * d["downloaded_bytes"] / d["total_bytes"]))

    opts = {
        "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/b[height<=1080]",
        "merge_output_format": "mp4",
        "outtmpl": str(folder / "source.%(ext)s"),
        "noplaylist": True,
        "match_filter": too_long,
        "max_filesize": MAX_BYTES,
        "progress_hooks": [hook],
        "quiet": True,
        "no_warnings": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except yt_dlp.utils.DownloadError as e:
        raise ImportError_(_friendly(str(e))) from e
    if not info or not (folder / "source.mp4").exists():
        raise ImportError_("The video could not be downloaded (it may be private, "
                           "age-restricted, too long, or not available as MP4).")
    return {"title": info.get("title", ""), "uploader": info.get("uploader", ""),
            "duration": info.get("duration")}


def _friendly(message: str) -> str:
    low = message.lower()
    if "private" in low:
        return "This video is private. Make it unlisted or public, or upload the MP4 file instead."
    if "sign in" in low or "age" in low:
        return "YouTube asks for a sign-in for this video. Upload the MP4 file instead."
    if "unavailable" in low or "not available" in low:
        return "This video is unavailable."
    if "live" in low:
        return "Live streams are not supported."
    return "Could not download this video: " + message.replace("ERROR: ", "")[:200]
