import argparse
import os
import sys

# Add parent directory to path for common module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.logging import setup_logger

from .config import read_server_list
from .film_index import bootstrap as film_bootstrap, update as film_update
from .scan_index import bootstrap as scan_bootstrap, update as scan_update, scan_paths
from .search import search_local, search_server
from .http_api import make_server
from .models import SearchFilters
from .utils import ensure_dir, save_json, ts_compact


def parse_args():
    p = argparse.ArgumentParser(description="scanner (stable, local-first)")
    p.add_argument("--mode", required=True, choices=["bootstrap", "update", "search-local", "search-server", "serve"])
    p.add_argument("--server-file", default="servers.txt")
    p.add_argument("--out", default="out")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--http-addr", default="127.0.0.1")
    p.add_argument("--http-port", type=int, default=8081)
    p.add_argument("--server", nargs="*")
    p.add_argument("--role", nargs="*", choices=["film", "scan"])
    p.add_argument("--wafer", nargs="*")
    p.add_argument("--lot", nargs="*")
    p.add_argument("--film", nargs="*")
    p.add_argument("--exact", action="store_true")
    p.add_argument("--regex", action="store_true")
    p.add_argument("--case-sensitive", action="store_true")
    p.add_argument("--link-recipe", dest="link_recipe", action="store_true")
    return p.parse_args()


def _filter_cfgs(cfgs, args):
    servers = set(args.server or [])
    roles = set([r.lower() for r in (args.role or [])])
    out = []
    for c in cfgs:
        if servers and c.name not in servers:
            continue
        if roles and c.role not in roles:
            continue
        out.append(c)
    return out


def main():
    args = parse_args()
    logger = setup_logger("scanner", args.out, verbose=args.verbose)
    try:
        cfgs = read_server_list(args.server_file)
    except Exception as e:
        logger.error(f"[config] failed to read servers: {e}")
        sys.exit(2)

    if args.mode == "serve":
        srv = make_server(cfgs, args.out, logger, addr=args.http_addr, port=args.http_port)
        print(f"[HTTP] listening on http://{args.http_addr}:{args.http_port}")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            print("[HTTP] shutdown")
            try:
                srv.shutdown()
            except Exception:
                pass
        return

    scope = _filter_cfgs(cfgs, args)
    if args.mode == "bootstrap":
        for c in scope:
            if c.role == "film":
                film_bootstrap(c, args.out, logger)
            else:
                scan_bootstrap(c, args.out, logger)
    elif args.mode == "update":
        for c in scope:
            if c.role == "film":
                film_update(c, args.out, logger)
            else:
                scan_update(c, args.out, logger)
    elif args.mode == "search-local":
        filters = SearchFilters(
            servers=args.server or [],
            roles=args.role or [],
            wafer=args.wafer or [],
            lot=args.lot or [],
            film=args.film or [],
            exact=args.exact,
            regex=args.regex,
            case_sensitive=args.case_sensitive,
            link_recipe=getattr(args, "link_recipe", False),
        )
        out = search_local(cfgs, filters, args.out, logger)
        outp = os.path.join(args.out, "search_results")
        ensure_dir(outp)
        path = os.path.join(outp, f"search_local_{out.get('kind','scan')}_{ts_compact()}.json")
        save_json(path, out)
        logger.info(f"[search-local] json={path}")
    elif args.mode == "search-server":
        filters = SearchFilters(
            servers=args.server or [],
            roles=args.role or [],
            wafer=args.wafer or [],
            lot=args.lot or [],
            film=args.film or [],
            exact=args.exact,
            regex=args.regex,
            case_sensitive=args.case_sensitive,
            link_recipe=getattr(args, "link_recipe", False),
        )
        out = search_server(cfgs, filters, args.out, logger)
        outp = os.path.join(args.out, "search_results")
        ensure_dir(outp)
        path = os.path.join(outp, f"search_server_{out.get('kind','scan')}_{ts_compact()}.json")
        save_json(path, out)
        logger.info(f"[search-server] json={path}")
    else:
        logger.error(f"unknown mode {args.mode}")


if __name__ == "__main__":
    main()
