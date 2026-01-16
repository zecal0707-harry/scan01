import os
import posixpath
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple, Any, Set

from .ftp import RobustFTP, list_dirs, ManagedFTPPool
from .fs_local import LocalAdapter, list_dirs_local
from .models import ServerConfig
from .policy import (
    DEFAULT_MAX_WORKERS_EXPAND,
    DEFAULT_MAX_LOTS_EXPAND,
    SCAN_INDEX_MAX_WORKERS,
    SCAN_INDEX_BATCH_SIZE,
    SCAN_INDEX_MAX_DEPTH,
)
from .utils import ensure_dir, join_path, save_json, load_json, match_text, lot_match, DATE_RX


def scan_paths(out_dir: str, server: str) -> Dict[str, str]:
    base = os.path.join(out_dir, "required")
    return {
        "full": os.path.join(base, f"{server}_Full.json"),
        "lots_index": os.path.join(base, f"{server}_lots_index.json"),
        "films_index": os.path.join(base, f"{server}_films_index.json"),
        "visited": os.path.join(base, f"{server}_visited.json"),
        "logs_dir": os.path.join(out_dir, "logs"),
    }


def get_index_status(cfg: ServerConfig, out_dir: str) -> Dict[str, Any]:
    """Get current index status for a server."""
    from .utils import now_kst_iso
    paths = scan_paths(out_dir, cfg.name)

    lots_doc = load_json(paths["lots_index"], {})
    films_doc = load_json(paths["films_index"], {})
    visited_doc = load_json(paths["visited"], {})

    lots_index = lots_doc.get("lots_index", {})
    films_index = films_doc.get("films_index", {})

    return {
        "server": cfg.name,
        "last_bootstrap": visited_doc.get("last_bootstrap"),
        "last_update": visited_doc.get("last_update"),
        "indexed_lots": len(lots_index),
        "indexed_films": sum(len(v) for v in films_index.values()),
        "visited_lot_paths": len(visited_doc.get("visited_lot_paths", [])),
    }


def _list_dirs(cfg: ServerConfig, path: str, logger) -> List[str]:
    if cfg.use_local_fs:
        return list_dirs_local(cfg.root, path)
    conn = RobustFTP(
        cfg.ip,
        cfg.user,
        cfg.password,
        port=cfg.port,
        timeout=cfg.timeout,
        op_deadline=cfg.op_deadline,
        logger=logger,
    )
    try:
        return list_dirs(conn, path, logger=logger)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _list_dirs_pool(pool: ManagedFTPPool, path: str, logger) -> List[str]:
    conn = pool.acquire()
    try:
        return list_dirs(conn, path, logger=logger)
    finally:
        pool.release(conn)


def _find_date_folders_local_optimized(root_abs: str, cfg_root: str, logger) -> List[Tuple[str, str, str, str, str]]:
    """
    Optimized recursive find of all date folders (8-digit) using parallel processing.
    Returns list of (date_path_posix, film_name, lot_name, wafer_name, lot_path_posix)
    """
    results = []
    start_time = time.time()
    processed_dirs = 0

    def scan_directory(dir_path: str, depth: int = 0) -> List[Tuple[str, str, str, str, str]]:
        """Scan a single directory and return date folder entries."""
        nonlocal processed_dirs
        local_results = []

        if depth > SCAN_INDEX_MAX_DEPTH:
            return local_results

        try:
            with os.scandir(dir_path) as entries:
                subdirs = []
                for entry in entries:
                    if entry.is_dir(follow_symlinks=False):
                        dirname = entry.name
                        if DATE_RX.fullmatch(dirname):
                            # Found date folder, parse structure
                            date_abs = entry.path
                            film_abs = dir_path
                            lot_abs = os.path.dirname(film_abs)
                            wafer_abs = os.path.dirname(lot_abs)

                            film_name = os.path.basename(film_abs)
                            lot_name = os.path.basename(lot_abs)
                            wafer_name = os.path.basename(wafer_abs)

                            rel_path = os.path.relpath(date_abs, root_abs)
                            date_path_posix = join_path(cfg_root, rel_path.replace("\\", "/"))

                            rel_lot = os.path.relpath(lot_abs, root_abs)
                            lot_path_posix = join_path(cfg_root, rel_lot.replace("\\", "/"))

                            local_results.append((date_path_posix, film_name, lot_name, wafer_name, lot_path_posix))
                        else:
                            subdirs.append(entry.path)

                # Recursively scan subdirectories
                for subdir in subdirs:
                    local_results.extend(scan_directory(subdir, depth + 1))

        except PermissionError:
            pass
        except Exception as e:
            logger.warning(f"[scan] error scanning {dir_path}: {e}")

        processed_dirs += 1
        if processed_dirs % SCAN_INDEX_BATCH_SIZE == 0:
            elapsed = time.time() - start_time
            logger.info(f"[scan] progress: scanned {processed_dirs} directories, found {len(results)} entries ({elapsed:.1f}s)")

        return local_results

    # Start scanning from root
    logger.info(f"[scan] starting local scan from {root_abs}")
    results = scan_directory(root_abs)

    elapsed = time.time() - start_time
    logger.info(f"[scan] local scan complete: {len(results)} date entries found in {elapsed:.1f}s")

    return results


def _find_date_folders_ftp_parallel(cfg: ServerConfig, logger) -> List[Tuple[str, str, str, str, str]]:
    """
    Parallel FTP directory traversal to find date folders.
    """
    results = []
    start_time = time.time()
    processed_dirs = [0]  # Use list to allow modification in nested function

    pool = ManagedFTPPool(
        lambda: RobustFTP(
            cfg.ip,
            cfg.user,
            cfg.password,
            port=cfg.port,
            timeout=cfg.timeout,
            op_deadline=cfg.op_deadline,
            logger=logger,
        ),
        size=max(4, cfg.pool_size),
    )

    def process_directory(current_path: str, depth: int) -> List[Tuple[str, str, str, str, str]]:
        """Process a single directory and return results + subdirs to process."""
        local_results = []

        if depth > SCAN_INDEX_MAX_DEPTH:
            return local_results

        try:
            dirs = _list_dirs_pool(pool, current_path, logger)
        except Exception as e:
            logger.warning(f"[scan] FTP error at {current_path}: {e}")
            return local_results

        subdirs_to_process = []

        for d in dirs:
            child_path = join_path(current_path, d)
            if DATE_RX.fullmatch(d):
                # Found date folder
                parts = child_path.split("/")
                if len(parts) >= 5:
                    date_path = child_path
                    film_name = parts[-2]
                    lot_name = parts[-3]
                    wafer_name = parts[-4]
                    lot_path = "/".join(parts[:-2])

                    local_results.append((date_path, film_name, lot_name, wafer_name, lot_path))
            else:
                subdirs_to_process.append((child_path, depth + 1))

        processed_dirs[0] += 1
        if processed_dirs[0] % SCAN_INDEX_BATCH_SIZE == 0:
            elapsed = time.time() - start_time
            logger.info(f"[scan] FTP progress: {processed_dirs[0]} dirs, {len(results)} entries ({elapsed:.1f}s)")

        return local_results, subdirs_to_process

    # BFS with parallel processing
    logger.info(f"[scan] starting FTP scan from {cfg.root}")

    queue = [(cfg.root, 0)]

    with ThreadPoolExecutor(max_workers=min(SCAN_INDEX_MAX_WORKERS, cfg.pool_size)) as executor:
        while queue:
            # Process batch of directories in parallel
            batch = queue[:SCAN_INDEX_MAX_WORKERS * 2]
            queue = queue[len(batch):]

            futures = {executor.submit(process_directory, path, depth): (path, depth)
                      for path, depth in batch}

            for future in as_completed(futures):
                try:
                    result = future.result()
                    if isinstance(result, tuple) and len(result) == 2:
                        local_results, subdirs = result
                        results.extend(local_results)
                        queue.extend(subdirs)
                except Exception as e:
                    path, depth = futures[future]
                    logger.warning(f"[scan] error processing {path}: {e}")

    try:
        pool.__exit__(None, None, None)
    except:
        pass

    elapsed = time.time() - start_time
    logger.info(f"[scan] FTP scan complete: {len(results)} entries in {elapsed:.1f}s")

    return results


def bootstrap(cfg: ServerConfig, out_dir: str, logger):
    """Full index rebuild with optimized traversal."""
    paths = scan_paths(out_dir, cfg.name)
    ensure_dir(os.path.dirname(paths["full"]))
    logger.info(f"=== [SCAN] BOOTSTRAP {cfg.name} ({cfg.ip}) root={cfg.root} ===")

    start_time = time.time()

    wafers: Dict[str, str] = {}
    lots_index: Dict[str, List[str]] = {}
    films_index: Dict[str, List[str]] = {}

    if cfg.use_local_fs:
        root_abs = os.path.abspath(cfg.root)
        date_entries = _find_date_folders_local_optimized(root_abs, cfg.root, logger)
    else:
        date_entries = _find_date_folders_ftp_parallel(cfg, logger)

    # Build indices from entries
    logger.info(f"[scan] building indices from {len(date_entries)} entries...")

    for i, (date_path_posix, film_name, lot_name, wafer_name, lot_path_posix) in enumerate(date_entries):
        # Collect wafers
        if wafer_name not in wafers:
            wafer_path = posixpath.dirname(lot_path_posix)
            wafers[wafer_name] = wafer_path

        # Build lots_index
        if lot_name not in lots_index:
            lots_index[lot_name] = []
        if lot_path_posix not in lots_index[lot_name]:
            lots_index[lot_name].append(lot_path_posix)

        # Build films_index
        if lot_path_posix not in films_index:
            films_index[lot_path_posix] = []
        films_index[lot_path_posix].append(date_path_posix)

        if (i + 1) % 10000 == 0:
            logger.info(f"[scan] indexing progress: {i + 1}/{len(date_entries)}")

    # Sort films_index values
    for k in films_index:
        films_index[k] = sorted(set(films_index[k]))

    wafer_list = [{"name": n, "path": p} for n, p in wafers.items()]

    from .utils import now_kst_iso
    now = now_kst_iso()

    full_doc = {
        "server": cfg.name,
        "scan_root": cfg.root,
        "generated_at": now,
        "updated_at": None,
        "wafer_paths": [w["path"] for w in wafer_list],
    }

    save_json(paths["full"], full_doc)
    save_json(paths["lots_index"], {"server": cfg.name, "lots_index": lots_index})
    save_json(paths["films_index"], {"server": cfg.name, "mode": "map", "films_index": films_index})

    # Save visited paths for incremental update
    visited_lot_paths = list(films_index.keys())
    visited_doc = {
        "server": cfg.name,
        "last_bootstrap": now,
        "last_update": None,
        "visited_lot_paths": visited_lot_paths,
    }
    save_json(paths["visited"], visited_doc)

    elapsed = time.time() - start_time
    logger.info(
        f"[scan] bootstrap complete: wafers={len(wafer_list)} lots={len(lots_index)} "
        f"film_paths={sum(len(v) for v in films_index.values())} in {elapsed:.1f}s"
    )
    return {"wafers": wafer_list, "lots_index": lots_index, "films_index": films_index}


def update(cfg: ServerConfig, out_dir: str, logger):
    """Incremental update: only scan new paths, skip visited paths."""
    from .utils import now_kst_iso

    paths = scan_paths(out_dir, cfg.name)
    start_time = time.time()

    # Load existing data
    lots_doc = load_json(paths["lots_index"], {})
    films_doc = load_json(paths["films_index"], {})
    visited_doc = load_json(paths["visited"], {})

    lots_index: Dict[str, List[str]] = lots_doc.get("lots_index", {})
    films_index: Dict[str, List[str]] = films_doc.get("films_index", {})
    visited_lot_paths: Set[str] = set(visited_doc.get("visited_lot_paths", []))

    if not visited_lot_paths:
        logger.info(f"[scan] update: no visited data, doing full bootstrap")
        return bootstrap(cfg, out_dir, logger)

    logger.info(f"=== [SCAN] UPDATE {cfg.name} ({cfg.ip}) root={cfg.root} ===")
    logger.info(f"[scan] existing: {len(visited_lot_paths)} visited lot paths, {len(lots_index)} lots")

    # Get current entries
    if cfg.use_local_fs:
        root_abs = os.path.abspath(cfg.root)
        date_entries = _find_date_folders_local_optimized(root_abs, cfg.root, logger)
    else:
        date_entries = _find_date_folders_ftp_parallel(cfg, logger)

    added_lots = 0
    added_films = 0
    current_lot_paths: Set[str] = set()

    # Process entries
    for date_path_posix, film_name, lot_name, wafer_name, lot_path_posix in date_entries:
        current_lot_paths.add(lot_path_posix)

        # Check if this is a new lot path
        is_new_lot_path = lot_path_posix not in visited_lot_paths

        if is_new_lot_path:
            if lot_name not in lots_index:
                lots_index[lot_name] = []
            if lot_path_posix not in lots_index[lot_name]:
                lots_index[lot_name].append(lot_path_posix)
                added_lots += 1

        # Always check for new film entries (even in visited lots, new films might exist)
        if lot_path_posix not in films_index:
            films_index[lot_path_posix] = []
        if date_path_posix not in films_index[lot_path_posix]:
            films_index[lot_path_posix].append(date_path_posix)
            added_films += 1

    # Sort films_index values
    for k in films_index:
        films_index[k] = sorted(set(films_index[k]))

    # Find and remove deleted lot paths
    deleted_lot_paths = visited_lot_paths - current_lot_paths
    deleted_lots = 0
    for lot_path in deleted_lot_paths:
        if lot_path in films_index:
            del films_index[lot_path]
            deleted_lots += 1
        for lot_name in list(lots_index.keys()):
            if lot_path in lots_index[lot_name]:
                lots_index[lot_name].remove(lot_path)
                if not lots_index[lot_name]:
                    del lots_index[lot_name]

    # Save updated data
    now = now_kst_iso()
    save_json(paths["lots_index"], {"server": cfg.name, "lots_index": lots_index})
    save_json(paths["films_index"], {"server": cfg.name, "mode": "map", "films_index": films_index})

    visited_doc["last_update"] = now
    visited_doc["visited_lot_paths"] = list(current_lot_paths)
    save_json(paths["visited"], visited_doc)

    elapsed = time.time() - start_time
    logger.info(
        f"[scan] update complete: +{added_lots} lots, -{deleted_lots} lots, +{added_films} films "
        f"in {elapsed:.1f}s"
    )
    return {
        "added_lots": added_lots,
        "deleted_lots": deleted_lots,
        "added_films": added_films,
        "lots_index": lots_index,
        "films_index": films_index,
    }
