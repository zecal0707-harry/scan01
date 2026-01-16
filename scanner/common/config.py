from typing import List, Dict
import csv
import os

from .models import ServerConfig


DEFAULT_USER = "FTP_TEST"
DEFAULT_PASS = "FTP_TEST"
DEFAULT_TIMEOUT = 15
DEFAULT_OP_DEADLINE = 25.0
DEFAULT_PORT = 21
DEFAULT_FILM_ROOT = "/Film List"
DEFAULT_SCAN_ROOT = "/auto scan data"
DEFAULT_PREFIX = "as"


def _int_or_default(val, default):
    try:
        return int(val)
    except Exception:
        return default


def read_server_list(path: str) -> List[ServerConfig]:
    """Parse servers.txt configuration file."""
    if not os.path.isfile(path):
        raise FileNotFoundError(f"server file not found: {path}")
    cleaned = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        for i, ln in enumerate(f, 1):
            base = ln.split("#", 1)[0].strip()
            if base:
                cleaned.append((i, base))
    rdr = csv.reader((x[1] for x in cleaned))
    out: List[ServerConfig] = []
    for (i, _raw), row in zip(cleaned, rdr):
        row = [c.strip() for c in row if c is not None and c.strip() != ""]
        if len(row) < 4:
            raise ValueError(f"line {i}: need >=4 columns (name, ip, max_depth, save_level)")
        name, ip, max_depth_s, save_level_s = row[:4]
        user, pw, meta_tokens = DEFAULT_USER, DEFAULT_PASS, row[4:]
        if len(row) >= 6:
            user, pw = row[4], row[5]
            meta_tokens = row[6:]
        meta: Dict[str, str] = {}
        for tok in meta_tokens:
            if "=" not in tok:
                raise ValueError(f"line {i}: meta token needs key=value => {tok}")
            k, v = tok.split("=", 1)
            k = k.strip().lower()
            if k in meta:
                raise ValueError(f"line {i}: duplicate meta key {k}")
            meta[k] = v.strip()
        role = (meta.get("role") or "film").lower()
        if role not in ("film", "scan"):
            raise ValueError(f"line {i}: role must be film|scan")
        group = meta.get("group") or name
        root = (meta.get("root") or (DEFAULT_FILM_ROOT if role == "film" else DEFAULT_SCAN_ROOT)).strip()
        prefix = (meta.get("prefix") or DEFAULT_PREFIX).strip() or DEFAULT_PREFIX
        port = _int_or_default(meta.get("port"), DEFAULT_PORT)
        timeout = _int_or_default(meta.get("timeout"), DEFAULT_TIMEOUT)
        op_deadline = float(meta.get("op_deadline") or DEFAULT_OP_DEADLINE)
        pool_size = _int_or_default(meta.get("pool_size"), 6 if role == "film" else 3)
        # source=local|network|ftp (권장), local=1 (하위 호환)
        # local: 로컬 파일시스템, network: 네트워크 드라이브(SMB/UNC), ftp: FTP 서버
        source_val = meta.get("source")
        local_val = meta.get("local")  # deprecated, use source=local instead
        if source_val is not None:
            # local, network 모두 파일시스템 API 사용 (use_local_fs=True)
            use_local_fs = source_val.strip().lower() in ("local", "network", "filesystem", "fs", "smb", "unc")
        elif local_val is not None:
            use_local_fs = local_val.strip().lower() in ("1", "true", "yes", "on")
        else:
            use_local_fs = (meta.get("scheme") == "local")
        out.append(
            ServerConfig(
                name=name,
                ip=ip,
                port=port,
                user=user,
                password=pw,
                role=role,
                group=group,
                root=root or (DEFAULT_FILM_ROOT if role == "film" else DEFAULT_SCAN_ROOT),
                prefix=prefix,
                timeout=timeout,
                op_deadline=op_deadline,
                pool_size=pool_size,
                use_local_fs=bool(use_local_fs),
                meta=meta,
            )
        )
    if not out:
        raise ValueError("no servers loaded from file")
    return out
