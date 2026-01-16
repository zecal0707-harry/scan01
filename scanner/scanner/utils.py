import json
import os
import posixpath
import re
import unicodedata
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Any


def ensure_dir(path: str) -> None:
    if path:
        os.makedirs(path, exist_ok=True)


def save_json(path: str, obj: Any, pretty: bool = True) -> None:
    ensure_dir(os.path.dirname(path) or ".")
    with open(path, "w", encoding="utf-8") as f:
        if pretty:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        else:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def load_json(path: str, default: Any = None) -> Any:
    if not os.path.isfile(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def join_path(base: str, name: str) -> str:
    if base in ("", "/"):
        return "/" + (name or "").strip("/")
    return posixpath.join(base, name or "")


def now_kst_iso() -> str:
    return datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="seconds")


def ts_compact() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


_WS_RX = re.compile(r"\s+", re.UNICODE)


def normalize_spaces(s: Optional[str]) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = _WS_RX.sub(" ", s).strip()
    return s


def normalize_name(s: Optional[str]) -> str:
    return normalize_spaces((s or "").lower().replace("_", " ").replace("-", " "))


def validate_regex_patterns(patterns: List[str], case_sensitive: bool = False) -> List[str]:
    """
    Validate regex patterns and return list of invalid ones.
    Returns empty list if all patterns are valid.
    """
    invalid = []
    for p in patterns:
        try:
            re.compile(p if case_sensitive else p.casefold())
        except re.error:
            invalid.append(p)
    return invalid


def match_text(
    val: Optional[str],
    patterns: List[str],
    *,
    exact: bool = False,
    regex: bool = False,
    case_sensitive: bool = False,
    normalize: bool = True,
) -> bool:
    if not patterns:
        return True
    if val is None:
        return False
    if normalize:
        val = normalize_spaces(val)
    valc = val if case_sensitive else val.casefold()
    if regex:
        for p in patterns:
            try:
                rx = re.compile(p if case_sensitive else p.casefold())
            except re.error:
                continue
            if rx.search(valc):
                return True
        return False
    normalized = []
    for p in patterns:
        if normalize:
            p = normalize_spaces(p)
        p = p if case_sensitive else p.casefold()
        normalized.append(p)
    if exact:
        return any(valc == p for p in normalized)
    return any(p in valc for p in normalized)


LOT_STEM_RX = re.compile(r"[_\-\s]")


def lot_stem(val: str) -> str:
    v = normalize_spaces(val or "")
    head = LOT_STEM_RX.split(v, maxsplit=1)[0] if v else v
    return head.upper()


def lot_match(name: str, path: str, patterns: List[str], *, exact: bool, regex: bool, case_sensitive: bool) -> bool:
    if not patterns:
        return True
    if exact and not regex:
        for p in patterns:
            if "/" in p:
                if normalize_spaces(path) == normalize_spaces(p):
                    return True
            else:
                if normalize_spaces(name if case_sensitive else name.casefold()) == normalize_spaces(
                    p if case_sensitive else p.casefold()
                ):
                    return True
        return False
    nm = normalize_spaces(name if case_sensitive else name.casefold())
    base = normalize_spaces(posixpath.basename(path) if case_sensitive else posixpath.basename(path).casefold())
    for p in patterns:
        if "/" in p:
            if normalize_spaces(p if case_sensitive else p.casefold()) == nm or normalize_spaces(
                p if case_sensitive else p.casefold()
            ) == base:
                return True
        if lot_stem(nm) == lot_stem(p) or lot_stem(base) == lot_stem(p):
            return True
    return False


DATE_RX = re.compile(r"^\d{8}$|^\d{4}[_-]\d{2}[_-]\d{2}$")


def extract_film_from_scan_path(p: str) -> str:
    """Extract film name from scan path. Structure: wafer/film/lot/date"""
    parts = (p or "").replace("\\", "/").rstrip("/").split("/")
    if not parts:
        return ""
    last = parts[-1]
    if DATE_RX.fullmatch(last):
        # 날짜가 마지막이면: lot=[-2], film=[-3]
        return parts[-3] if len(parts) >= 3 else (parts[-2] if len(parts) >= 2 else last)
    # 날짜가 없으면: lot=[-1], film=[-2]
    return parts[-2] if len(parts) >= 2 else last


def parse_scan_path(p: str) -> dict:
    """
    Parse scan data path to extract wafer, lot, film, date.

    Path structure: .../class/wafer/film/lot/date
    Example: /MTMI01_SCAN/CMP/RGZF/RGZF_M0CWCMP_PRE_CM002/RGBT017_10/20241014

    Returns: {"wafer": ..., "lot": ..., "film": ..., "date": ...}
    """
    parts = [x for x in (p or "").replace("\\", "/").split("/") if x]
    result = {"wafer": None, "lot": None, "film": None, "date": None}

    if not parts:
        return result

    # Check if last part is a date (8 digits)
    last = parts[-1]
    if DATE_RX.fullmatch(last):
        result["date"] = last
        parts = parts[:-1]

    # Structure: wafer/film/lot (from the end: lot, film, wafer)
    if len(parts) >= 1:
        result["lot"] = parts[-1]
    if len(parts) >= 2:
        result["film"] = parts[-2]
    if len(parts) >= 3:
        result["wafer"] = parts[-3]

    return result
