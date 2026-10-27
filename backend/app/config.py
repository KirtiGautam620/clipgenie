from pathlib import Path

# Project root = the clipgenie folder
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
WORK_DIR = DATA_DIR / "work"  # one sub-folder per job

# Whisper model (downloaded automatically the first time, ~500 MB)
WHISPER_MODEL = "mlx-community/whisper-small-mlx"

WORK_DIR.mkdir(parents=True, exist_ok=True)
