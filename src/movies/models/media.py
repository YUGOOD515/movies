"""Database models for AList Media Center (MVC Model Layer)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from movies.config import DEFAULT_SETTINGS
from movies.extensions import db


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Setting(db.Model):
    """Key-value configuration store persisted in SQLite."""

    __tablename__ = "settings"

    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text, nullable=False, default="")
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    @classmethod
    def get(cls, key: str, default: str | None = None) -> str:
        try:
            row = db.session.get(cls, key)
            if row is not None and row.value != "":
                return row.value
        except RuntimeError:
            pass
        if default is not None:
            return default
        return DEFAULT_SETTINGS.get(key, "")

    @classmethod
    def get_all(cls) -> dict[str, str]:
        merged = dict(DEFAULT_SETTINGS)
        rows = cls.query.all()
        for row in rows:
            if row.value is not None and row.value != "":
                merged[row.key] = row.value
        return merged

    @classmethod
    def set_many(cls, values: dict[str, Any]) -> None:
        for key, val in values.items():
            if val is None:
                continue
            str_val = str(val).strip()
            row = db.session.get(cls, key)
            if row is None:
                row = cls(key=key, value=str_val)
                db.session.add(row)
            else:
                row.value = str_val
        db.session.commit()


class MediaItem(db.Model):
    """Represents a Movie or TV Series managed in the library."""

    __tablename__ = "media_items"

    id = db.Column(db.Integer, primary_key=True)
    tmdb_id = db.Column(db.Integer, index=True, nullable=True)
    imdb_id = db.Column(db.String(32), nullable=True)
    media_type = db.Column(db.String(16), nullable=False, default="movie", index=True)  # 'movie' | 'tv'

    # Titles & basic metadata
    title = db.Column(db.String(255), nullable=False)
    original_title = db.Column(db.String(255), nullable=True)
    year = db.Column(db.String(16), nullable=True)
    release_date = db.Column(db.String(32), nullable=True)
    overview = db.Column(db.Text, nullable=True)
    tagline = db.Column(db.String(500), nullable=True)
    genres = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(64), nullable=True)
    runtime = db.Column(db.Integer, nullable=True)

    # Artwork URLs (Poster, Widescreen Backdrop, Transparent Logo)
    poster_url = db.Column(db.String(500), nullable=True)
    backdrop_url = db.Column(db.String(500), nullable=True)
    logo_url = db.Column(db.String(500), nullable=True)
    alt_logos_json = db.Column(db.Text, nullable=True, default="[]")
    alt_posters_json = db.Column(db.Text, nullable=True, default="[]")
    alt_backdrops_json = db.Column(db.Text, nullable=True, default="[]")

    # Multi-platform ratings (TMDB + MDBList)
    tmdb_rating = db.Column(db.Float, nullable=True, default=0.0)
    imdb_rating = db.Column(db.Float, nullable=True)
    rt_score = db.Column(db.Integer, nullable=True)
    popcorn_score = db.Column(db.Integer, nullable=True)
    metacritic_score = db.Column(db.Integer, nullable=True)
    trakt_score = db.Column(db.Integer, nullable=True)
    letterboxd_score = db.Column(db.Float, nullable=True)
    mdblist_score = db.Column(db.Integer, nullable=True)
    ratings_json = db.Column(db.Text, nullable=True, default="[]")

    # AList source & DeepSeek AI De-obfuscation metadata
    alist_path = db.Column(db.String(1000), nullable=False, index=True)
    video_path = db.Column(db.String(1000), nullable=True)
    raw_alist_name = db.Column(db.String(500), nullable=False)
    ai_guessed_title = db.Column(db.String(255), nullable=True)
    ai_obfuscation_type = db.Column(db.String(64), nullable=True, default="标准命名")
    ai_explanation = db.Column(db.Text, nullable=True)
    alt_sources_json = db.Column(db.Text, nullable=True, default="[]")
    quality_badge = db.Column(db.String(128), nullable=True, default="4K UHD")

    # Admin & Watch Progress Tracking
    is_featured = db.Column(db.Boolean, default=False, index=True)
    featured_order = db.Column(db.Integer, default=100)
    is_visible = db.Column(db.Boolean, default=True, index=True)
    active_season_number = db.Column(db.Integer, default=1)

    current_season = db.Column(db.Integer, default=1)
    current_episode = db.Column(db.Integer, default=1)
    progress_percent = db.Column(db.Integer, default=0)
    last_watched_at = db.Column(db.DateTime, nullable=True)
    play_count = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    seasons = db.relationship(
        "Season",
        backref="media",
        lazy="select",
        cascade="all, delete-orphan",
        order_by="Season.season_number",
    )
    episodes = db.relationship(
        "Episode",
        backref="media",
        lazy="select",
        cascade="all, delete-orphan",
        order_by="Episode.season_number, Episode.episode_number",
    )

    @property
    def alt_logos(self) -> list[str]:
        try:
            return json.loads(self.alt_logos_json or "[]")
        except Exception:
            return []

    @property
    def alt_posters(self) -> list[str]:
        try:
            return json.loads(self.alt_posters_json or "[]")
        except Exception:
            return []

    @property
    def alt_backdrops(self) -> list[str]:
        try:
            return json.loads(self.alt_backdrops_json or "[]")
        except Exception:
            return []

    @property
    def alt_sources(self) -> list[dict[str, Any]]:
        try:
            return json.loads(self.alt_sources_json or "[]")
        except Exception:
            return []

    @property
    def ratings_list(self) -> list[dict[str, Any]]:
        try:
            return json.loads(self.ratings_json or "[]")
        except Exception:
            return []

    @property
    def genre_list(self) -> list[str]:
        if not self.genres:
            return []
        return [g.strip() for g in self.genres.split(",") if g.strip()]

    @property
    def watched_episodes_count(self) -> int:
        if self.media_type != "tv":
            return 1 if self.progress_percent >= 90 else 0
        return sum(1 for ep in self.episodes if ep.is_watched)

    @property
    def total_episodes_count(self) -> int:
        if self.media_type != "tv":
            return 1
        return len(self.episodes)

    @property
    def available_episodes_count(self) -> int:
        if self.media_type != "tv":
            return 1 if self.video_path else 0
        return sum(1 for ep in self.episodes if ep.alist_file_path)

    def to_dict(self, include_seasons: bool = False) -> dict[str, Any]:
        data = {
            "id": self.id,
            "tmdb_id": self.tmdb_id,
            "imdb_id": self.imdb_id,
            "media_type": self.media_type,
            "title": self.title,
            "original_title": self.original_title,
            "year": self.year,
            "release_date": self.release_date,
            "overview": self.overview,
            "tagline": self.tagline,
            "genres": self.genre_list,
            "status": self.status,
            "runtime": self.runtime,
            "poster_url": self.poster_url,
            "backdrop_url": self.backdrop_url,
            "logo_url": self.logo_url,
            "alt_logos": self.alt_logos,
            "alt_posters": self.alt_posters,
            "alt_backdrops": self.alt_backdrops,
            "tmdb_rating": round(self.tmdb_rating or 0.0, 1),
            "imdb_rating": self.imdb_rating,
            "rt_score": self.rt_score,
            "popcorn_score": self.popcorn_score,
            "metacritic_score": self.metacritic_score,
            "trakt_score": self.trakt_score,
            "letterboxd_score": self.letterboxd_score,
            "mdblist_score": self.mdblist_score,
            "ratings": self.ratings_list,
            "alist_path": self.alist_path,
            "video_path": self.video_path,
            "raw_alist_name": self.raw_alist_name,
            "ai_guessed_title": self.ai_guessed_title,
            "ai_obfuscation_type": self.ai_obfuscation_type,
            "ai_explanation": self.ai_explanation,
            "alt_sources": self.alt_sources,
            "quality_badge": self.quality_badge,
            "is_featured": self.is_featured,
            "featured_order": self.featured_order,
            "is_visible": self.is_visible,
            "active_season_number": self.active_season_number,
            "current_season": self.current_season,
            "current_episode": self.current_episode,
            "progress_percent": self.progress_percent,
            "watched_episodes_count": self.watched_episodes_count,
            "total_episodes_count": self.total_episodes_count,
            "available_episodes_count": self.available_episodes_count,
            "last_watched_at": self.last_watched_at.isoformat() if self.last_watched_at else None,
            "play_count": self.play_count,
        }
        if include_seasons:
            data["seasons"] = [s.to_dict(include_episodes=True) for s in self.seasons]
        return data


class Season(db.Model):
    """Represents a single season of a TV Series with its own Season Poster."""

    __tablename__ = "seasons"

    id = db.Column(db.Integer, primary_key=True)
    media_id = db.Column(db.Integer, db.ForeignKey("media_items.id"), nullable=False, index=True)
    season_number = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    overview = db.Column(db.Text, nullable=True)
    poster_url = db.Column(db.String(500), nullable=True)
    air_date = db.Column(db.String(32), nullable=True)
    episode_count = db.Column(db.Integer, default=0)
    vote_average = db.Column(db.Float, default=0.0)
    alist_season_path = db.Column(db.String(1000), nullable=True)

    episodes = db.relationship(
        "Episode",
        backref="season",
        lazy="select",
        cascade="all, delete-orphan",
        order_by="Episode.episode_number",
    )

    def to_dict(self, include_episodes: bool = True) -> dict[str, Any]:
        data = {
            "id": self.id,
            "media_id": self.media_id,
            "season_number": self.season_number,
            "name": self.name,
            "overview": self.overview,
            "poster_url": self.poster_url,
            "air_date": self.air_date,
            "episode_count": self.episode_count or len(self.episodes),
            "vote_average": round(self.vote_average or 0.0, 1),
            "alist_season_path": self.alist_season_path,
        }
        if include_episodes:
            data["episodes"] = [ep.to_dict() for ep in self.episodes]
        return data


class Episode(db.Model):
    """Represents a single episode of a TV Series with its Still Image, Title, Rating, and AList file."""

    __tablename__ = "episodes"

    id = db.Column(db.Integer, primary_key=True)
    media_id = db.Column(db.Integer, db.ForeignKey("media_items.id"), nullable=False, index=True)
    season_id = db.Column(db.Integer, db.ForeignKey("seasons.id"), nullable=False, index=True)
    season_number = db.Column(db.Integer, nullable=False)
    episode_number = db.Column(db.Integer, nullable=False)

    title = db.Column(db.String(255), nullable=False)
    overview = db.Column(db.Text, nullable=True)
    still_url = db.Column(db.String(500), nullable=True)  # 每一集的剧照
    rating = db.Column(db.Float, default=0.0)  # 每集的评分
    runtime = db.Column(db.Integer, nullable=True)
    air_date = db.Column(db.String(32), nullable=True)

    # Bound AList video resource
    alist_file_path = db.Column(db.String(1000), nullable=True)
    file_name = db.Column(db.String(500), nullable=True)
    file_size = db.Column(db.BigInteger, nullable=True, default=0)

    # Progress tracking
    is_watched = db.Column(db.Boolean, default=False)
    watch_progress = db.Column(db.Integer, default=0)
    last_played_at = db.Column(db.DateTime, nullable=True)

    @property
    def file_size_human(self) -> str:
        if not self.file_size:
            return ""
        gb = self.file_size / (1024**3)
        if gb >= 1.0:
            return f"{gb:.1f} GB"
        mb = self.file_size / (1024**2)
        return f"{mb:.0f} MB"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "media_id": self.media_id,
            "season_id": self.season_id,
            "season_number": self.season_number,
            "episode_number": self.episode_number,
            "title": self.title,
            "overview": self.overview,
            "still_url": self.still_url,
            "rating": round(self.rating or 0.0, 1),
            "runtime": self.runtime,
            "air_date": self.air_date,
            "alist_file_path": self.alist_file_path,
            "file_name": self.file_name,
            "file_size": self.file_size,
            "file_size_human": self.file_size_human,
            "is_watched": self.is_watched,
            "watch_progress": self.watch_progress,
            "last_played_at": self.last_played_at.isoformat() if self.last_played_at else None,
        }
