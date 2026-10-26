"""REST API Controller (MVC Controller Layer): Handles AJAX calls for playback, scanning, AI guessing, progress tracking, and admin management."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from movies.connectors import (
    AListConnector,
    LLMConnector,
    MDBListConnector,
    PlayerConnector,
    TMDBConnector,
)
from movies.extensions import db
from movies.models import Episode, MediaItem, Season, Setting
from movies.services import LibraryService

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route("/settings", methods=["GET", "POST"])
def manage_settings():
    """Get or update API keys and system settings."""
    if request.method == "GET":
        return jsonify({"ok": True, "settings": Setting.get_all()})

    payload = request.get_json(silent=True) or {}
    allowed_keys = {
        "ALIST_URL",
        "ALIST_USERNAME",
        "ALIST_PASSWORD",
        "ALIST_SCAN_PATH",
        "TMDB_TOKEN",
        "MDBLIST_APIKEY",
        "LLM_BASE_URL",
        "LLM_API_KEY",
        "LLM_MODEL",
        "LLM_API",
        "MPC_HC_PATH",
    }
    updates = {k: v for k, v in payload.items() if k in allowed_keys}
    Setting.set_many(updates)
    return jsonify({"ok": True, "message": "密钥与系统配置已保存", "settings": Setting.get_all()})


@api_bp.route("/settings/test", methods=["POST"])
def test_settings():
    """Test connectivity for AList, TMDB, MDBList, DeepSeek AI, or MPC-HC player."""
    payload = request.get_json(silent=True) or {}
    target = (payload.get("target") or "all").lower()

    # Temporarily apply any unsaved form values passed in payload
    overrides = payload.get("settings") or {}
    if overrides:
        Setting.set_many(overrides)

    results = {}
    targets = ["alist", "tmdb", "mdblist", "llm", "player"] if target == "all" else [target]

    for t in targets:
        try:
            if t == "alist":
                results["alist"] = AListConnector().test_connection()
            elif t == "tmdb":
                results["tmdb"] = TMDBConnector().test_connection()
            elif t == "mdblist":
                results["mdblist"] = MDBListConnector().test_connection()
            elif t == "llm":
                results["llm"] = LLMConnector().test_connection()
            elif t == "player":
                results["player"] = PlayerConnector().test_connection()
        except Exception as exc:
            results[t] = {"ok": False, "error": str(exc)}

    all_ok = all(v.get("ok") for v in results.values())
    return jsonify({"ok": all_ok, "results": results})


@api_bp.route("/alist/list", methods=["GET", "POST"])
def alist_list():
    """List files and folders inside AList for interactive browsing."""
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        path = data.get("path") or Setting.get("ALIST_SCAN_PATH", "/Quark/来自：分享")
    else:
        path = request.args.get("path") or Setting.get("ALIST_SCAN_PATH", "/Quark/来自：分享")

    try:
        conn = AListConnector()
        items = conn.list_dir(path)
        return jsonify({"ok": True, "path": path, "items": items})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc), "path": path, "items": []}), 400


@api_bp.route("/ai/guess", methods=["POST"])
def ai_guess_title():
    """Use DeepSeek AI + Chinese netdisk heuristics to guess the original movie/TV name and search TMDB."""
    data = request.get_json(silent=True) or {}
    raw_name = (data.get("raw_name") or "").strip()
    inner_files = data.get("inner_files") or []
    force_live = bool(data.get("force_live", True))

    if not raw_name:
        return jsonify({"ok": False, "error": "请输入需要识别的网盘目录或文件名称"}), 400

    try:
        llm = LLMConnector()
        guess = llm.guess_media_info(raw_name, inner_files=inner_files, force_live_llm=force_live)
        tmdb = TMDBConnector()
        candidates = tmdb.search(
            guess.get("clean_title") or raw_name,
            media_type=guess.get("media_type"),
            year=guess.get("year"),
        )
        if not candidates and guess.get("english_title"):
            candidates = tmdb.search(guess["english_title"], media_type=guess.get("media_type"))
        return jsonify({"ok": True, "guess": guess, "tmdb_candidates": candidates})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@api_bp.route("/tmdb/search", methods=["GET"])
def tmdb_search():
    """Search TMDB movies or TV series."""
    q = (request.args.get("q") or "").strip()
    media_type = (request.args.get("type") or "").strip() or None
    year = (request.args.get("year") or "").strip() or None
    if not q:
        return jsonify({"ok": True, "results": []})
    try:
        results = TMDBConnector().search(q, media_type=media_type, year=year)
        return jsonify({"ok": True, "results": results})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc), "results": []}), 400


@api_bp.route("/media", methods=["GET"])
def list_media():
    """Return JSON list of all media items."""
    items = MediaItem.query.order_by(MediaItem.id.desc()).all()
    return jsonify({"ok": True, "items": [x.to_dict() for x in items]})


@api_bp.route("/media/<int:media_id>", methods=["GET"])
def get_media(media_id: int):
    """Return full JSON details of a single media item including seasons & episodes."""
    item = db.session.get(MediaItem, media_id)
    if not item:
        return jsonify({"ok": False, "error": "Not found"}), 404
    return jsonify({"ok": True, "item": item.to_dict(include_seasons=True)})


@api_bp.route("/media/add", methods=["POST"])
def add_media():
    """Add a movie or TV series from an AList path and/or explicit TMDB ID."""
    data = request.get_json(silent=True) or {}
    alist_path = (data.get("alist_path") or "").strip()
    tmdb_id = data.get("tmdb_id")
    media_type = (data.get("media_type") or "").strip() or None
    custom_title = (data.get("title") or "").strip()

    if tmdb_id:
        try:
            tmdb_id = int(tmdb_id)
        except ValueError:
            tmdb_id = None

    service = LibraryService()
    try:
        if alist_path:
            item = service.import_by_alist_path(
                alist_path=alist_path,
                custom_tmdb_id=tmdb_id,
                custom_media_type=media_type,
                force_live_llm=True,
            )
            if custom_title:
                item.title = custom_title
                db.session.commit()
            return jsonify({"ok": True, "message": f"成功添加《{item.title}》", "item": item.to_dict(include_seasons=True)})
        elif tmdb_id:
            # Add directly by TMDB ID with a virtual/placeholder AList path if user only selected TMDB
            cand = {
                "raw_name": custom_title or f"TMDB-{tmdb_id}",
                "alist_path": f"/Quark/来自：分享/{custom_title or tmdb_id}",
                "is_dir": True,
                "media_type_hint": media_type or "movie",
                "video_files": [],
                "local_artwork": {},
                "quality_badge": "4K UHD",
            }
            item, _ = service.import_candidate(cand, custom_tmdb_id=tmdb_id, custom_media_type=media_type)
            return jsonify({"ok": True, "message": f"成功添加《{item.title}》", "item": item.to_dict(include_seasons=True)})
        else:
            return jsonify({"ok": False, "error": "请提供 AList 网盘路径或选择 TMDB 影视条目"}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@api_bp.route("/media/scan", methods=["POST"])
def scan_alist():
    """Batch scan AList directory and import discovered movies and TV series."""
    data = request.get_json(silent=True) or {}
    scan_path = (data.get("scan_path") or "").strip() or None
    limit = data.get("limit")
    force_live_llm = bool(data.get("force_live_llm", False))

    try:
        service = LibraryService()
        result = service.scan_alist_directory(
            scan_path=scan_path,
            limit=int(limit) if limit else None,
            force_live_llm=force_live_llm,
        )
        return jsonify({"ok": True, **result})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@api_bp.route("/play", methods=["POST"])
def play_media():
    """Launch MPC-HC (C:\\Program Files\\MPC-HC\\mpc-hc64.exe) to play the selected movie or episode."""
    data = request.get_json(silent=True) or {}
    media_id = data.get("media_id")
    season_number = data.get("season_number")
    episode_number = data.get("episode_number")
    episode_id = data.get("episode_id")
    custom_path = data.get("alist_path")

    if not media_id:
        return jsonify({"ok": False, "error": "缺少 media_id 参数"}), 400

    try:
        service = LibraryService()
        res = service.play_media(
            media_id=int(media_id),
            season_number=int(season_number) if season_number is not None else None,
            episode_number=int(episode_number) if episode_number is not None else None,
            episode_id=int(episode_id) if episode_id is not None else None,
            custom_path=custom_path,
        )
        return jsonify(res)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@api_bp.route("/progress", methods=["POST"])
def update_progress():
    """Update viewing progress for a Movie or TV Series / Episode."""
    data = request.get_json(silent=True) or {}
    media_id = data.get("media_id")
    if not media_id:
        return jsonify({"ok": False, "error": "缺少 media_id 参数"}), 400

    item = db.session.get(MediaItem, int(media_id))
    if not item:
        return jsonify({"ok": False, "error": "未找到影视条目"}), 404

    now = datetime.now(timezone.utc)
    item.last_watched_at = now

    episode_id = data.get("episode_id")
    season_number = data.get("season_number")
    episode_number = data.get("episode_number")
    is_watched = data.get("is_watched")
    progress_percent = data.get("progress_percent")
    action = data.get("action")  # e.g., 'next_episode', 'reset', 'toggle_episode'

    target_ep: Episode | None = None
    if episode_id:
        target_ep = db.session.get(Episode, int(episode_id))
    elif season_number is not None and episode_number is not None:
        target_ep = Episode.query.filter_by(
            media_id=item.id,
            season_number=int(season_number),
            episode_number=int(episode_number),
        ).first()

    if action == "next_episode" and item.media_type == "tv":
        cur_s = item.current_season or item.active_season_number or 1
        cur_e = item.current_episode or 1
        cur_ep_obj = Episode.query.filter_by(media_id=item.id, season_number=cur_s, episode_number=cur_e).first()
        if cur_ep_obj:
            cur_ep_obj.is_watched = True
            cur_ep_obj.watch_progress = 100
            cur_ep_obj.last_played_at = now
        next_ep_obj = (
            Episode.query.filter(
                Episode.media_id == item.id,
                (Episode.season_number > cur_s)
                | ((Episode.season_number == cur_s) & (Episode.episode_number > cur_e)),
            )
            .order_by(Episode.season_number.asc(), Episode.episode_number.asc())
            .first()
        )
        if next_ep_obj:
            item.current_season = next_ep_obj.season_number
            item.current_episode = next_ep_obj.episode_number
            next_ep_obj.is_watched = True
            next_ep_obj.watch_progress = 100
            next_ep_obj.last_played_at = now
    elif action == "reset":
        item.progress_percent = 0
        item.last_watched_at = None
        for ep in item.episodes:
            ep.is_watched = False
            ep.watch_progress = 0
    else:
        if target_ep:
            if is_watched is not None:
                target_ep.is_watched = bool(is_watched)
            else:
                target_ep.is_watched = not target_ep.is_watched
            target_ep.watch_progress = 100 if target_ep.is_watched else 0
            target_ep.last_played_at = now
            item.current_season = target_ep.season_number
            item.current_episode = target_ep.episode_number
        elif season_number is not None and episode_number is not None:
            item.current_season = int(season_number)
            item.current_episode = int(episode_number)

    if item.media_type == "tv":
        if progress_percent is not None:
            item.progress_percent = max(0, min(100, int(progress_percent)))
        else:
            total = max(1, item.total_episodes_count)
            watched = sum(1 for ep in item.episodes if ep.is_watched)
            item.progress_percent = min(100, int((watched / total) * 100))
    else:
        if progress_percent is not None:
            item.progress_percent = max(0, min(100, int(progress_percent)))
        elif is_watched is not None:
            item.progress_percent = 100 if is_watched else 0

    db.session.commit()
    return jsonify(
        {
            "ok": True,
            "media": item.to_dict(),
            "episode": target_ep.to_dict() if target_ep else None,
        }
    )


@api_bp.route("/admin/media/<int:media_id>/update", methods=["POST"])
def admin_update_media(media_id: int):
    """Admin Backend: Switch/manage series or movie title, logo, poster, backdrop, hero featured status, active season, or AList source."""
    item = db.session.get(MediaItem, media_id)
    if not item:
        return jsonify({"ok": False, "error": "未找到影视项目"}), 404

    data = request.get_json(silent=True) or {}
    for field in [
        "title",
        "original_title",
        "year",
        "overview",
        "genres",
        "poster_url",
        "backdrop_url",
        "logo_url",
        "alist_path",
        "video_path",
        "quality_badge",
        "media_type",
        "ai_guessed_title",
        "ai_obfuscation_type",
        "ai_explanation",
    ]:
        if field in data and data[field] is not None:
            setattr(item, field, str(data[field]).strip())

    if "is_featured" in data:
        item.is_featured = bool(data["is_featured"])
    if "is_visible" in data:
        item.is_visible = bool(data["is_visible"])
    if "featured_order" in data and data["featured_order"] is not None:
        item.featured_order = int(data["featured_order"])
    if "active_season_number" in data and data["active_season_number"] is not None:
        item.active_season_number = int(data["active_season_number"])
        item.current_season = int(data["active_season_number"])

    db.session.commit()
    return jsonify({"ok": True, "message": f"《{item.title}》后台配置已更新", "item": item.to_dict()})


@api_bp.route("/admin/media/<int:media_id>/rematch", methods=["POST"])
def admin_rematch_media(media_id: int):
    """Admin Backend: Switch a media item to a different TMDB ID and re-fetch all posters, logos, seasons, and episode stills."""
    item = db.session.get(MediaItem, media_id)
    if not item:
        return jsonify({"ok": False, "error": "未找到影视项目"}), 404

    data = request.get_json(silent=True) or {}
    new_tmdb_id = data.get("tmdb_id")
    new_media_type = data.get("media_type") or item.media_type
    if not new_tmdb_id:
        return jsonify({"ok": False, "error": "请提供新的 TMDB ID"}), 400

    try:
        service = LibraryService()
        # Clear old seasons/episodes before rematching
        Season.query.filter_by(media_id=item.id).delete()
        Episode.query.filter_by(media_id=item.id).delete()
        db.session.commit()

        updated = service.import_by_alist_path(
            alist_path=item.alist_path,
            custom_tmdb_id=int(new_tmdb_id),
            custom_media_type=new_media_type,
            force_live_llm=False,
        )
        return jsonify(
            {
                "ok": True,
                "message": f"已重新匹配为《{updated.title}》(TMDB #{updated.tmdb_id})",
                "item": updated.to_dict(include_seasons=True),
            }
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@api_bp.route("/admin/media/<int:media_id>", methods=["DELETE"])
def admin_delete_media(media_id: int):
    """Delete a media item from the library."""
    item = db.session.get(MediaItem, media_id)
    if not item:
        return jsonify({"ok": False, "error": "未找到影视项目"}), 404
    title = item.title
    db.session.delete(item)
    db.session.commit()
    return jsonify({"ok": True, "message": f"已移除《{title}》"})
