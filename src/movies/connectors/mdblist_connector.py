"""MDBList Connector: Fetches multi-platform ratings (IMDb, Rotten Tomatoes, Metacritic, Letterboxd, Trakt)."""
from __future__ import annotations

from typing import Any

import requests

from movies.models import Setting


class MDBListConnector:
    """Connector for MDBList ratings API."""

    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = (api_key if api_key is not None else Setting.get("MDBLIST_APIKEY", "")).strip()

    def test_connection(self) -> dict[str, Any]:
        data = self.get_ratings(tmdb_id=286217, media_type="movie")
        return {
            "ok": True,
            "sample_title": data.get("title", "The Martian"),
            "mdblist_score": data.get("mdblist_score"),
            "ratings_count": len(data.get("ratings", [])),
        }

    def get_ratings(self, tmdb_id: int, media_type: str = "movie") -> dict[str, Any]:
        """Fetch aggregated scores from MDBList by TMDB ID."""
        if not self.api_key or not tmdb_id:
            return {}

        m_param = "show" if media_type == "tv" else "movie"
        url = f"https://api.mdblist.com/tmdb/{m_param}/{tmdb_id}"
        try:
            resp = requests.get(
                url,
                params={"apikey": self.api_key},
                headers={"User-Agent": self.USER_AGENT, "Accept": "application/json"},
                timeout=10,
            )
            if resp.status_code != 200:
                # Fallback endpoint
                resp = requests.get(
                    "https://mdblist.com/api/",
                    params={"apikey": self.api_key, "tm": tmdb_id, "m": m_param},
                    headers={"User-Agent": self.USER_AGENT, "Accept": "application/json"},
                    timeout=10,
                )
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return {}

        raw_ratings = data.get("ratings") or []
        parsed_ratings = []
        imdb_rating = None
        rt_score = None
        popcorn_score = None
        metacritic_score = None
        trakt_score = None
        letterboxd_score = None
        tmdb_score = None

        for r in raw_ratings:
            src = (r.get("source") or "").lower()
            val = r.get("value")
            score = r.get("score")
            if val is None and score is None:
                continue
            parsed_ratings.append(
                {
                    "source": src,
                    "value": val,
                    "score": score,
                    "votes": r.get("votes"),
                }
            )
            if src == "imdb" and val is not None:
                imdb_rating = float(val)
            elif src == "tomatoes" and val is not None:
                rt_score = int(val)
            elif src in ("popcorn", "tomatoesaudience") and val is not None:
                popcorn_score = int(val)
            elif src == "metacritic" and val is not None:
                metacritic_score = int(val)
            elif src == "trakt" and val is not None:
                trakt_score = int(val)
            elif src == "letterboxd" and val is not None:
                letterboxd_score = float(val)
            elif src == "tmdb" and val is not None:
                tmdb_score = float(val)

        return {
            "title": data.get("title"),
            "imdb_id": data.get("imdbid"),
            "mdblist_score": data.get("score"),
            "imdb_rating": imdb_rating,
            "rt_score": rt_score,
            "popcorn_score": popcorn_score,
            "metacritic_score": metacritic_score,
            "trakt_score": trakt_score,
            "letterboxd_score": letterboxd_score,
            "tmdb_score": tmdb_score,
            "ratings": parsed_ratings,
        }
