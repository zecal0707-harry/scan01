"""
Policy constants & helpers (tuning separated from core logic).
"""
from typing import List

DIR_ENUM_ORDER = ("mlsd", "list", "nlst")
FILM_BACKOFF_S = (0.2, 0.6, 1.2)
DEFAULT_MAX_LOTS_EXPAND = 5000
DEFAULT_MAX_WORKERS_EXPAND = 12
DEFAULT_DIRCACHE_MAX = 8000
DEFAULT_DIRCACHE_TTL = 900
BUILD_FILMS_INDEX_IN_BOOTSTRAP = False  # set True if you want map built during bootstrap
STRICT_EXACT = True

# Film index optimization settings
FILM_INDEX_MAX_WORKERS = 32  # parallel workers for strategy.ini reading
FILM_INDEX_BATCH_SIZE = 500  # log progress every N folders
FILM_INDEX_SKIP_EXISTING = True  # skip already indexed folders in update mode

# Scan index optimization settings
SCAN_INDEX_MAX_WORKERS = 16  # parallel workers for directory traversal
SCAN_INDEX_BATCH_SIZE = 1000  # log progress every N entries
SCAN_INDEX_MAX_DEPTH = 15  # max directory depth to prevent infinite loops


def match_name(name: str, path: str, pats: List[str], *, exact: bool, regex: bool, case_sensitive: bool):
    from .utils import match_text

    return match_text(name, pats, exact=exact, regex=regex, case_sensitive=case_sensitive) or match_text(
        path, pats, exact=exact, regex=regex, case_sensitive=case_sensitive
    )


def match_lot(name: str, path: str, pats: List[str], *, exact: bool, regex: bool, case_sensitive: bool):
    from .utils import lot_match

    return lot_match(name, path, pats, exact=exact, regex=regex, case_sensitive=case_sensitive)
