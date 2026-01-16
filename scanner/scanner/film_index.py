import os
import posixpath
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple, Set, Optional

from .ftp import RobustFTP, ManagedFTPPool
from .fs_local import LocalAdapter, list_dirs_local
from .models import ServerConfig
from .policy import (
    FILM_BACKOFF_S,
    FILM_INDEX_MAX_WORKERS,
    FILM_INDEX_BATCH_SIZE,
    FILM_INDEX_SKIP_EXISTING,
)
from .utils import (
    ensure_dir,
    join_path,
    save_json,
    load_json,
    normalize_spaces,
)

TARGET_LINE_INDEX = 3  # strategy.ini line to inspect first


def _parse_strategy(lines: List[str]) -> str:
    if len(lines) >= TARGET_LINE_INDEX:
        candidates = [lines[TARGET_LINE_INDEX - 1]] + lines[: TARGET_LINE_INDEX - 1]
    else:
        candidates = lines[:]
    for ln in candidates:
        if "StrategyName" in ln:
            s = ln.split("=", 1)[-1].strip().strip("'\"")
            s = normalize_spaces(s)
            if s:
                return s
    return ""


def film_paths(out_dir: str, server: str) -> Dict[str, str]:
    base = os.path.join(out_dir, "recipes")
    return {
        "index": os.path.join(base, f"{server}_recipes_index.json"),
        "logs_dir": os.path.join(base, "logs"),
    }


def load_index(out_dir: str, server: str):
    p = film_paths(out_dir, server)["index"]
    return load_json(
        p,
        {
            "server": server,
            "recipes_root": None,
            "generated_at": None,
            "updated_at": None,
            "folders": {},
            "by_recipe": {},
            "stats": {"folders": 0, "recipes": 0},
        },
    )


def save_index(out_dir: str, idx):
    p = film_paths(out_dir, idx.get("server", "unknown"))["index"]
    ensure_dir(os.path.dirname(p))
    save_json(p, idx)


def _list_bucket(conn_factory, root: str, pattern: str):
    conn = conn_factory()
    try:
        conn.cwd(root)
        try:
            names = set(conn.nlst(pattern))
            if names:
                names |= set(conn.nlst(pattern))
        except Exception:
            # Fallback for servers that don't support NLST globbing
            try:
                all_names = conn.nlst()
            except Exception:
                all_names = []
            # pattern is "as..." or "as...*"
            pfx = pattern.rstrip("*")
            names = set(n for n in all_names if n.startswith(pfx))
        return sorted(n for n in names if n)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _list_film_names_local(root: str, prefix: str, logger) -> List[str]:
    """Optimized local folder listing."""
    base = os.path.abspath(root)
    if not os.path.isdir(base):
        logger.warning(f"[film] root not found {base}")
        return []

    names = []
    try:
        # Use scandir for better performance than listdir
        with os.scandir(base) as entries:
            for entry in entries:
                if entry.is_dir() and entry.name.startswith(prefix):
                    names.append(entry.name)
    except Exception as e:
        logger.warning(f"[film] scandir failed, fallback to listdir: {e}")
        for d in os.listdir(base):
            if d.startswith(prefix):
                names.add(d)

    return sorted(names)


def _list_film_names_ftp(cfg: ServerConfig, logger) -> List[str]:
    """FTP folder listing with bucket parallelization."""
    root = cfg.root
    prefix = cfg.prefix
    names = set()

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
        size=cfg.pool_size,
    )
    buckets: List[Tuple[str, int]] = [(prefix, 0)]
    with ThreadPoolExecutor(max_workers=max(1, cfg.pool_size)) as ex:
        while buckets:
            pfx, depth = buckets.pop(0)
            futs = []
            if depth < 2:  # depth limit to avoid explosion
                for d in "0123456789":
                    futs.append(ex.submit(_list_bucket, lambda: pool.acquire(), root, f"{pfx}{d}*"))
                subnames = set()
                for fut in as_completed(futs):
                    try:
                        lst = fut.result()
                        subnames |= set(lst)
                    except Exception:
                        continue
                if len(subnames) >= 5000 and depth + 1 < 2:
                    for d in "0123456789":
                        buckets.append((pfx + d, depth + 1))
                else:
                    names |= subnames
            else:
                lst = _list_bucket(lambda: pool.acquire(), root, f"{pfx}*")
                names |= set(lst)
    return sorted({n.rstrip("/") for n in names})


def _list_film_names(cfg: ServerConfig, logger) -> List[str]:
    """List all film folder names from server."""
    root = cfg.root
    prefix = cfg.prefix
    logger.info(f"[film] list server={cfg.name} root={root} prefix={prefix} use_local_fs={cfg.use_local_fs}")

    if cfg.use_local_fs:
        return _list_film_names_local(root, prefix, logger)
    else:
        return _list_film_names_ftp(cfg, logger)


def _read_strategy_local(adapter: LocalAdapter, name: str) -> Tuple[str, str, Optional[str]]:
    """Read strategy.ini from local filesystem."""
    try:
        lines = adapter.retr_first_n(join_path(name, "strategy.ini"), 6)
        sname = _parse_strategy(lines)
        return name, sname, None
    except Exception as e:
        return name, "", str(e)


def _read_strategy_ftp(cfg: ServerConfig, name: str, logger) -> Tuple[str, str, Optional[str]]:
    """Read strategy.ini from FTP server."""
    folder = join_path(cfg.root, name)
    ini_path = join_path(folder, "strategy.ini")
    try:
        conn = RobustFTP(
            cfg.ip,
            cfg.user,
            cfg.password,
            port=cfg.port,
            timeout=cfg.timeout,
            op_deadline=cfg.op_deadline,
            logger=logger,
        )
        lines = conn.retr_first_n(ini_path, 6)
        conn.close()
        sname = _parse_strategy(lines)
        return name, sname, None
    except Exception as e:
        return name, "", str(e)


def _process_strategies_batch(
    cfg: ServerConfig,
    names: List[str],
    existing_folders: Dict[str, dict],
    out_dir: str,
    logger,
    skip_existing: bool = True,
) -> Tuple[Dict[str, dict], int, int]:
    """Process strategy.ini files in parallel batches."""
    folders = {}
    processed = 0
    skipped = 0
    total = len(names)
    start_time = time.time()

    # Determine which folders need processing
    if skip_existing:
        to_process = [n for n in names if n not in existing_folders]
        # Copy existing folders
        for n in names:
            if n in existing_folders:
                folders[n] = existing_folders[n]
                skipped += 1
    else:
        to_process = names

    if skipped > 0:
        logger.info(f"[film] skipping {skipped} already indexed folders, processing {len(to_process)} new folders")

    if not to_process:
        logger.info("[film] no new folders to process")
        return folders, processed, skipped

    # Determine worker count
    max_workers = min(FILM_INDEX_MAX_WORKERS, len(to_process))
    if cfg.use_local_fs:
        max_workers = min(max_workers, 16)  # Local IO doesn't benefit from too many workers

    logger.info(f"[film] processing {len(to_process)} folders with {max_workers} workers")

    # Create adapter for local or prepare for FTP
    if cfg.use_local_fs:
        adapter = LocalAdapter(cfg.root)

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        if cfg.use_local_fs:
            futs = {ex.submit(_read_strategy_local, adapter, nm): nm for nm in to_process}
        else:
            futs = {ex.submit(_read_strategy_ftp, cfg, nm, logger): nm for nm in to_process}

        for fut in as_completed(futs):
            nm = futs[fut]
            try:
                name, strategy, error = fut.result()
                folder_path = join_path(cfg.root, name)
                folders[name] = {"path": folder_path, "strategy": strategy}
                processed += 1

                # Progress logging
                if processed % FILM_INDEX_BATCH_SIZE == 0:
                    elapsed = time.time() - start_time
                    rate = processed / elapsed if elapsed > 0 else 0
                    remaining = (len(to_process) - processed) / rate if rate > 0 else 0
                    logger.info(
                        f"[film] progress: {processed}/{len(to_process)} "
                        f"({100*processed/len(to_process):.1f}%) "
                        f"rate={rate:.1f}/s eta={remaining:.0f}s"
                    )
            except Exception as e:
                logger.warning(f"[film] strategy parse fail {nm}: {e}")
                # Still add the folder with empty strategy
                folder_path = join_path(cfg.root, nm)
                folders[nm] = {"path": folder_path, "strategy": ""}
                processed += 1

    elapsed = time.time() - start_time
    logger.info(f"[film] processed {processed} folders in {elapsed:.1f}s ({processed/elapsed:.1f}/s)")

    return folders, processed, skipped


def bootstrap(cfg: ServerConfig, out_dir: str, logger):
    """Full index rebuild - processes all folders."""
    t_paths = film_paths(out_dir, cfg.name)
    ensure_dir(os.path.dirname(t_paths["index"]))
    logger.info(f"=== [FILM] BOOTSTRAP {cfg.name} ({cfg.ip}) root={cfg.root} ===")

    start_time = time.time()

    # List all folders
    names = _list_film_names(cfg, logger)
    logger.info(f"[film] found {len(names)} folders")

    # Process all (don't skip existing in bootstrap)
    folders, processed, skipped = _process_strategies_batch(
        cfg, names, {}, out_dir, logger, skip_existing=False
    )

    # Build by_recipe index
    by_recipe = {}
    for nm, data in folders.items():
        key = data.get("strategy") or nm
        folder_path = data.get("path", join_path(cfg.root, nm))
        by_recipe.setdefault(key, []).append(folder_path)

    # Save index
    idx = {
        "server": cfg.name,
        "recipes_root": cfg.root,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "updated_at": None,
        "folders": folders,
        "by_recipe": by_recipe,
        "stats": {"folders": len(folders), "recipes": len(by_recipe)},
    }
    save_index(out_dir, idx)

    elapsed = time.time() - start_time
    logger.info(f"[film] bootstrap done: {len(folders)} folders, {len(by_recipe)} recipes in {elapsed:.1f}s")
    return idx


def update(cfg: ServerConfig, out_dir: str, logger):
    """Incremental update - only processes new folders."""
    t_paths = film_paths(out_dir, cfg.name)
    ensure_dir(os.path.dirname(t_paths["index"]))
    logger.info(f"=== [FILM] UPDATE {cfg.name} ({cfg.ip}) root={cfg.root} ===")

    start_time = time.time()

    # Load existing index
    idx = load_index(out_dir, cfg.name)
    existing_folders = idx.get("folders", {})
    logger.info(f"[film] existing index has {len(existing_folders)} folders")

    # List current folders
    names = _list_film_names(cfg, logger)
    logger.info(f"[film] found {len(names)} folders on server")

    # Check for removed folders
    current_set = set(names)
    existing_set = set(existing_folders.keys())
    removed = existing_set - current_set
    if removed:
        logger.info(f"[film] {len(removed)} folders removed from server")
        for r in removed:
            del existing_folders[r]

    # Process only new folders (skip existing)
    folders, processed, skipped = _process_strategies_batch(
        cfg, names, existing_folders, out_dir, logger,
        skip_existing=FILM_INDEX_SKIP_EXISTING
    )

    # Rebuild by_recipe index
    by_recipe = {}
    for nm, data in folders.items():
        key = data.get("strategy") or nm
        folder_path = data.get("path", join_path(cfg.root, nm))
        by_recipe.setdefault(key, []).append(folder_path)

    # Update index
    idx["folders"] = folders
    idx["by_recipe"] = by_recipe
    idx["stats"] = {"folders": len(folders), "recipes": len(by_recipe)}
    idx["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    save_index(out_dir, idx)

    elapsed = time.time() - start_time
    logger.info(
        f"[film] update done: {len(folders)} folders ({processed} new, {skipped} skipped, {len(removed)} removed) "
        f"in {elapsed:.1f}s"
    )
    return idx
