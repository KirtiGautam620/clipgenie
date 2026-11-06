"""Where the assistant keeps conversations and workflows: small JSON files, written atomically."""
import json
import re
import uuid
from pathlib import Path

from app import jobs
from app.config import DATA_DIR

ROOT = DATA_DIR / "assistant"
ID = re.compile(r"[0-9a-f]{12}")


class NotFound(LookupError):
    pass


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def _path(kind: str, item_id: str) -> Path:
    if not ID.fullmatch(item_id or ""):
        raise NotFound(item_id)               # only ids we made: a request can never reach other files
    folder = Path(ROOT) / kind
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{item_id}.json"


def load(kind: str, item_id: str) -> dict:
    path = _path(kind, item_id)
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        raise NotFound(item_id)


def save(kind: str, item: dict) -> None:
    jobs.write_atomic(_path(kind, item["id"]), json.dumps(item, ensure_ascii=False))


def all_of(kind: str) -> list[dict]:
    folder = Path(ROOT) / kind
    if not folder.exists():
        return []
    out = []
    for path in folder.glob("*.json"):
        try:
            out.append(json.loads(path.read_text()))
        except (OSError, ValueError):
            continue
    return out
