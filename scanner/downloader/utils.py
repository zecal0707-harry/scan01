import os
import re
import json
import shutil
from typing import Any


RESERVED = r'[<>:"/\\|?*]'
RESERVED_RX = re.compile(RESERVED)


def ensure_dir(path: str):
    if path:
        os.makedirs(path, exist_ok=True)


def safe_segment(seg: str) -> str:
    seg = seg.strip()
    seg = seg.replace(" ", "_")
    seg = RESERVED_RX.sub("_", seg)
    return seg[:64]  # keep it short


def save_json(path: str, obj: Any, pretty: bool = True):
    ensure_dir(os.path.dirname(path) or ".")
    with open(path, "w", encoding="utf-8") as f:
        if pretty:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        else:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def load_json(path: str, default=None):
    if not os.path.isfile(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def atomic_move(tmp_path: str, final_path: str):
    ensure_dir(os.path.dirname(final_path))
    shutil.move(tmp_path, final_path)
