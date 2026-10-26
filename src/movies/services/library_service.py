"""Library Service: Orchestrates AList scanning, DeepSeek AI title de-obfuscation, TMDB & MDBList metadata enrichment, and playback."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from movies.connectors import (
    AListConnector,
    LLMConnector,
    MDBListConnector,
    PlayerConnector,
    TMDBConnector,
)
from movies.extensions import db
from movies.models import Episode, MediaItem, Season, Setting


class LibraryService:
    """High-level service layer connecting Models and External Connectors."""

    def __init__(self) -> None:
        self.alist = AListConnector()
        self.llm = LLMConnector()
        self.tmdb = TMDBConnector()
        self.mdblist = MDBListConnector()
        self.player = PlayerConnector()

    def scan_alist_directory(
        self,
        scan_path: str | None = None,
        limit: int | None = None,
        force_live_llm: bool = False,
    ) -> dict[str, Any]:
        """Scan an AList directory, identify movies & TV series with AI, and enrich via TMDB + MDBList."""
        target_path = scan_path or Setting.get("ALIST_SCAN_PATH", "/Quark/来自：分享")
        entries = self.alist.list_dir(target_path)

        candidates: list[dict[str, Any]] = []
        for entry in entries:
            try:
                found = self.alist.inspect_media_entry(entry)
                candidates.extend(found)
            except Exception:
                continue
            if limit and len(candidates) >= limit:
                break

        added_items: list[MediaItem] = []
        updated_items: list[MediaItem] = []
        skipped_names: list[str] = []

        for cand in candidates:
            try:
                item, created = self.import_candidate(cand, force_live_llm=force_live_llm)
                if item:
                    if created:
                        added_items.append(item)
                    else:
                        updated_items.append(item)
                else:
                    skipped_names.append(cand.get("raw_name", ""))
            except Exception:
                skipped_names.append(cand.get("raw_name", ""))

        # Ensure featured hero banner items are set if none are marked yet
        self.ensure_featured_banners()

        return {
            "scan_path": target_path,
            "total_candidates": len(candidates),
            "added_count": len(added_items),
            "updated_count": len(updated_items),
            "skipped": skipped_names,
            "items": [x.to_dict() for x in added_items + updated_items],
        }

    def import_by_alist_path(
        self,
        alist_path: str,
        custom_tmdb_id: int | None = None,
        custom_media_type: str | None = None,
        force_live_llm: bool = True,
    ) -> MediaItem:
        """Import a single movie or TV series from a specific AList path."""
        info = self.alist.get_file_info(alist_path)
        entry = {
            "name": info.get("name") or alist_path.rstrip("/").split("/")[-1],
            "path": "/" + alist_path.strip("/"),
            "is_dir": bool(info.get("is_dir")),
            "size": info.get("size", 0),
        }
        candidates = self.alist.inspect_media_entry(entry)
        if not candidates:
            # Create a fallback candidate even if folder structure is unusual
            candidates = [
                {
                    "raw_name": entry["name"],
                    "alist_path": entry["path"],
                    "is_dir": entry["is_dir"],
                    "media_type_hint": custom_media_type or "movie",
                    "video_files": [] if entry["is_dir"] else [{"name": entry["name"], "path": entry["path"], "size": entry["size"], "season": None, "episode": None}],
                    "local_artwork": {},
                    "quality_badge": self.alist.extract_quality_badge(entry["name"]),
                }
            ]
        item, _ = self.import_candidate(
            candidates[0],
            custom_tmdb_id=custom_tmdb_id,
            custom_media_type=custom_media_type,
            force_live_llm=force_live_llm,
        )
        self.ensure_featured_banners()
        return item

    def import_candidate(
        self,
        cand: dict[str, Any],
        custom_tmdb_id: int | None = None,
        custom_media_type: str | None = None,
        force_live_llm: bool = False,
    ) -> tuple[MediaItem, bool]:
        """Import or update a single media candidate with AI title recognition, TMDB, and MDBList."""
        raw_name = cand["raw_name"]
        alist_path = cand["alist_path"]
        video_files = cand.get("video_files") or []
        local_artwork = cand.get("local_artwork") or {}
        quality_badge = cand.get("quality_badge") or "4K UHD"

        inner_filenames = [v["name"] for v in video_files[:5]]
        ai_info = self.llm.guess_media_info(
            raw_name,
            inner_files=inner_filenames,
            force_live_llm=force_live_llm,
        )

        media_type = custom_media_type or cand.get("media_type_hint") or ai_info.get("media_type") or "movie"
        clean_title = ai_info.get("clean_title") or raw_name
        english_title = ai_info.get("english_title") or ""
        year_hint = ai_info.get("year") or ""

        # Resolve TMDB ID
        tmdb_id = custom_tmdb_id
        if not tmdb_id:
            search_queries = [clean_title]
            if english_title and english_title.lower() != clean_title.lower():
                search_queries.append(english_title)

            for q in search_queries:
                matches = self.tmdb.search(q, media_type=media_type, year=year_hint)
                if not matches and year_hint:
                    matches = self.tmdb.search(q, media_type=media_type, year=None)
                if not matches:
                    matches = self.tmdb.search(q, media_type=None, year=None)
                if matches:
                    tmdb_id = matches[0]["tmdb_id"]
                    if not custom_media_type and cand.get("media_type_hint") != "tv":
                        media_type = matches[0]["media_type"]
                    break

        tmdb_details: dict[str, Any] = {}
        if tmdb_id:
            try:
                tmdb_details = self.tmdb.get_details(tmdb_id, media_type=media_type)
            except Exception:
                # Try opposite media_type if initial type failed on TMDB
                alt_type = "tv" if media_type == "tv" else "movie"
                try:
                    tmdb_details = self.tmdb.get_details(tmdb_id, media_type=alt_type)
                except Exception:
                    tmdb_details = {}

        mdb_ratings: dict[str, Any] = {}
        if tmdb_id:
            mdb_ratings = self.mdblist.get_ratings(tmdb_id, media_type=media_type)

        # Check if MediaItem already exists (by alist_path or by tmdb_id + media_type)
        existing = MediaItem.query.filter_by(alist_path=alist_path).first()
        if not existing and tmdb_id:
            existing = MediaItem.query.filter_by(tmdb_id=tmdb_id, media_type=media_type).first()

        created = existing is None
        item = existing or MediaItem(alist_path=alist_path, raw_alist_name=raw_name)

        primary_video_path = video_files[0]["path"] if video_files else alist_path

        # Record alternative sources if another AList folder maps to the same TMDB item
        alt_sources = item.alt_sources
        source_entry = {
            "raw_name": raw_name,
            "alist_path": alist_path,
            "video_path": primary_video_path,
            "quality_badge": quality_badge,
        }
        if not any(s.get("alist_path") == alist_path for s in alt_sources):
            alt_sources.append(source_entry)
        item.alt_sources_json = json.dumps(alt_sources, ensure_ascii=False)

        if created:
            item.alist_path = alist_path
            item.raw_alist_name = raw_name
            item.video_path = primary_video_path
            item.quality_badge = quality_badge
        elif not item.video_path:
            item.video_path = primary_video_path

        item.tmdb_id = tmdb_id
        item.media_type = media_type
        item.ai_guessed_title = clean_title
        item.ai_obfuscation_type = ai_info.get("obfuscation_type") or "标准命名"
        item.ai_explanation = ai_info.get("explanation") or ""

        # Apply TMDB metadata
        item.title = tmdb_details.get("title") or clean_title
        item.original_title = tmdb_details.get("original_title") or english_title or raw_name
        item.year = tmdb_details.get("year") or year_hint or ""
        item.release_date = tmdb_details.get("release_date") or ""
        item.overview = tmdb_details.get("overview") or f"来自 AList 网盘资源：{raw_name}"
        item.tagline = tmdb_details.get("tagline") or ""
        item.genres = tmdb_details.get("genres") or ("剧集" if media_type == "tv" else "电影")
        item.status = tmdb_details.get("status") or "Released"
        item.runtime = tmdb_details.get("runtime")
        item.imdb_id = tmdb_details.get("imdb_id") or mdb_ratings.get("imdb_id")

        # Artwork (TMDB with local AList artwork fallback)
        alt_logos = list(tmdb_details.get("alt_logos") or [])
        if local_artwork.get("logo") and local_artwork["logo"] not in alt_logos:
            alt_logos.insert(0, local_artwork["logo"])
        alt_posters = list(tmdb_details.get("alt_posters") or [])
        if local_artwork.get("poster") and local_artwork["poster"] not in alt_posters:
            alt_posters.append(local_artwork["poster"])
        alt_backdrops = list(tmdb_details.get("alt_backdrops") or [])
        if local_artwork.get("backdrop") and local_artwork["backdrop"] not in alt_backdrops:
            alt_backdrops.append(local_artwork["backdrop"])

        item.poster_url = tmdb_details.get("poster_url") or local_artwork.get("poster")
        item.backdrop_url = tmdb_details.get("backdrop_url") or local_artwork.get("backdrop") or item.poster_url
        item.logo_url = tmdb_details.get("logo_url") or local_artwork.get("logo")
        item.alt_logos_json = json.dumps(alt_logos, ensure_ascii=False)
        item.alt_posters_json = json.dumps(alt_posters, ensure_ascii=False)
        item.alt_backdrops_json = json.dumps(alt_backdrops, ensure_ascii=False)

        # Ratings
        item.tmdb_rating = float(tmdb_details.get("tmdb_rating") or mdb_ratings.get("tmdb_score") or 0.0)
        item.imdb_rating = mdb_ratings.get("imdb_rating")
        item.rt_score = mdb_ratings.get("rt_score")
        item.popcorn_score = mdb_ratings.get("popcorn_score")
        item.metacritic_score = mdb_ratings.get("metacritic_score")
        item.trakt_score = mdb_ratings.get("trakt_score")
        item.letterboxd_score = mdb_ratings.get("letterboxd_score")
        item.mdblist_score = mdb_ratings.get("mdblist_score")
        item.ratings_json = json.dumps(mdb_ratings.get("ratings") or [], ensure_ascii=False)

        db.session.add(item)
        db.session.flush()

        if media_type == "tv":
            self._sync_tv_seasons_and_episodes(item, tmdb_details, video_files)

        db.session.commit()
        return item, created

    def _sync_tv_seasons_and_episodes(
        self,
        item: MediaItem,
        tmdb_details: dict[str, Any],
        video_files: list[dict[str, Any]],
    ) -> None:
        """Populate every season's poster and every episode's still image, title, rating, and AList file mapping."""
        # Map AList video files by (season_number, episode_number)
        file_map: dict[tuple[int, int], dict[str, Any]] = {}
        seasons_with_files: set[int] = set()
        for idx, vf in enumerate(video_files, start=1):
            s_num = vf.get("season") or 1
            ep_num = vf.get("episode") or idx
            seasons_with_files.add(s_num)
            if (s_num, ep_num) not in file_map or vf.get("size", 0) > file_map[(s_num, ep_num)].get("size", 0):
                file_map[(s_num, ep_num)] = vf

        seasons_summary = tmdb_details.get("seasons_summary") or []
        tmdb_season_nums = [s["season_number"] for s in seasons_summary if s.get("season_number", 0) >= 1]

        # Decide which seasons to fetch: all TMDB regular seasons (up to 7) + any season present in local files
        target_seasons = sorted(set(tmdb_season_nums[:7]) | seasons_with_files)
        if not target_seasons:
            target_seasons = [1]

        existing_seasons = {s.season_number: s for s in item.seasons}
        existing_episodes = {(e.season_number, e.episode_number): e for e in item.episodes}

        for s_num in target_seasons:
            s_data: dict[str, Any] = {}
            if item.tmdb_id:
                try:
                    s_data = self.tmdb.get_season_details(
                        item.tmdb_id,
                        s_num,
                        fallback_poster=item.poster_url,
                        fallback_backdrop=item.backdrop_url,
                    )
                except Exception:
                    s_data = {}

            season_obj = existing_seasons.get(s_num)
            if not season_obj:
                season_obj = Season(
                    media_id=item.id,
                    season_number=s_num,
                    name=s_data.get("name") or f"第 {s_num} 季",
                )
                db.session.add(season_obj)
                db.session.flush()

            season_obj.name = s_data.get("name") or season_obj.name or f"第 {s_num} 季"
            season_obj.overview = s_data.get("overview") or season_obj.overview or ""
            season_obj.poster_url = s_data.get("poster_url") or season_obj.poster_url or item.poster_url
            season_obj.air_date = s_data.get("air_date") or season_obj.air_date or ""
            season_obj.vote_average = s_data.get("vote_average") or season_obj.vote_average or item.tmdb_rating or 0.0

            tmdb_eps = {ep["episode_number"]: ep for ep in (s_data.get("episodes") or [])}
            local_ep_nums = {ep_n for (sn, ep_n) in file_map.keys() if sn == s_num}
            all_ep_nums = sorted(set(tmdb_eps.keys()) | local_ep_nums)

            season_obj.episode_count = len(all_ep_nums)

            for ep_num in all_ep_nums:
                t_ep = tmdb_eps.get(ep_num, {})
                l_vf = file_map.get((s_num, ep_num))

                ep_obj = existing_episodes.get((s_num, ep_num))
                if not ep_obj:
                    ep_obj = Episode(
                        media_id=item.id,
                        season_id=season_obj.id,
                        season_number=s_num,
                        episode_number=ep_num,
                        title=t_ep.get("title") or f"第 {ep_num} 集",
                    )
                    db.session.add(ep_obj)

                ep_obj.season_id = season_obj.id
                ep_obj.title = t_ep.get("title") or ep_obj.title or f"第 {ep_num} 集"
                ep_obj.overview = t_ep.get("overview") or ep_obj.overview or (
                    f"网盘片源：{l_vf['name']}" if l_vf else ""
                )
                ep_obj.still_url = t_ep.get("still_url") or ep_obj.still_url or item.backdrop_url or item.poster_url
                ep_obj.rating = float(t_ep.get("rating") or ep_obj.rating or item.tmdb_rating or 0.0)
                ep_obj.runtime = t_ep.get("runtime") or ep_obj.runtime or item.runtime
                ep_obj.air_date = t_ep.get("air_date") or ep_obj.air_date or ""

                if l_vf:
                    ep_obj.alist_file_path = l_vf["path"]
                    ep_obj.file_name = l_vf["name"]
                    ep_obj.file_size = l_vf.get("size", 0)

        # Set default active season to the first season that has bound AList video files
        if seasons_with_files:
            first_avail_season = min(seasons_with_files)
            item.active_season_number = first_avail_season
            if item.play_count == 0:
                item.current_season = first_avail_season
                avail_eps = sorted(ep_n for (sn, ep_n) in file_map.keys() if sn == first_avail_season)
                if avail_eps:
                    item.current_episode = avail_eps[0]
                    item.video_path = file_map[(first_avail_season, avail_eps[0])]["path"]

    def ensure_featured_banners(self) -> None:
        """Ensure top high-resolution movies and series with backdrops & logos are featured on the homepage hero."""
        featured_count = MediaItem.query.filter_by(is_featured=True, is_visible=True).count()
        if featured_count >= 5:
            return

        candidates = (
            MediaItem.query.filter(MediaItem.is_visible.is_(True), MediaItem.backdrop_url.isnot(None))
            .order_by(MediaItem.logo_url.isnot(None).desc(), MediaItem.tmdb_rating.desc())
            .limit(6)
            .all()
        )
        for idx, c in enumerate(candidates, start=1):
            c.is_featured = True
            c.featured_order = idx
        db.session.commit()

    def play_media(
        self,
        media_id: int,
        season_number: int | None = None,
        episode_number: int | None = None,
        episode_id: int | None = None,
        custom_path: str | None = None,
    ) -> dict[str, Any]:
        """Resolve signed AList stream URL, launch MPC-HC, and update viewing progress."""
        item = db.session.get(MediaItem, media_id)
        if not item:
            raise ValueError("未找到对应的影视项目")

        target_path = custom_path
        played_episode: Episode | None = None

        if item.media_type == "tv":
            if episode_id:
                played_episode = db.session.get(Episode, episode_id)
            elif season_number is not None and episode_number is not None:
                played_episode = Episode.query.filter_by(
                    media_id=item.id,
                    season_number=season_number,
                    episode_number=episode_number,
                ).first()
            else:
                # Default to current tracked season/episode or first available episode with a file
                played_episode = Episode.query.filter_by(
                    media_id=item.id,
                    season_number=item.current_season or item.active_season_number or 1,
                    episode_number=item.current_episode or 1,
                ).first()
                if not played_episode or not played_episode.alist_file_path:
                    played_episode = (
                        Episode.query.filter(
                            Episode.media_id == item.id,
                            Episode.alist_file_path.isnot(None),
                        )
                        .order_by(Episode.season_number, Episode.episode_number)
                        .first()
                    )

            if played_episode and played_episode.alist_file_path:
                target_path = played_episode.alist_file_path

        if not target_path:
            target_path = item.video_path or item.alist_path

        stream_url = self.alist.get_stream_url(target_path)
        play_title = item.title
        if played_episode:
            play_title = f"{item.title} S{played_episode.season_number:02d}E{played_episode.episode_number:02d} - {played_episode.title}"

        launch_info = self.player.launch(stream_url, title=play_title)

        # Update watch progress
        now = datetime.now(timezone.utc)
        item.last_watched_at = now
        item.play_count = (item.play_count or 0) + 1

        if played_episode:
            played_episode.is_watched = True
            played_episode.watch_progress = 100
            played_episode.last_played_at = now
            item.current_season = played_episode.season_number
            item.current_episode = played_episode.episode_number
            total_avail = max(1, item.available_episodes_count or item.total_episodes_count)
            watched_cnt = sum(1 for ep in item.episodes if ep.is_watched)
            item.progress_percent = min(100, max(5, int((watched_cnt / total_avail) * 100)))
        else:
            if not item.progress_percent or item.progress_percent < 15:
                item.progress_percent = 25

        db.session.commit()
        return {
            **launch_info,
            "media": item.to_dict(),
            "episode": played_episode.to_dict() if played_episode else None,
        }
