"""AList Connector: Handles authentication, directory browsing, video scanning, and stream URL generation."""
from __future__ import annotations

import re
import urllib.parse
from typing import Any

import requests

from movies.models import Setting

VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".ts", ".m2ts", ".wmv", ".flv", ".webm"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

# Keywords indicating non-movie/non-TV folders (software, books, music, stock footage, games)
NON_MEDIA_KEYWORDS = [
    "情绪流龙头战法",
    "游戏一键汉化",
    "hackintosh",
    "stata",
    "Billboard",
    "无损FLAC",
    "VMware",
    "Adobe",
    "Kindle书库",
    "网络文学",
    "亚马逊原版电子书",
    "网络小说",
    "科幻小说",
    "城市地标风光",
    "航拍太原",
    "treesize",
    "深度学习入门",
    "Squad",
    "Qwen",
    "纪念碑谷",
    "C++ Primer",
    "ComfyUI",
    "精选壁纸",
    "Planet Zoo",
    "动物园之星",
    "SolidWorks",
    "图吧工具箱",
    "DaVinci Resolve",
    "Steve Lacy",
    "零售机横评",
]


class AListConnector:
    """Connector for interacting with a local or remote AList server."""

    _token_cache: dict[tuple[str, str, str], str] = {}

    def __init__(
        self,
        base_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self.base_url = (base_url or Setting.get("ALIST_URL", "http://localhost:5244")).rstrip("/")
        self.username = username if username is not None else Setting.get("ALIST_USERNAME", "admin")
        self.password = password if password is not None else Setting.get("ALIST_PASSWORD", "")

    def get_token(self, force_refresh: bool = False) -> str:
        cache_key = (self.base_url, self.username, self.password)
        if not force_refresh and cache_key in self._token_cache:
            return self._token_cache[cache_key]

        resp = requests.post(
            f"{self.base_url}/api/auth/login",
            json={"username": self.username, "password": self.password},
            timeout=10,
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") != 200 or not payload.get("data", {}).get("token"):
            raise RuntimeError(f"AList 登录失败: {payload.get('message', '未知错误')}")
        token = payload["data"]["token"]
        self._token_cache[cache_key] = token
        return token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": self.get_token(),
            "Content-Type": "application/json; charset=utf-8",
        }

    def test_connection(self) -> dict[str, Any]:
        token = self.get_token(force_refresh=True)
        items = self.list_dir("/")
        return {
            "ok": True,
            "base_url": self.base_url,
            "root_mounts": [item.get("name") for item in items],
            "token_preview": f"{token[:12]}...",
        }

    def list_dir(self, path: str = "/", refresh: bool = False) -> list[dict[str, Any]]:
        norm_path = "/" + path.strip("/") if path.strip("/") else "/"
        resp = requests.post(
            f"{self.base_url}/api/fs/list",
            headers=self._headers(),
            json={
                "path": norm_path,
                "password": "",
                "page": 1,
                "per_page": 0,
                "refresh": refresh,
            },
            timeout=15,
        )
        data = resp.json()
        if data.get("code") == 401:
            self.get_token(force_refresh=True)
            resp = requests.post(
                f"{self.base_url}/api/fs/list",
                headers=self._headers(),
                json={
                    "path": norm_path,
                    "password": "",
                    "page": 1,
                    "per_page": 0,
                    "refresh": refresh,
                },
                timeout=15,
            )
            data = resp.json()

        if data.get("code") != 200:
            return []
        content = (data.get("data") or {}).get("content") or []
        results = []
        for item in content:
            child_path = f"{norm_path.rstrip('/')}/{item['name']}"
            item_copy = dict(item)
            item_copy["path"] = child_path
            results.append(item_copy)
        return results

    def get_file_info(self, path: str) -> dict[str, Any]:
        norm_path = "/" + path.strip("/")
        resp = requests.post(
            f"{self.base_url}/api/fs/get",
            headers=self._headers(),
            json={"path": norm_path, "password": ""},
            timeout=15,
        )
        data = resp.json()
        if data.get("code") == 401:
            self.get_token(force_refresh=True)
            resp = requests.post(
                f"{self.base_url}/api/fs/get",
                headers=self._headers(),
                json={"path": norm_path, "password": ""},
                timeout=15,
            )
            data = resp.json()
        if data.get("code") != 200:
            raise RuntimeError(f"无法获取 AList 文件信息 ({norm_path}): {data.get('message')}")
        return data.get("data") or {}

    def get_stream_url(self, path: str) -> str:
        """Build a signed direct stream URL (/d/<path>?sign=...) playable by MPC-HC."""
        norm_path = "/" + path.strip("/")
        try:
            info = self.get_file_info(norm_path)
            sign = info.get("sign") or ""
        except Exception:
            sign = ""
        encoded_path = urllib.parse.quote(norm_path, safe="/")
        if sign:
            return f"{self.base_url}/d{encoded_path}?sign={ urllib.parse.quote(sign, safe='=:') }"
        return f"{self.base_url}/d{encoded_path}"

    @staticmethod
    def is_video_file(filename: str) -> bool:
        lower = filename.lower()
        return any(lower.endswith(ext) for ext in VIDEO_EXTENSIONS)

    @staticmethod
    def is_non_media_name(name: str) -> bool:
        lower = name.lower()
        for kw in NON_MEDIA_KEYWORDS:
            if kw.lower() in lower:
                return True
        if lower.endswith((".zip", ".7z", ".rar", ".exe", ".pdf", ".epub", ".txt")):
            return True
        return False

    @staticmethod
    def extract_quality_badge(text: str) -> str:
        tags = []
        upper = text.upper()
        if "2160P" in upper or "4K" in upper or "UHD" in upper:
            tags.append("4K UHD")
        elif "1080P" in upper:
            tags.append("1080P")
        if "REMUX" in upper:
            tags.append("REMUX")
        if "DV" in upper or "DOVI" in upper or "杜比视界" in text:
            tags.append("Dolby Vision")
        elif "HDR" in upper:
            tags.append("HDR")
        if "60FPS" in upper or "60帧" in text:
            tags.append("60FPS")
        if "ATMOS" in upper:
            tags.append("Atmos")
        return " · ".join(tags[:3]) if tags else "HD"

    @staticmethod
    def parse_season_episode(name: str, default_season: int = 1) -> tuple[int, int] | None:
        """Extract (season_number, episode_number) from a video filename."""
        # Standard S01E02 or s1e2
        m = re.search(r"[Ss](\d{1,2})\s*[.\-_ ]*[Ee](\d{1,3})", name)
        if m:
            return int(m.group(1)), int(m.group(2))

        # E01 / EP01
        m_ep = re.search(r"(?:[Ee][Pp]?|第)\s*(\d{1,3})\s*(?:集|\b)", name)
        if m_ep:
            return default_season, int(m_ep.group(1))

        # Pure numeric filename like "01.mp4", "08 4K.mp4", "1.mp4", "12.mkv"
        stem = re.sub(r"\.[a-zA-Z0-9]+$", "", name).strip()
        m_num = re.match(r"^0*(\d{1,3})(?:\s+4[kK]|\s+1080[pP]|\s*【.*】)?$", stem)
        if m_num:
            ep_num = int(m_num.group(1))
            if 1 <= ep_num <= 200:
                return default_season, ep_num

        return None

    @staticmethod
    def parse_season_folder_number(folder_name: str) -> int | None:
        """Detect if a subfolder represents a season (e.g. 'Season 1', 'S02', '第 3 季', '第二季')."""
        m = re.search(r"(?:Season|S)\s*0*(\d{1,2})\b", folder_name, re.IGNORECASE)
        if m:
            return int(m.group(1))
        m_cn_num = re.search(r"第\s*(\d{1,2})\s*季", folder_name)
        if m_cn_num:
            return int(m_cn_num.group(1))
        cn_map = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
        m_cn = re.search(r"第([一二三四五六七八九十])季", folder_name)
        if m_cn:
            return cn_map.get(m_cn.group(1))
        return None

    def inspect_media_entry(self, entry: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Inspect a top-level item in AList scan directory and return 0, 1, or more
        structured media candidates (handles multi-movie collection folders too).
        """
        name = entry.get("name", "")
        path = entry.get("path", "")
        is_dir = bool(entry.get("is_dir"))

        if self.is_non_media_name(name):
            return []

        if not is_dir:
            if not self.is_video_file(name):
                return []
            # Skip generic unnamed clips like "2026 1080p AMZN WEB-DL DDP5 1 - LYZM.mkv" if no title
            if re.match(r"^202\d\s+1080p", name, re.IGNORECASE):
                return []
            return [
                {
                    "raw_name": name,
                    "alist_path": path,
                    "is_dir": False,
                    "media_type_hint": "movie",
                    "video_files": [
                        {
                            "name": name,
                            "path": path,
                            "size": entry.get("size", 0),
                            "season": None,
                            "episode": None,
                        }
                    ],
                    "local_artwork": {},
                    "quality_badge": self.extract_quality_badge(name),
                }
            ]

        children = self.list_dir(path)
        if not children:
            return []

        # Collect local artwork if present in folder (e.g. logo.png, poster.jpg, backdrop.jpg)
        local_artwork: dict[str, str] = {}
        for ch in children:
            if not ch.get("is_dir"):
                lower_n = ch["name"].lower()
                if lower_n in ("logo.png", "clearlogo.png"):
                    local_artwork["logo"] = self.get_stream_url(ch["path"])
                elif lower_n in ("poster.jpg", "poster.png"):
                    local_artwork["poster"] = self.get_stream_url(ch["path"])
                elif lower_n in ("backdrop.jpg", "fanart.jpg", "background.jpg"):
                    local_artwork["backdrop"] = self.get_stream_url(ch["path"])

        direct_videos = [ch for ch in children if not ch.get("is_dir") and self.is_video_file(ch["name"])]
        subdirs = [ch for ch in children if ch.get("is_dir")]

        # Check if this is a multi-movie collection folder like "【流.浪.地.球】全2部..."
        if not direct_videos and subdirs and ("全2部" in name or "合集" in name or "系列" in name and "暗黑" not in name):
            multi_results = []
            for sd in subdirs:
                sd_vids = [
                    x for x in self.list_dir(sd["path"]) if not x.get("is_dir") and self.is_video_file(x["name"])
                ]
                if sd_vids:
                    multi_results.append(
                        {
                            "raw_name": sd["name"],
                            "alist_path": sd["path"],
                            "is_dir": True,
                            "media_type_hint": "movie" if len(sd_vids) == 1 else "tv",
                            "video_files": [
                                {
                                    "name": v["name"],
                                    "path": v["path"],
                                    "size": v.get("size", 0),
                                    "season": None,
                                    "episode": None,
                                }
                                for v in sd_vids
                            ],
                            "local_artwork": local_artwork,
                            "quality_badge": self.extract_quality_badge(sd["name"] + " " + sd_vids[0]["name"]),
                        }
                    )
            if multi_results:
                return multi_results

        # Check season hint in main folder name (e.g. "绝命毒师 第4季 4K")
        folder_season_hint = self.parse_season_folder_number(name) or 1

        all_video_files: list[dict[str, Any]] = []
        season_folders_found = 0

        for v in direct_videos:
            se = self.parse_season_episode(v["name"], default_season=folder_season_hint)
            all_video_files.append(
                {
                    "name": v["name"],
                    "path": v["path"],
                    "size": v.get("size", 0),
                    "season": se[0] if se else None,
                    "episode": se[1] if se else None,
                }
            )

        for sd in subdirs:
            sd_name = sd["name"]
            if any(skip in sd_name for skip in ["没有字幕", "热门影视", "更多资源", "解锁", "提示："]):
                continue
            s_num = self.parse_season_folder_number(sd_name)
            if s_num is not None:
                season_folders_found += 1
            sd_children = self.list_dir(sd["path"])
            sd_videos = [x for x in sd_children if not x.get("is_dir") and self.is_video_file(x["name"])]
            # Check one level deeper if needed (e.g. 黑暗荣耀 -> 4k -> S01/files)
            if not sd_videos:
                for sub_sd in [x for x in sd_children if x.get("is_dir")]:
                    sub_s_num = self.parse_season_folder_number(sub_sd["name"]) or s_num or folder_season_hint
                    sub_vids = [
                        x
                        for x in self.list_dir(sub_sd["path"])
                        if not x.get("is_dir") and self.is_video_file(x["name"])
                    ]
                    for v in sub_vids:
                        se = self.parse_season_episode(v["name"], default_season=sub_s_num)
                        all_video_files.append(
                            {
                                "name": v["name"],
                                "path": v["path"],
                                "size": v.get("size", 0),
                                "season": se[0] if se else sub_s_num,
                                "episode": se[1] if se else None,
                            }
                        )
            else:
                effective_season = s_num or folder_season_hint
                for v in sd_videos:
                    se = self.parse_season_episode(v["name"], default_season=effective_season)
                    all_video_files.append(
                        {
                            "name": v["name"],
                            "path": v["path"],
                            "size": v.get("size", 0),
                            "season": se[0] if se else (effective_season if len(sd_videos) > 1 else None),
                            "episode": se[1] if se else None,
                        }
                    )

        if not all_video_files:
            return []

        # Deduplicate episodes if folder has both "01.mp4" and "01 4K.mp4" or ".mkv" (prefer larger file)
        episode_files = [f for f in all_video_files if f["episode"] is not None]
        is_tv = (
            season_folders_found > 0
            or len(episode_files) >= 2
            or any(k in name for k in ["季", "全集", "集全", "全系列", "BL剧"])
        )
        # Special case: folder with two cuts of the same movie (e.g. 蜘蛛侠 4K.mp4 and 4K正式版.mp4)
        if not season_folders_found and len(all_video_files) <= 3 and not episode_files:
            is_tv = False

        if is_tv and episode_files:
            deduped: dict[tuple[int, int], dict[str, Any]] = {}
            for f in episode_files:
                key = (f["season"] or 1, f["episode"])
                if key not in deduped or (f.get("size", 0) > deduped[key].get("size", 0)):
                    deduped[key] = f
            all_video_files = [deduped[k] for k in sorted(deduped.keys())]
        else:
            # Sort movie files by size descending so the main feature film comes first
            all_video_files.sort(key=lambda x: x.get("size", 0), reverse=True)

        sample_names = " ".join([name] + [f["name"] for f in all_video_files[:3]])
        return [
            {
                "raw_name": name,
                "alist_path": path,
                "is_dir": True,
                "media_type_hint": "tv" if is_tv else "movie",
                "video_files": all_video_files,
                "local_artwork": local_artwork,
                "quality_badge": self.extract_quality_badge(sample_names),
            }
        ]
