"""TMDB Connector: Fetches posters, widescreen backdrops, official logos, season posters, and episode stills/ratings."""
from __future__ import annotations

from typing import Any

import requests

from movies.models import Setting

TMDB_API_BASE = "https://api.themoviedb.org/3"
TMDB_IMG_BASE = "https://image.tmdb.org/t/p"


class TMDBConnector:
    """Connector for The Movie Database (TMDB) v3 API."""

    def __init__(self, token: str | None = None) -> None:
        self.token = (token if token is not None else Setting.get("TMDB_TOKEN", "")).strip()

    def _request(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.token:
            raise RuntimeError("未配置 TMDB 密钥 (TMDB_TOKEN)")

        query = dict(params or {})
        headers = {"Accept": "application/json"}
        if self.token.startswith("eyJ") or len(self.token) > 45:
            headers["Authorization"] = f"Bearer {self.token}"
        else:
            query["api_key"] = self.token

        resp = requests.get(
            f"{TMDB_API_BASE}{endpoint}",
            headers=headers,
            params=query,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def img_url(path: str | None, size: str = "w780") -> str | None:
        if not path:
            return None
        if path.startswith("http"):
            return path
        return f"{TMDB_IMG_BASE}/{size}{path}"

    def test_connection(self) -> dict[str, Any]:
        data = self._request("/configuration")
        return {
            "ok": True,
            "base_url": data.get("images", {}).get("secure_base_url", TMDB_IMG_BASE),
        }

    def search(
        self,
        query: str,
        media_type: str | None = None,
        year: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search TMDB for movie or TV series candidates."""
        if not query or not query.strip():
            return []
        q = query.strip()

        endpoints = []
        if media_type == "movie":
            endpoints = [("/search/movie", "movie"), ("/search/tv", "tv")]
        elif media_type == "tv":
            endpoints = [("/search/tv", "tv"), ("/search/movie", "movie")]
        else:
            endpoints = [("/search/multi", "multi")]

        results: list[dict[str, Any]] = []
        seen: set[tuple[str, int]] = set()

        for ep, m_type in endpoints:
            params: dict[str, Any] = {"query": q, "language": "zh-CN", "include_adult": "false"}
            if year and len(str(year)) == 4:
                if m_type == "movie":
                    params["year"] = str(year)
                elif m_type == "tv":
                    params["first_air_date_year"] = str(year)

            try:
                data = self._request(ep, params)
                items = data.get("results") or []
                # If filtering by year yielded nothing, retry without year filter
                if not items and year:
                    params.pop("year", None)
                    params.pop("first_air_date_year", None)
                    data = self._request(ep, params)
                    items = data.get("results") or []
            except Exception:
                items = []

            for item in items:
                resolved_type = item.get("media_type") if m_type == "multi" else m_type
                if resolved_type not in ("movie", "tv"):
                    continue
                tid = item.get("id")
                if not tid or (resolved_type, tid) in seen:
                    continue
                seen.add((resolved_type, tid))
                date_str = item.get("release_date") or item.get("first_air_date") or ""
                results.append(
                    {
                        "tmdb_id": tid,
                        "media_type": resolved_type,
                        "title": item.get("title") or item.get("name") or q,
                        "original_title": item.get("original_title") or item.get("original_name") or "",
                        "year": date_str[:4] if date_str else "",
                        "release_date": date_str,
                        "overview": item.get("overview") or "",
                        "poster_url": self.img_url(item.get("poster_path"), "w500"),
                        "backdrop_url": self.img_url(item.get("backdrop_path"), "w1280"),
                        "rating": round(float(item.get("vote_average") or 0.0), 1),
                    }
                )
            if results and media_type in ("movie", "tv"):
                break

        return results[:12]

    @classmethod
    def _pick_images(cls, items: list[dict[str, Any]], size: str = "w500", limit: int = 8) -> list[str]:
        """Sort TMDB images prioritizing Chinese (zh/cn), then English (en), then null."""
        def lang_rank(img: dict[str, Any]) -> tuple[int, float]:
            iso = (img.get("iso_639_1") or "").lower()
            # Prefer PNG over SVG for logos
            file_path = (img.get("file_path") or "").lower()
            is_svg = 1 if file_path.endswith(".svg") else 0
            if iso in ("zh", "cn"):
                lang_score = 0
            elif iso == "en":
                lang_score = 1
            elif not iso:
                lang_score = 2
            else:
                lang_score = 3
            return (is_svg, lang_score, -float(img.get("vote_average") or 0.0))

        sorted_items = sorted(items or [], key=lang_rank)
        urls = []
        for img in sorted_items:
            u = cls.img_url(img.get("file_path"), size)
            if u and u not in urls:
                urls.append(u)
            if len(urls) >= limit:
                break
        return urls

    def get_details(self, tmdb_id: int, media_type: str = "movie") -> dict[str, Any]:
        """Fetch full movie or TV details including logos, posters, backdrops, and seasons list."""
        m_type = "tv" if media_type == "tv" else "movie"
        data = self._request(
            f"/{m_type}/{tmdb_id}",
            {
                "language": "zh-CN",
                "append_to_response": "images,external_ids",
                "include_image_language": "zh,cn,en,null",
            },
        )

        # Fallback overview if zh-CN overview is empty
        overview = data.get("overview") or ""
        if not overview:
            try:
                en_data = self._request(f"/{m_type}/{tmdb_id}", {"language": "en-US"})
                overview = en_data.get("overview") or ""
            except Exception:
                pass

        images = data.get("images") or {}
        logos = self._pick_images(images.get("logos") or [], size="w500", limit=8)
        posters = self._pick_images(images.get("posters") or [], size="w780", limit=8)
        backdrops = self._pick_images(images.get("backdrops") or [], size="original", limit=8)

        primary_poster = self.img_url(data.get("poster_path"), "w780") or (posters[0] if posters else None)
        primary_backdrop = self.img_url(data.get("backdrop_path"), "original") or (
            backdrops[0] if backdrops else primary_poster
        )
        primary_logo = logos[0] if logos else None

        if primary_poster and primary_poster not in posters:
            posters.insert(0, primary_poster)
        if primary_backdrop and primary_backdrop not in backdrops:
            backdrops.insert(0, primary_backdrop)

        date_str = data.get("release_date") or data.get("first_air_date") or ""
        genres = [g["name"] for g in (data.get("genres") or []) if g.get("name")]
        runtime = data.get("runtime")
        if not runtime and data.get("episode_run_time"):
            runtime = data["episode_run_time"][0]

        ext_ids = data.get("external_ids") or {}
        imdb_id = data.get("imdb_id") or ext_ids.get("imdb_id")

        seasons_summary = []
        if m_type == "tv":
            for s in data.get("seasons") or []:
                s_num = s.get("season_number")
                if s_num is None or s_num < 0:
                    continue
                seasons_summary.append(
                    {
                        "season_number": s_num,
                        "name": s.get("name") or f"第 {s_num} 季",
                        "overview": s.get("overview") or "",
                        "poster_url": self.img_url(s.get("poster_path"), "w500") or primary_poster,
                        "air_date": s.get("air_date") or "",
                        "episode_count": s.get("episode_count") or 0,
                        "vote_average": float(s.get("vote_average") or 0.0),
                    }
                )

        return {
            "tmdb_id": tmdb_id,
            "imdb_id": imdb_id,
            "media_type": m_type,
            "title": data.get("title") or data.get("name") or "",
            "original_title": data.get("original_title") or data.get("original_name") or "",
            "year": date_str[:4] if date_str else "",
            "release_date": date_str,
            "overview": overview,
            "tagline": data.get("tagline") or "",
            "genres": ", ".join(genres),
            "status": data.get("status") or "",
            "runtime": runtime,
            "tmdb_rating": float(data.get("vote_average") or 0.0),
            "poster_url": primary_poster,
            "backdrop_url": primary_backdrop,
            "logo_url": primary_logo,
            "alt_logos": logos,
            "alt_posters": posters,
            "alt_backdrops": backdrops,
            "seasons_summary": seasons_summary,
        }

    def get_season_details(
        self,
        tmdb_id: int,
        season_number: int,
        fallback_poster: str | None = None,
        fallback_backdrop: str | None = None,
    ) -> dict[str, Any]:
        """Fetch a TV season's poster and all episodes with their still images, titles, and ratings."""
        data = self._request(
            f"/tv/{tmdb_id}/season/{season_number}",
            {"language": "zh-CN"},
        )
        season_poster = self.img_url(data.get("poster_path"), "w500") or fallback_poster
        episodes = []
        for ep in data.get("episodes") or []:
            ep_num = ep.get("episode_number")
            if ep_num is None:
                continue
            still_url = self.img_url(ep.get("still_path"), "w500") or fallback_backdrop or season_poster
            episodes.append(
                {
                    "season_number": season_number,
                    "episode_number": ep_num,
                    "title": ep.get("name") or f"第 {ep_num} 集",
                    "overview": ep.get("overview") or "",
                    "still_url": still_url,
                    "rating": round(float(ep.get("vote_average") or 0.0), 1),
                    "runtime": ep.get("runtime"),
                    "air_date": ep.get("air_date") or "",
                }
            )
        return {
            "season_number": season_number,
            "name": data.get("name") or f"第 {season_number} 季",
            "overview": data.get("overview") or "",
            "poster_url": season_poster,
            "air_date": data.get("air_date") or "",
            "episode_count": len(episodes),
            "vote_average": round(float(data.get("vote_average") or 0.0), 1),
            "episodes": episodes,
        }
