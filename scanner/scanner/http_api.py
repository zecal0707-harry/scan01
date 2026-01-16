import json
import os
import sys
import posixpath
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer, SimpleHTTPRequestHandler
import socketserver
import traceback
from typing import List
from concurrent.futures import ThreadPoolExecutor

# Add parent directory to path for module imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .search import search_cache, search_direct
from .scan_index import bootstrap, update as index_update, get_index_status, scan_paths
from .models import SearchFilters, ServerConfig
from .utils import now_kst_iso, ensure_dir

# Import downloader modules
from downloader.planner import plan_download
from downloader.worker import download_hit


def _parse_search_filters(body: dict) -> SearchFilters:
    """Parse request body into SearchFilters."""
    return SearchFilters(
        servers=body.get("servers") or [],
        roles=body.get("roles") or [],
        wafer=body.get("wafer") or [],
        lot=body.get("lot") or [],
        film=body.get("film") or [],
        exact=bool(body.get("exact")),
        regex=bool(body.get("regex")),
        case_sensitive=bool(body.get("case_sensitive")),
        link_recipe=bool(body.get("link_recipe")),
    )


def _handle_download(body: dict, cfgs: List[ServerConfig], out_dir: str, logger) -> dict:
    """Handle download request for selected hits."""
    hits = body.get("hits") or []
    dest_root = body.get("dest_root") or ""
    overwrite = body.get("overwrite") or "resume"
    dest_mode = body.get("dest_mode") or "simple"

    if not hits:
        return {"status": "error", "message": "No hits provided"}
    if not dest_root:
        return {"status": "error", "message": "dest_root is required"}

    results = []
    success_count = 0
    error_count = 0

    for i, h in enumerate(hits, 1):
        server_name = h.get("server")
        cfg = next((c for c in cfgs if c.name == server_name), None)
        if not cfg:
            if logger:
                logger.warning(f"[download][{i}] server not found: {server_name}")
            results.append({"hit": h, "status": "error", "reason": "server not found"})
            error_count += 1
            continue

        try:
            plan = plan_download(h, dest_root, mode=dest_mode)
            dest_dir = plan["dest_dir"]
            recipe_dest = plan.get("recipe_dest")

            # Path length guard (Windows)
            if len(dest_dir) > 240:
                if logger:
                    logger.error(f"[download][{i}] dest path too long ({len(dest_dir)}): {dest_dir}")
                results.append({"hit": h, "status": "error", "reason": "path too long"})
                error_count += 1
                continue

            ensure_dir(dest_dir)
            res = download_hit(h, cfg, dest_dir, overwrite, logger, all_cfgs=cfgs, recipe_dest=recipe_dest)
            res.update({"hit": h, "dest": dest_dir})
            results.append(res)

            if res.get("status") == "ok":
                success_count += 1
            else:
                error_count += 1

            if logger:
                logger.info(f"[download][{i}] {h.get('path')} -> {dest_dir} status={res.get('status')}")
        except Exception as e:
            if logger:
                logger.error(f"[download][{i}] failure {h.get('path')}: {e}")
            results.append({"hit": h, "status": "error", "reason": str(e)})
            error_count += 1

    return {
        "status": "completed",
        "total": len(hits),
        "success": success_count,
        "errors": error_count,
        "results": results,
        "generated_at": now_kst_iso(),
    }


def create_handler(cfgs: List[ServerConfig], out_dir: str, logger, static_dir: str = None):
    """Factory function to create handler class with captured configuration."""

    class APIHandler(SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            # Suppress default logging, use our logger instead
            if logger:
                logger.debug(f"HTTP: {format % args}")

        def _json(self, code: int, obj: dict):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "*")
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "*")
            self.end_headers()

        def _parse_json(self) -> dict:
            try:
                ln = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(ln) if ln > 0 else b""
                return json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                return {}

        def do_GET(self):
            # Support /scanner prefix (proxy emulation)
            if self.path.startswith("/scanner/"):
                self.path = self.path[8:]  # strip "/scanner"

            # API Endpoints
            if self.path.startswith("/v1/") or self.path == "/health":
                return self._handle_api_get()
            
            # Static File Serving
            if not static_dir or not os.path.exists(static_dir):
                return self._json(404, {"error": "UI not found (static_dir missing)"})
            
            # Map request path to file path
            if self.path == "/" or self.path == "":
                self.path = "/index.html"
            
            # SimpleHTTPRequestHandler serves from CWD by default, 
            # so we must change directory temporarily or override translate_path.
            # A safer way without changing CWD is to manually serve the file or use directory argument (Py3.7+)
            # But SimpleHTTPRequestHandler(..., directory=...) is only available in constructor.
            # So we will override translate_path.
            try:
                return super().do_GET()
            except Exception as e:
                if logger:
                    logger.error(f"GET unhandled error: {str(e)}\n{traceback.format_exc()}")
                self.send_error(500, f"Internal Server Error: {e}")

        def translate_path(self, path):
            # Override to serve from static_dir
            path = path.split('?',1)[0]
            path = path.split('#',1)[0]
            trailing_slash = path.rstrip().endswith('/')
            path = urllib.parse.unquote(path, errors='surrogatepass')
            
            path = posixpath.normpath(path)
            words = path.split('/')
            words = [w for w in words if w and w != '..']
            
            path = static_dir
            for word in words:
                drive, word = os.path.splitdrive(word)
                head, word = os.path.split(word)
                if word in (os.curdir, os.pardir): continue
                path = os.path.join(path, word)
            if trailing_slash:
                path += os.sep
            return path

        def _handle_api_get(self):
            try:
                if self.path == "/health":
                    return self._json(200, {"ok": True, "time": now_kst_iso()})
                if self.path == "/v1/servers":
                    brief = [
                        {"name": c.name, "role": c.role, "ip": c.ip, "group": c.group, "root": c.root, "source": "local" if c.use_local_fs else "ftp"}
                        for c in cfgs
                    ]
                    return self._json(200, {"servers": brief, "count": len(brief)})
                if self.path == "/v1/index/status":
                    # Get index status for all scan servers
                    statuses = []
                    for c in cfgs:
                        if c.role == "scan":
                            status = get_index_status(c, out_dir)
                            statuses.append(status)
                    return self._json(200, {"statuses": statuses, "count": len(statuses)})
                return self._json(404, {"error": "not found"})
            except Exception as e:
                if logger:
                    logger.error(f"GET ERROR: {str(e)}\n{traceback.format_exc()}")
                return self._json(500, {"error": str(e)})

        def do_POST(self):
            if self.path.startswith("/scanner/"):
                self.path = self.path[8:]

            try:
                # Search endpoints
                if self.path == "/v1/search/cache" or self.path == "/v1/search/local":
                    body = self._parse_json() or {}
                    filters = _parse_search_filters(body)
                    out = search_cache(cfgs, filters, out_dir, logger)
                    return self._json(200, out)
                if self.path == "/v1/search/direct" or self.path == "/v1/search/server":
                    body = self._parse_json() or {}
                    filters = _parse_search_filters(body)
                    out = search_direct(cfgs, filters, out_dir, logger)
                    return self._json(200, out)
                if self.path == "/v1/download":
                    body = self._parse_json() or {}
                    out = _handle_download(body, cfgs, out_dir, logger)
                    return self._json(200, out)
                # Index management endpoints
                if self.path == "/v1/index/bootstrap":
                    body = self._parse_json() or {}
                    target_servers = body.get("servers") or []
                    results = []
                    for c in cfgs:
                        if c.role != "scan":
                            continue
                        if target_servers and c.name not in target_servers:
                            continue
                        try:
                            result = bootstrap(c, out_dir, logger)
                            results.append({
                                "server": c.name,
                                "status": "ok",
                                "lots": len(result.get("lots_index", {})),
                                "films": sum(len(v) for v in result.get("films_index", {}).values()),
                            })
                        except Exception as e:
                            results.append({"server": c.name, "status": "error", "message": str(e)})
                    return self._json(200, {"status": "completed", "results": results})
                if self.path == "/v1/index/update":
                    body = self._parse_json() or {}
                    target_servers = body.get("servers") or []
                    results = []
                    for c in cfgs:
                        if c.role != "scan":
                            continue
                        if target_servers and c.name not in target_servers:
                            continue
                        try:
                            result = index_update(c, out_dir, logger)
                            results.append({
                                "server": c.name,
                                "status": "ok",
                                "added_lots": result.get("added_lots", 0),
                                "deleted_lots": result.get("deleted_lots", 0),
                                "added_films": result.get("added_films", 0),
                            })
                        except Exception as e:
                            results.append({"server": c.name, "status": "error", "message": str(e)})
                    return self._json(200, {"status": "completed", "results": results})
                return self._json(404, {"error": "not found"})
            except Exception as e:
                if logger:
                    logger.error(f"POST ERROR: {str(e)}\n{traceback.format_exc()}")
                return self._json(500, {"error": str(e), "trace": traceback.format_exc()})

    return APIHandler


def make_server(cfgs, out_dir, logger, addr="127.0.0.1", port=8081):
    """Create and return HTTP server instance."""
    # Determine static directory (../ui/dist relative to this file)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(current_dir))
    static_dir = os.path.join(project_root, "scanner", "ui", "dist")
    
    if logger:
        logger.info(f"Serve static dir: {static_dir}")

    handler_class = create_handler(cfgs, out_dir, logger, static_dir)

    class ThreadingHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
        daemon_threads = True
        allow_reuse_address = True

    srv = ThreadingHTTPServer((addr, port), handler_class)
    return srv
