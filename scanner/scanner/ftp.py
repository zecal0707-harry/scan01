import ftplib
import posixpath
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Callable

from .policy import DIR_ENUM_ORDER


class FTPDeadlineTimeout(TimeoutError):
    pass


class RobustFTP:
    """FTP wrapper with deadline, reconnect, keepalive."""

    def __init__(self, host, user, passwd, port=21, timeout=15, op_deadline=25.0, logger=None):
        self.host = host
        self.user = user
        self.passwd = passwd
        self.port = port
        self.timeout = timeout
        self.op_deadline = op_deadline
        self.log = logger
        self.ftp: Optional[ftplib.FTP] = None
        self._connect()

    def _connect(self):
        self.close()
        ftp = ftplib.FTP()
        ftp.connect(self.host, self.port, timeout=self.timeout)
        ftp.login(self.user, self.passwd)
        ftp.set_pasv(True)
        try:
            ftp.sock.settimeout(self.timeout)
            ftp.sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        except Exception:
            pass
        self.ftp = ftp

    def close(self):
        if self.ftp:
            try:
                self.ftp.quit()
            except Exception:
                try:
                    self.ftp.close()
                except Exception:
                    pass
        self.ftp = None

    def _deadline(self, fn: Callable, *args, **kwargs):
        out = {}
        err = {}

        def run():
            try:
                out["v"] = fn(*args, **kwargs)
            except Exception as e:
                err["e"] = e

        t = threading.Thread(target=run, daemon=True)
        t.start()
        t.join(self.op_deadline)
        if t.is_alive():
            try:
                if self.ftp:
                    self.ftp.close()
            except Exception:
                pass
            t.join(0.05)
            raise FTPDeadlineTimeout("FTP op deadline exceeded")
        if "e" in err:
            raise err["e"]
        return out.get("v")

    def cwd(self, p: str):
        return self._deadline(self.ftp.cwd, p)

    def nlst(self, pattern: str = "") -> List[str]:
        out = []
        cmd = f"NLST {pattern}" if pattern else "NLST"
        self._deadline(self.ftp.retrlines, cmd, out.append)
        return [posixpath.basename(n.rstrip("/")) for n in out if n and n not in (".", "..")]

    def retr_first_n(self, path: str, n: int = 3) -> List[str]:
        lines = []

        class _Stop(Exception):
            pass

        def cb(s):
            lines.append(s)
            if len(lines) >= n:
                raise _Stop()

        try:
            self._deadline(self.ftp.retrlines, f"RETR {path}", cb)
        except _Stop:
            pass
        except ftplib.error_perm:
            return []
        except Exception:
            return []
        return lines


def list_dirs(conn: RobustFTP, path: str, logger=None) -> List[str]:
    def _try(fn):
        try:
            return fn()
        except Exception as e:
            if logger:
                logger.debug(f"list_dirs: {fn.__name__} failed: {e}")
            return None

    def dir_mlsd():
        items = []
        conn._deadline(conn.ftp.retrlines, f"MLSD {path}", items.append)
        dirs = []
        for ln in items:
            parts = ln.split(";")
            facts = {kv.split("=")[0].strip().lower(): kv.split("=")[1] for kv in parts if "=" in kv}
            name = parts[-1].strip()
            if facts.get("type") == "dir" and name not in (".", ".."):
                dirs.append(name)
        return sorted(dirs)

    def dir_list():
        items = []
        conn._deadline(conn.ftp.retrlines, f"LIST {path}", items.append)
        dirs = []
        for ln in items:
            if not ln:
                continue
            parts = ln.split()
            name = parts[-1] if parts else ""
            if ln.startswith("d") and name not in (".", ".."):
                dirs.append(name)
        return sorted(dirs)

    def dir_nlst():
        conn.cwd(path)
        names = set(conn.nlst("*"))
        if names:
            names |= set(conn.nlst("*"))  # second probe
        return sorted(n for n in names if n and n not in (".", ".."))

    order = {
        "mlsd": dir_mlsd,
        "list": dir_list,
        "nlst": dir_nlst,
    }
    for key in DIR_ENUM_ORDER:
        fn = order.get(key)
        if not fn:
            continue
        res = _try(fn)
        if res is not None:
            return res
    return []


class ManagedFTPPool:
    """Simple pool to reuse FTP connections across threads."""

    def __init__(self, factory, size: int = 4):
        self.factory = factory
        self.size = max(1, size)
        self.pool = []
        self.lock = threading.Lock()

    def acquire(self) -> RobustFTP:
        with self.lock:
            if self.pool:
                return self.pool.pop()
        return self.factory()

    def release(self, conn: RobustFTP):
        with self.lock:
            if len(self.pool) < self.size:
                self.pool.append(conn)
                return
        try:
            conn.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        with self.lock:
            conns = list(self.pool)
            self.pool.clear()
        for c in conns:
            try:
                c.close()
            except Exception:
                pass


def parallel_map(pool: ManagedFTPPool, work_items, fn, max_workers: int):
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = []
        for item in work_items:
            futs.append(
                ex.submit(
                    _run_with_conn,
                    pool,
                    fn,
                    item,
                )
            )
        for fut in futs:
            try:
                results.append(fut.result())
            except Exception as e:
                results.append(e)
    return results


def _run_with_conn(pool: ManagedFTPPool, fn, item):
    conn = pool.acquire()
    try:
        return fn(conn, item)
    finally:
        pool.release(conn)
