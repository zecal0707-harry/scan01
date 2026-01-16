import os
import posixpath
from typing import List


class LocalAdapter:
    """FTP-like minimal interface for local filesystem (POSIX-style paths)."""

    def __init__(self, root: str):
        self.root = os.path.abspath(root)
        self.cwd_path = self.root

    def _real(self, p: str) -> str:
        if p.startswith("/"):
            p = p[1:]
        return os.path.join(self.root, p)

    def cwd(self, p: str):
        rp = self._real(p)
        if not os.path.isdir(rp):
            raise FileNotFoundError(p)
        self.cwd_path = rp

    def nlst(self, pattern: str = "") -> List[str]:
        base = self.cwd_path
        names = []
        for name in os.listdir(base):
            if name in (".", ".."):
                continue
            names.append(posixpath.basename(name.rstrip("/")))
        return names

    def retr_first_n(self, path: str, n: int = 3) -> List[str]:
        """Read first n lines from a text file."""
        rp = self._real(path)
        out = []
        if not os.path.isfile(rp):
            return out
        with open(rp, "r", encoding="utf-8", errors="ignore") as f:
            for i, ln in enumerate(f):
                if i >= n:
                    break
                out.append(ln.rstrip("\r\n"))
        return out

    def retrbinary(self, cmd: str, cb, blocksize=8192):
        """FTP-style binary retrieval (cmd like 'RETR <path>')."""
        path = cmd.split(" ", 1)[-1]
        rp = self._real(path)
        with open(rp, "rb") as f:
            while True:
                b = f.read(blocksize)
                if not b:
                    break
                cb(b)


def list_dirs_local(root: str, path: str) -> List[str]:
    """List directories at given path under root."""
    rp = os.path.join(os.path.abspath(root), path.lstrip("/"))
    if not os.path.isdir(rp):
        return []
    return sorted([p for p in os.listdir(rp) if os.path.isdir(os.path.join(rp, p))])
