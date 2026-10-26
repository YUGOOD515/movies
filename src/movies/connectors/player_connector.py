"""Player Connector: Invokes local MPC-HC (C:\\Program Files\\MPC-HC\\mpc-hc64.exe) to play AList streams."""
from __future__ import annotations

import subprocess
import urllib.parse
from pathlib import Path
from typing import Any

from movies.models import Setting


class PlayerConnector:
    """Connector for launching the local MPC-HC 64-bit media player."""

    DEFAULT_PATH = r"C:\Program Files\MPC-HC\mpc-hc64.exe"

    def __init__(self, player_path: str | None = None) -> None:
        self.player_path = (player_path or Setting.get("MPC_HC_PATH", self.DEFAULT_PATH)).strip()

    def is_installed(self) -> bool:
        return Path(self.player_path).is_file()

    def test_connection(self) -> dict[str, Any]:
        exists = self.is_installed()
        return {
            "ok": exists,
            "player_path": self.player_path,
            "message": "MPC-HC 播放器路径已就绪" if exists else f"未找到播放器文件: {self.player_path}",
        }

    def launch(self, stream_url: str, title: str | None = None) -> dict[str, Any]:
        """Launch MPC-HC with the given HTTP/HTTPS stream URL."""
        if not stream_url.startswith(("http://", "https://")):
            raise ValueError("仅支持合法的 HTTP/HTTPS 播放链接")

        exe_path = Path(self.player_path)
        if not exe_path.is_file():
            raise FileNotFoundError(f"找不到 MPC-HC 播放器: {self.player_path}")

        cmd = [str(exe_path), stream_url]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
             close_fds=True,
        )
        protocol_url = f"mpchc://play?url={urllib.parse.quote(stream_url, safe='')}"
        return {
            "ok": True,
            "pid": proc.pid,
            "player_path": str(exe_path),
            "stream_url": stream_url,
            "protocol_url": protocol_url,
            "title": title or "",
        }
