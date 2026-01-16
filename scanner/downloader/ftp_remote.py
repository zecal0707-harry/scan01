import ftplib
import socket
import threading
from typing import Callable


class RobustFTP:
    def __init__(self, host, user, passwd, port=21, timeout=15, op_deadline=25.0, logger=None):
        self.host = host
        self.user = user
        self.passwd = passwd
        self.port = port
        self.timeout = timeout
        self.op_deadline = op_deadline
        self.log = logger
        self.ftp = ftplib.FTP()
        self.ftp.connect(self.host, self.port, timeout=self.timeout)
        self.ftp.login(self.user, self.passwd)
        self.ftp.set_pasv(True)
        try:
            self.ftp.sock.settimeout(self.timeout)
            self.ftp.sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        except Exception:
            pass

    def close(self):
        try:
            self.ftp.quit()
        except Exception:
            try:
                self.ftp.close()
            except Exception:
                pass

    def cwd(self, path):
        return self.ftp.cwd(path)

    def nlst(self, *args):
        return self.ftp.nlst(*args)

    def retrbinary(self, cmd: str, cb: Callable, blocksize=8192):
        out = {}
        err = {}

        def run():
            try:
                out["v"] = self.ftp.retrbinary(cmd, cb, blocksize=blocksize)
            except Exception as e:
                err["e"] = e

        t = threading.Thread(target=run, daemon=True)
        t.start()
        t.join(self.op_deadline)
        if t.is_alive():
            try:
                self.ftp.close()
            except Exception:
                pass
            t.join(0.05)
            raise TimeoutError("FTP op deadline exceeded")
        if "e" in err:
            raise err["e"]
        return out.get("v")

    def mlsd(self, path="", facts=None):
        return self.ftp.mlsd(path, facts=facts)

    def rename(self, from_name, to_name):
        return self.ftp.rename(from_name, to_name)
