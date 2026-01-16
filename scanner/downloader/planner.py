import os
import posixpath
from typing import Dict, List

from .utils import safe_segment


def _split_scan_path(path: str):
    parts = (path or "").split("/")
    parts = [p for p in parts if p]
    cls = ""
    wafer = ""
    lot = ""
    film = ""
    date = ""
    if not parts:
        return cls, wafer, lot, film, date
    last = parts[-1]
    if len(parts) >= 4 and last.isdigit() and len(last) in (8,):
        date = last
        film = parts[-2]
        lot = parts[-3]
        wafer = parts[-4]
        cls = "/".join(parts[:-4])
    else:
        film = last
        lot = parts[-2] if len(parts) >= 2 else ""
        wafer = parts[-3] if len(parts) >= 3 else ""
        cls = "/".join(parts[:-3])
    return cls, wafer, lot, film, date


def plan_download(hit: Dict, dest_root: str, mode: str = "simple"):
    cls, wafer, lot, film, date = _split_scan_path(hit.get("path", ""))
    wafer_seg = safe_segment(wafer) or "UNKNOWN_WAFER"
    lot_seg = safe_segment(lot) or "UNKNOWN_LOT"
    film_seg = safe_segment(film) or "UNKNOWN_FILM"
    date_seg = safe_segment(date)

    # 경로 구조: wafer/film_spectrum/lot(/date) - 스캔 데이터에 _spectrum 접미사
    film_spectrum_seg = f"{film_seg}_spectrum" if film_seg else "UNKNOWN_FILM_spectrum"
    rel_parts = [wafer_seg, film_spectrum_seg, lot_seg]
    if date_seg:
        rel_parts.append(date_seg)
    dest_dir = os.path.join(dest_root, *rel_parts)

    recipe_primary = None
    recipe_paths: List[str] = []
    recipe_dest = None
    if hit.get("recipe_paths"):
        recipe_paths = hit["recipe_paths"]
        recipe_primary = hit.get("recipe_primary") or hit["recipe_paths"][0]
        recipe_display = hit.get("recipe_name") or posixpath.basename(recipe_primary.rstrip("/")) or "recipe"
        # 레시피 경로: wafer/film_filmRecipe
        recipe_base = f"{safe_segment(recipe_display)}_filmRecipe"
        recipe_dest = os.path.join(dest_root, wafer_seg, recipe_base)
    return {
        "dest_dir": dest_dir,
        "recipe_primary": recipe_primary,
        "recipe_paths": recipe_paths,
        "recipe_dest": recipe_dest,
        "wafer": wafer,
        "lot": lot,
        "film": film,
        "date": date,
    }
