import argparse
import os
import sys
from typing import List

# Add parent directory to path for common module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.logging import setup_logger

from .config import read_server_list
from .planner import plan_download
from .worker import download_hit
from .utils import load_json, save_json, ensure_dir


def parse_args():
    p = argparse.ArgumentParser(description="downloader (CLI ingest only)")
    p.add_argument("--server-file", default="servers.txt")
    p.add_argument("--out", default="out")
    p.add_argument("--file", required=True, help="search result JSON (exported from UI)")
    p.add_argument("--dest-root", required=True, help="local destination root")
    p.add_argument("--overwrite", choices=["resume", "skip", "replace"], default="resume")
    p.add_argument("--dest-mode", choices=["simple", "full"], default="simple", help="simple: wafer/film/lot/date, full: class/wafer/film/lot/date")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args()


def _load_hits(path: str) -> List[dict]:
    doc = load_json(path, {})
    hits = doc.get("hits") if isinstance(doc, dict) else None
    if hits is None:
        hits = load_json(path, [])
    if not isinstance(hits, list):
        return []
    return hits


def main():
    args = parse_args()
    logger = setup_logger("downloader", args.out, verbose=args.verbose)
    try:
        cfgs = read_server_list(args.server_file)
    except Exception as e:
        logger.error(f"[config] failed to read servers: {e}")
        sys.exit(2)

    hits = _load_hits(args.file)
    if not hits:
        logger.error(f"no hits in {args.file}")
        sys.exit(1)

    reports_dir = os.path.join(args.out, "downloader", "reports")
    ensure_dir(reports_dir)
    results = []
    for i, h in enumerate(hits, 1):
        server_name = h.get("server")
        cfg = next((c for c in cfgs if c.name == server_name), None)
        if not cfg:
            logger.warning(f"[{i}] server not found: {server_name}")
            results.append({"hit": h, "status": "error", "reason": "server not found"})
            continue
        plan = plan_download(h, args.dest_root, mode=args.dest_mode)
        dest_dir = plan["dest_dir"]
        recipe_dest = plan.get("recipe_dest")
        # path length guard (Windows XP)
        if len(dest_dir) > 240:
            logger.error(f"[{i}] dest path too long ({len(dest_dir)}): {dest_dir}")
            results.append({"hit": h, "status": "error", "reason": "path too long"})
            continue
        try:
            ensure_dir(dest_dir)
            res = download_hit(h, cfg, dest_dir, args.overwrite, logger, all_cfgs=cfgs, recipe_dest=recipe_dest)
            res.update({"hit": h, "dest": dest_dir})
            results.append(res)
            logger.info(f"[{i}] {h.get('path')} -> {dest_dir} status={res.get('status')}")
        except Exception as e:
            logger.error(f"[{i}] failure {h.get('path')}: {e}")
            results.append({"hit": h, "status": "error", "reason": str(e)})
    rep_path = os.path.join(reports_dir, f"ingest_{os.path.basename(args.file)}")
    save_json(rep_path, {"file": args.file, "dest_root": args.dest_root, "results": results})
    logger.info(f"[report] {rep_path}")


if __name__ == "__main__":
    main()
