import os
import shutil
from typing import Dict, Callable, List

from .utils import ensure_dir
from .ftp_remote import RobustFTP
from .ftp_local import LocalAdapter


def _fetch_file(conn, remote_path: str, local_path: str, logger, overwrite: str):
    tmp_path = local_path + ".part"
    ensure_dir(os.path.dirname(local_path))
    if os.path.isfile(local_path):
        if overwrite == "skip":
            return "skip"
        if overwrite == "resume" and os.path.isfile(tmp_path):
            pass  # resume not implemented; overwrite part
    with open(tmp_path, "wb") as f:
        def writer(chunk: bytes):
            f.write(chunk)

        conn.retrbinary(f"RETR {remote_path}", writer)
    shutil.move(tmp_path, local_path)
    return "ok"


def _copy_recipe_local(recipe_path: str, film_root: str, dest_base: str):
    # recipe_path is posix absolute, may already include root
    rp = recipe_path
    if recipe_path.startswith(film_root):
        rp = recipe_path
    else:
        rp = os.path.join(film_root, recipe_path.lstrip("/"))
    if not os.path.isdir(rp):
        return False
    out_dir = dest_base
    for root, dirs, files in os.walk(rp):
        rel = os.path.relpath(root, rp)
        for d in dirs:
            ensure_dir(os.path.join(out_dir, rel, d))
        for f in files:
            src = os.path.join(root, f)
            dst = os.path.join(out_dir, rel, f)
            ensure_dir(os.path.dirname(dst))
            shutil.copy2(src, dst)
    return True


def _download_recipe_ftp(conn, recipe_path: str, dest_base: str):
    # best-effort: download strategy.ini only
    ensure_dir(dest_base)
    dst = os.path.join(dest_base, "strategy.ini")
    try:
        _fetch_file(conn, f"{recipe_path}/strategy.ini", dst, logger=None, overwrite="replace")
        return True
    except Exception:
        return False


def _download_tree_local(src_root: str, dest_root: str, overwrite: str):
    statuses = []
    if not os.path.isdir(src_root):
        return [f"err:not_found:{src_root}"]

    for root, dirs, files in os.walk(src_root):
        rel = os.path.relpath(root, src_root)
        cur_dest = os.path.join(dest_root, rel)
        ensure_dir(cur_dest)

        for f in files:
            src_file = os.path.join(root, f)
            dst_file = os.path.join(cur_dest, f)
            try:
                if os.path.exists(dst_file):
                    if overwrite == "skip":
                        statuses.append("skip")
                        continue
                    if overwrite == "resume":
                        # Simplistic resume: if size matches or exists?
                        # For local-to-local, copy is cheap, just overwrite?
                        pass
                shutil.copy2(src_file, dst_file)
                statuses.append("ok")
            except Exception as e:
                statuses.append(f"err:{f}:{e}")
    return statuses


def _download_tree_remote(conn, remote_dir: str, local_dir: str, logger, overwrite: str):
    ensure_dir(local_dir)
    statuses = []

    # Try MLSD
    try:
        items = list(conn.mlsd(remote_dir, facts=["type"]))
    except Exception as e:
        # If MLSD fails, it might be a file or MLSD not supported.
        # Check if we can fallback to file download (if remote_dir is actually a file)
        # But here we assume remote_dir is the path provided in hit.
        return [f"err:mlsd_fail:{e}"]

    for name, facts in items:
        if name in (".", ".."):
            continue
        
        ftype = facts.get("type", "file")
        r_path = f"{remote_dir}/{name}"
        l_path = os.path.join(local_dir, name)

        if ftype == "dir":
            res = _download_tree_remote(conn, r_path, l_path, logger, overwrite)
            statuses.extend(res)
        else:
            try:
                msg = _fetch_file(conn, r_path, l_path, logger, overwrite)
                statuses.append(msg)
            except Exception as e:
                statuses.append(f"err:{name}:{e}")
    
    return statuses


def download_hit(hit: Dict, server, dest_dir: str, overwrite: str, logger, all_cfgs: List = None, recipe_dest: str = None):
    """Download data files (recursively), then recipe."""
    role = server.role
    remote_path = hit.get("path")
    if not remote_path:
        return {"status": "error", "reason": "no path"}

    conn = None
    if server.use_local_fs:
        # Local source
        rp = os.path.join(server.root, remote_path.strip("/")) # strip leading /
        if not os.path.exists(rp):
             return {"status": "error", "reason": "not found"}
        
        if os.path.isfile(rp):
            # Singe file download case?
            # If hit path points to a file, we put it in dest_dir?
            # demo_export says "level": "folder" normally.
            # If it is a file, copy to dest_dir/filename
            fn = os.path.basename(rp)
            dst = os.path.join(dest_dir, fn)
            ensure_dir(dest_dir)
            try:
                shutil.copy2(rp, dst)
                statuses = ["ok"]
            except Exception as e:
                statuses = [f"err:{e}"]
        else:
            # Directory
            statuses = _download_tree_local(rp, dest_dir, overwrite)
        
        data_status = {"status": "ok" if all(s in ("ok", "skip") for s in statuses) else "partial", "files": len(statuses)}
        
    else:
        # Remote FTP
        # Setup connection
        try:
            conn = RobustFTP(
                server.ip,
                server.user,
                server.password,
                port=server.port,
                timeout=server.timeout,
                op_deadline=server.op_deadline,
                logger=logger,
            )
            
            # Check if remote_path is root-relative
            # We don't 'cwd' here to avoid state confusion, or we do?
            # usage of _download_tree_remote expects absolute path or consistent path.
            # RobustFTP setup does not CWD.
            
            # Use remote_path as is?
            # servers.txt root usually "/"
            # path "Film List/as0001"
            
            statuses = _download_tree_remote(conn, remote_path, dest_dir, logger, overwrite)
            
            data_status = {"status": "ok" if all(s in ("ok", "skip") for s in statuses) else "partial", "files": len(statuses)}
            
        except Exception as e:
            return {"status": "error", "reason": f"ftp_connect:{e}"}
        finally:
            if conn:
                conn.close()

    # Download recipe if linked
    recipe_status = None
    if hit.get("recipe_paths") and recipe_dest:
        recipe_primary = hit.get("recipe_primary") or hit["recipe_paths"][0]
        rsv = hit.get("recipe_server")
        film_cfg = None
        if all_cfgs:
            if rsv:
                film_cfg = next((c for c in all_cfgs if c.name == rsv), None)
            if not film_cfg:
                film_cfg = next((c for c in all_cfgs if c.role == "film"), None)
        
        if film_cfg:
             # Logic for recipe download - usually specific file strategy.ini
             # Re-use similar connection logic or existing helpers
             if film_cfg.use_local_fs:
                 ok = _copy_recipe_local(recipe_primary, film_cfg.root, recipe_dest)
                 recipe_status = "ok" if ok else "error"
             else:
                 try:
                     c2 = RobustFTP(
                        film_cfg.ip, film_cfg.user, film_cfg.password,
                        port=film_cfg.port, timeout=film_cfg.timeout,
                        op_deadline=film_cfg.op_deadline, logger=logger
                     )
                     ok = _download_recipe_ftp(c2, recipe_primary, recipe_dest)
                     c2.close()
                     recipe_status = "ok" if ok else "error"
                 except Exception:
                     recipe_status = "error"
        else:
            recipe_status = "error"

    out = data_status
    if recipe_status:
        out["recipe_status"] = recipe_status
    return out
