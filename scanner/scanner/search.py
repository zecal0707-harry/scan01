import os
import posixpath
from typing import List, Dict, Tuple

from .models import ServerConfig, SearchFilters, Hit
from .utils import (
    load_json,
    now_kst_iso,
    match_text,
    extract_film_from_scan_path,
    parse_scan_path,
    join_path,
    validate_regex_patterns,
)
from .policy import match_name, match_lot


def _prepare_filters(f: SearchFilters) -> SearchFilters:
    f.servers = [s for s in (f.servers or []) if s]
    f.roles = [r.lower() for r in (f.roles or []) if r]
    f.wafer = [w for w in (f.wafer or []) if w]
    f.lot = [l for l in (f.lot or []) if l]
    f.film = [p for p in (f.film or []) if p]
    return f


def _create_scan_hit(server: str, path: str) -> Hit:
    """Create a Hit object for scan data with parsed path components."""
    parsed = parse_scan_path(path)
    return Hit(
        server=server,
        role="scan",
        level="film",
        path=path,
        kind="scan",
        wafer=parsed.get("wafer"),
        lot=parsed.get("lot"),
        film=parsed.get("film"),
        date=parsed.get("date"),
    )


def _validate_regex_filters(filters: SearchFilters) -> List[str]:
    """Validate regex patterns in filters. Returns list of warnings."""
    warnings = []
    if not filters.regex:
        return warnings

    all_patterns = filters.wafer + filters.lot + filters.film
    invalid = validate_regex_patterns(all_patterns, filters.case_sensitive)
    for p in invalid:
        warnings.append(f"Invalid regex pattern: '{p}'")
    return warnings


def link_recipe_for_film(cfgs: List[ServerConfig], film_name: str, out_dir: str) -> Tuple[bool, str, List[str], str]:
    film_name_norm = film_name.strip()
    cand_paths: List[str] = []
    recipe_server = None
    recipe_display = film_name_norm
    for fc in cfgs:
        if fc.role != "film":
            continue
        idx = load_json(os.path.join(out_dir, "recipes", f"{fc.name}_recipes_index.json"), {}) or {}
        by_recipe = idx.get("by_recipe") or {}
        for key, paths in by_recipe.items():
            if match_text(key, [film_name_norm], exact=False, regex=False, case_sensitive=False):
                cand_paths.extend(paths or [])
                recipe_server = fc.name
                recipe_display = key
    cand_paths = list(dict.fromkeys(cand_paths))
    return (len(cand_paths) > 0, recipe_display, cand_paths, recipe_server)


def search_cache(cfgs: List[ServerConfig], filters: SearchFilters, out_dir: str, logger):
    """Search in cached index files (fast)."""
    filters = _prepare_filters(filters)
    servers = set(filters.servers or [])
    roles = set([r.lower() for r in (filters.roles or [])])
    hits: List[Dict] = []
    notices: List[str] = _validate_regex_filters(filters)
    for c in cfgs:
        if servers and c.name not in servers:
            continue
        if roles and c.role not in roles:
            continue
        if c.role == "scan":
            films_doc = load_json(os.path.join(out_dir, "required", f"{c.name}_films_index.json"), {}) or {}
            fimode = (films_doc.get("mode") or "map").lower()
            if fimode != "map":
                notices.append(f"{c.name}: films_index missing or wrong mode")
                continue
            fidx: Dict[str, List[str]] = films_doc.get("films_index")
            if fidx is None:
                fidx = films_doc # support unwrapped format
            fidx = fidx or {}
            for lot_path, film_paths in fidx.items():
                lot_name = posixpath.basename(lot_path.rstrip("/"))
                if filters.wafer:
                    # wafer filter uses parent wafer name
                    wafer_name = posixpath.basename(posixpath.dirname(lot_path.replace("\\", "/").rstrip("/")))
                    if not match_name(wafer_name, lot_path, filters.wafer, exact=filters.exact, regex=filters.regex, case_sensitive=filters.case_sensitive):
                        continue
                if filters.lot and not match_lot(
                    lot_name,
                    lot_path,
                    filters.lot,
                    exact=filters.exact,
                    regex=filters.regex,
                    case_sensitive=filters.case_sensitive,
                ):
                    continue
                fps = film_paths or []
                if filters.film:
                    fps = [
                        fp
                        for fp in fps
                        if match_name(
                            posixpath.basename(fp.replace("\\", "/").rstrip("/")),
                            fp,
                            filters.film,
                            exact=filters.exact,
                            regex=filters.regex,
                            case_sensitive=filters.case_sensitive,
                        )
                    ]
                for fp in fps:
                    hit = _create_scan_hit(c.name, fp)
                    if filters.link_recipe:
                        film_for_link = extract_film_from_scan_path(fp)
                        linked, rname, rpaths, rsv = link_recipe_for_film(cfgs, film_for_link, out_dir)
                        hit.recipe_linked = bool(linked)
                        hit.recipe_name = rname
                        hit.recipe_paths = rpaths
                        hit.recipe_primary = rpaths[0] if rpaths else None
                        hit.recipe_server = rsv
                    hits.append(hit.to_dict())
        else:
            if not filters.film:
                continue
            idx = load_json(os.path.join(out_dir, "recipes", f"{c.name}_recipes_index.json"), {}) or {}
            by_recipe = idx.get("by_recipe") or {}
            for key, paths in by_recipe.items():
                if match_text(key, filters.film, exact=filters.exact, regex=filters.regex, case_sensitive=filters.case_sensitive):
                    for p in (paths or []):
                        hits.append(
                            Hit(server=c.name, role="film", level="folder", path=p, recipe_name=key, kind="recipe").to_dict()
                        )
    out_kind = _decide_result_kind(filters)
    out = {"mode": "cache", "kind": out_kind, "hits": hits, "count": len(hits), "generated_at": now_kst_iso()}
    if notices:
        out["notices"] = notices
    logger.info(f"[search-cache] kind={out_kind} hits={len(hits)}")
    return out


# Backward compatibility alias (DEPRECATED: use search_cache instead)
def search_local(cfgs: List[ServerConfig], filters: SearchFilters, out_dir: str, logger):
    """DEPRECATED: Use search_cache() instead. This searches in index files, not local filesystem."""
    return search_cache(cfgs, filters, out_dir, logger)


def search_direct(cfgs: List[ServerConfig], filters: SearchFilters, out_dir: str, logger):
    """Search by directly traversing server directories (slower but up-to-date).

    Optimization: Uses cached films_index paths first, only traverses if needed.
    """
    filters = _prepare_filters(filters)
    servers = set(filters.servers or [])
    roles = set([r.lower() for r in (filters.roles or [])])
    hits: List[Dict] = []
    notices: List[str] = _validate_regex_filters(filters)
    for c in cfgs:

        if servers and c.name not in servers:
            continue
        if roles and c.role not in roles:
            continue
        if c.role == "scan":
            lots_doc = load_json(os.path.join(out_dir, "required", f"{c.name}_lots_index.json"), {}) or {}
            idx = lots_doc.get("lots_index")
            if idx is None:
                idx = lots_doc # support unwrapped format
            idx = idx or {}
            
            candidate_paths: List[str] = []
            if filters.lot:
                for lot_name, plist in idx.items():
                    if not match_lot(
                        lot_name,
                        "",
                        filters.lot,
                        exact=filters.exact,
                        regex=filters.regex,
                        case_sensitive=filters.case_sensitive,
                    ):
                        continue
                    
                    for p in plist:
                        if filters.wafer:
                            # Robust extraction
                            p_norm = p.replace("\\", "/")
                            wafer_name = posixpath.basename(posixpath.dirname(p_norm.rstrip("/")))

                            if not match_name(
                                wafer_name,
                                p,
                                filters.wafer,
                                exact=filters.exact,
                                regex=filters.regex,
                                case_sensitive=filters.case_sensitive,
                            ):
                                continue

                        if filters.film: # Check if this lot actually contains the requested film
                            films_doc = load_json(os.path.join(out_dir, "required", f"{c.name}_films_index.json"), {}) or {}
                            fidx = films_doc.get("films_index")
                            if fidx is None:
                                fidx = films_doc # support unwrapped format
                            fidx = fidx or {}
                            lot_films = fidx.get(p) or []
                            
                            match_found = False
                            for fp in lot_films:
                                if match_name(
                                    posixpath.basename(fp.replace("\\", "/").rstrip("/")),
                                    fp,
                                    filters.film,
                                    exact=filters.exact,
                                    regex=filters.regex,
                                    case_sensitive=filters.case_sensitive,
                                ):
                                    match_found = True
                                    break
                            if not match_found:
                                continue

                        candidate_paths.append(p)
            elif filters.wafer:
                for plist in idx.values():
                    for p in plist:
                        wafer_name = posixpath.basename(posixpath.dirname(p.replace("\\", "/").rstrip("/")))
                        if match_name(
                            wafer_name,
                            p,
                            filters.wafer,
                            exact=filters.exact,
                            regex=filters.regex,
                            case_sensitive=filters.case_sensitive,
                        ):
                            candidate_paths.append(p)
            elif filters.film:
                # Fallback: if searching by film only, we must consult films_index to find relevant lots
                films_doc = load_json(os.path.join(out_dir, "required", f"{c.name}_films_index.json"), {}) or {}
                fidx = films_doc.get("films_index")
                if fidx is None:
                    fidx = films_doc
                fidx = fidx or {}
                for lot_path, film_paths in fidx.items():
                    # check if any film in this lot matches
                    match_found = False
                    for fp in (film_paths or []):
                        if match_name(
                            posixpath.basename(fp.rstrip("/")),
                            fp,
                            filters.film,
                            exact=filters.exact,
                            regex=filters.regex,
                            case_sensitive=filters.case_sensitive,
                        ):
                            match_found = True
                            break
                    if match_found:
                        candidate_paths.append(lot_path)
            else:
                candidate_paths = []
            candidate_paths = sorted(set(candidate_paths))
            if not candidate_paths:
                continue
            if c.use_local_fs:
                adapter_root = c.root
                for lot_path in candidate_paths:
                    real_path = os.path.join(adapter_root, lot_path.lstrip("/"))

                    if not os.path.isdir(real_path):
                        continue
                    for film in sorted(os.listdir(real_path)):
                        film_path = os.path.join(real_path, film)
                        if not os.path.isdir(film_path):
                            continue
                        for date in sorted(os.listdir(film_path)):
                            date_path = os.path.join(film_path, date)
                            if os.path.isdir(date_path):
                                fp = join_path(lot_path, join_path(film, date))
                                if filters.film and not match_name(
                                    film, fp, filters.film, exact=filters.exact, regex=filters.regex, case_sensitive=filters.case_sensitive
                                ):
                                    continue
                                hit = _create_scan_hit(c.name, fp)
                                if filters.link_recipe:
                                    film_for_link = extract_film_from_scan_path(fp)
                                    linked, rname, rpaths, rsv = link_recipe_for_film(cfgs, film_for_link, out_dir)
                                    hit.recipe_linked = bool(linked)
                                    hit.recipe_name = rname
                                    hit.recipe_paths = rpaths
                                    hit.recipe_primary = rpaths[0] if rpaths else None
                                    hit.recipe_server = rsv
                                hits.append(hit.to_dict())
            else:
                from .ftp import ManagedFTPPool, list_dirs
                from .ftp import RobustFTP

                pool = ManagedFTPPool(
                    lambda: RobustFTP(
                        c.ip,
                        c.user,
                        c.password,
                        port=c.port,
                        timeout=c.timeout,
                        op_deadline=c.op_deadline,
                        logger=logger,
                    ),
                    size=max(2, c.pool_size),
                )
                for lot_path in candidate_paths:
                    conn = pool.acquire()
                    try:
                        film_dirs = list_dirs(conn, lot_path, logger=logger)
                    finally:
                        pool.release(conn)
                    for film in film_dirs:
                        fp = join_path(lot_path, film)
                        if filters.film and not match_name(
                            film, fp, filters.film, exact=filters.exact, regex=filters.regex, case_sensitive=filters.case_sensitive
                        ):
                            continue
                        hit = _create_scan_hit(c.name, fp)
                        if filters.link_recipe:
                            film_for_link = extract_film_from_scan_path(fp)
                            linked, rname, rpaths, rsv = link_recipe_for_film(cfgs, film_for_link, out_dir)
                            hit.recipe_linked = bool(linked)
                            hit.recipe_name = rname
                            hit.recipe_paths = rpaths
                            hit.recipe_primary = rpaths[0] if rpaths else None
                            hit.recipe_server = rsv
                        hits.append(hit.to_dict())
                pool.__exit__(None, None, None)
        else:
            idx = load_json(os.path.join(out_dir, "recipes", f"{c.name}_recipes_index.json"), {}) or {}
            by_recipe = idx.get("by_recipe") or {}
            for key, paths in by_recipe.items():
                if match_text(key, filters.film, exact=filters.exact, regex=filters.regex, case_sensitive=filters.case_sensitive):
                    for p in (paths or []):
                        hits.append(Hit(server=c.name, role="film", level="folder", path=p, recipe_name=key, kind="recipe").to_dict())
    out_kind = _decide_result_kind(filters)
    out = {"mode": "direct", "kind": out_kind, "hits": hits, "count": len(hits), "generated_at": now_kst_iso()}
    if notices:
        out["notices"] = notices
    logger.info(f"[search-direct] kind={out_kind} hits={len(hits)}")
    return out


# Backward compatibility alias (DEPRECATED: use search_direct instead)
def search_server(cfgs: List[ServerConfig], filters: SearchFilters, out_dir: str, logger):
    """DEPRECATED: Use search_direct() instead. This traverses directories in real-time."""
    return search_direct(cfgs, filters, out_dir, logger)


def _decide_result_kind(filters: SearchFilters) -> str:
    roles = [r.lower() for r in (filters.roles or []) if r]
    roles = sorted(set(roles))
    if roles == ["film"]:
        return "recipe"
    if roles == ["scan"]:
        return "scan"
    return "mixed"
