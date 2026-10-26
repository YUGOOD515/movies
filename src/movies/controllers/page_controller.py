"""Page Controller (MVC Controller Layer): Renders Jinja2 HTML views."""
from __future__ import annotations

from flask import Blueprint, abort, render_template, request

from movies.models import MediaItem, Setting

page_bp = Blueprint("pages", __name__)


def _get_config_status() -> dict[str, bool]:
    settings = Setting.get_all()
    tmdb_ok = bool(settings.get("TMDB_TOKEN"))
    mdblist_ok = bool(settings.get("MDBLIST_APIKEY"))
    llm_ok = bool(settings.get("LLM_API_KEY"))
    alist_ok = bool(settings.get("ALIST_URL") and settings.get("ALIST_PASSWORD"))
    return {
        "tmdb_ok": tmdb_ok,
        "mdblist_ok": mdblist_ok,
        "llm_ok": llm_ok,
        "alist_ok": alist_ok,
        "all_ok": tmdb_ok and mdblist_ok and llm_ok and alist_ok,
    }


@page_bp.route("/")
def index():
    """Homepage: Hero Banner Carousel, Continue Watching, Movies, TV Series, and AI De-obfuscation showcase."""
    q = (request.args.get("q") or "").strip()
    media_filter = (request.args.get("type") or "all").strip()

    base_query = MediaItem.query.filter_by(is_visible=True)
    if q:
        like_q = f"%{q}%"
        base_query = base_query.filter(
            (MediaItem.title.ilike(like_q))
            | (MediaItem.original_title.ilike(like_q))
            | (MediaItem.raw_alist_name.ilike(like_q))
            | (MediaItem.ai_guessed_title.ilike(like_q))
            | (MediaItem.genres.ilike(like_q))
        )

    featured_items = (
        MediaItem.query.filter_by(is_visible=True, is_featured=True)
        .order_by(MediaItem.featured_order.asc(), MediaItem.tmdb_rating.desc())
        .limit(8)
        .all()
    )
    if not featured_items:
        featured_items = (
            MediaItem.query.filter_by(is_visible=True)
            .order_by(MediaItem.tmdb_rating.desc())
            .limit(5)
            .all()
        )

    continue_watching = (
        MediaItem.query.filter(
            MediaItem.is_visible.is_(True),
            (MediaItem.progress_percent > 0) | (MediaItem.last_watched_at.isnot(None)),
        )
        .order_by(MediaItem.last_watched_at.desc().nullslast(), MediaItem.updated_at.desc())
        .limit(8)
        .all()
    )

    tv_series = (
        base_query.filter_by(media_type="tv")
        .order_by(MediaItem.tmdb_rating.desc(), MediaItem.id.desc())
        .all()
    )
    movies_list = (
        base_query.filter_by(media_type="movie")
        .order_by(MediaItem.tmdb_rating.desc(), MediaItem.id.desc())
        .all()
    )

    ai_decoded_items = (
        MediaItem.query.filter(
            MediaItem.is_visible.is_(True),
            MediaItem.ai_obfuscation_type.isnot(None),
            MediaItem.ai_obfuscation_type != "标准命名",
        )
        .order_by(MediaItem.id.asc())
        .all()
    )

    return render_template(
        "index.html",
        featured_items=featured_items,
        continue_watching=continue_watching,
        tv_series=tv_series,
        movies_list=movies_list,
        ai_decoded_items=ai_decoded_items,
        search_query=q,
        media_filter=media_filter,
        config_status=_get_config_status(),
        settings=Setting.get_all(),
    )


@page_bp.route("/media/<int:media_id>")
def media_detail(media_id: int):
    """Movie or TV Series detail page with Season Selector, Season Poster, Episode Selector, and Still Cards."""
    from movies.extensions import db
    item = db.get_or_404(MediaItem, media_id)
    selected_season_num = request.args.get("season", type=int)
    selected_episode_num = request.args.get("episode", type=int)

    seasons_data = [s.to_dict(include_episodes=True) for s in item.seasons]
    if not selected_season_num:
        selected_season_num = item.current_season or item.active_season_number or (
            seasons_data[0]["season_number"] if seasons_data else 1
        )

    active_season = next(
        (s for s in seasons_data if s["season_number"] == selected_season_num),
        seasons_data[0] if seasons_data else None,
    )

    if active_season and not selected_episode_num:
        if item.current_season == active_season["season_number"] and item.current_episode:
            selected_episode_num = item.current_episode
        elif active_season["episodes"]:
            # Prefer first episode that has an AList file bound
            avail = [e for e in active_season["episodes"] if e.get("alist_file_path")]
            selected_episode_num = (
                avail[0]["episode_number"] if avail else active_season["episodes"][0]["episode_number"]
            )
        else:
            selected_episode_num = 1

    return render_template(
        "detail.html",
        item=item,
        item_json=item.to_dict(include_seasons=True),
        seasons_data=seasons_data,
        active_season=active_season,
        selected_season_num=selected_season_num,
        selected_episode_num=selected_episode_num,
        config_status=_get_config_status(),
        settings=Setting.get_all(),
    )


@page_bp.route("/admin")
def admin_dashboard():
    """Admin Backend: Manage & switch TV Series and Movies, Logos, Hero Banners, AList sources, and TMDB bindings."""
    all_items = MediaItem.query.order_by(MediaItem.media_type.desc(), MediaItem.featured_order.asc(), MediaItem.id.desc()).all()
    tv_items = [x for x in all_items if x.media_type == "tv"]
    movie_items = [x for x in all_items if x.media_type == "movie"]
    return render_template(
        "admin.html",
        all_items=all_items,
        tv_items=tv_items,
        movie_items=movie_items,
        config_status=_get_config_status(),
        settings=Setting.get_all(),
    )


@page_bp.route("/settings")
def settings_page():
    """Guided onboarding & API keys configuration page."""
    return render_template(
        "settings.html",
        config_status=_get_config_status(),
        settings=Setting.get_all(),
    )
