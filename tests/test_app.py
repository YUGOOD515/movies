"""Unit and integration tests for CineVault AList Media Center (MVC + Connector)."""
from __future__ import annotations

import pytest

from movies import create_app
from movies.connectors import AListConnector, LLMConnector, PlayerConnector
from movies.extensions import db
from movies.models import Episode, MediaItem, Season, Setting


@pytest.fixture()
def app():
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )
    with app.app_context():
        db.create_all()
        yield app


@pytest.fixture()
def client(app):
    return app.test_client()


def test_llm_deobfuscation_patterns(app):
    """Test AI & heuristic netdisk name de-obfuscation (拆字, 同形字, 谐音, 穿插符号)."""
    with app.app_context():
        llm = LLMConnector()

        # 1. 拆字 (Radical splitting)
        res_spider = llm.heuristic_clean("虫知-虫朱-亻夹", ["new-Spider-Man.Brand.New.Day.2026.mp4"])
        assert "蜘蛛侠" in res_spider["clean_title"]
        assert res_spider["obfuscation_type"] == "拆字还原"

        # 2. 同形字/形近字 (Homoglyphs)
        res_sev = llm.heuristic_clean("R 人苼苆剨朮（2025）[10集全] 4K HDR")
        assert res_sev["clean_title"] == "人生切割术"
        assert res_sev["obfuscation_type"] == "同形字还原"

        # 3. 谐音 (Homophones)
        res_hoppers = llm.heuristic_clean("【合.力.变.神.计.划】4K.UHD蓝光原盘REMUX")
        assert res_hoppers["clean_title"] == "河狸变身计划"
        assert res_hoppers["obfuscation_type"] == "谐音还原"

        # 4. 穿插字符/符号 (Inserted symbols)
        res_lychee = llm.heuristic_clean("长z安z的z荔z枝 (2025) 4K 高码 60帧")
        assert res_lychee["clean_title"] == "长安的荔枝"
        assert res_lychee["obfuscation_type"] == "防和谐符号清理"

        res_solitude = llm.heuristic_clean("B 百丨年孤丨独 (2024)[哥伦比亚 历史 奇幻]")
        assert res_solitude["clean_title"] == "百年孤独"


def test_alist_season_episode_parsing():
    """Test parsing season and episode numbers from diverse netdisk filenames."""
    assert AListConnector.parse_season_episode("Breaking.Bad.S04E08.2160p.mkv") == (4, 8)
    assert AListConnector.parse_season_episode("05 4K.mp4", default_season=1) == (1, 5)
    assert AListConnector.parse_season_episode("12.mkv", default_season=2) == (2, 12)
    assert AListConnector.parse_season_folder_number("第 3 季 - 2160p UHD") == 3
    assert AListConnector.parse_season_folder_number("第二季 (2024) 4K") == 2
    assert AListConnector.parse_season_folder_number("Season 1") == 1


def test_mvc_pages_and_progress_tracking(client, app):
    """Test homepage, series detail page (season poster + episode stills), progress API, and admin API."""
    with app.app_context():
        show = MediaItem(
            tmdb_id=1396,
            media_type="tv",
            title="绝命毒师",
            original_title="Breaking Bad",
            year="2008",
            overview="高中化学老师制毒传奇。",
            poster_url="https://image.tmdb.org/t/p/w780/ggFHVNu6YYI5L9pCfOacjizRGt.jpg",
            backdrop_url="https://image.tmdb.org/t/p/original/tsRy63Mu5cu8etL1X7ZLyf7UP1M.jpg",
            logo_url="https://image.tmdb.org/t/p/w500/logo.png",
            alist_path="/Quark/来自：分享/绝命毒师 第4季 4K",
            raw_alist_name="绝命毒师 第4季 4K",
            ai_guessed_title="绝命毒师",
            ai_obfuscation_type="标准命名",
            tmdb_rating=8.9,
            imdb_rating=9.5,
            is_featured=True,
            active_season_number=4,
            current_season=4,
            current_episode=1,
        )
        db.session.add(show)
        db.session.flush()

        s4 = Season(
            media_id=show.id,
            season_number=4,
            name="第 4 季",
            poster_url="https://image.tmdb.org/t/p/w500/s4.jpg",
            episode_count=2,
            vote_average=9.2,
        )
        db.session.add(s4)
        db.session.flush()

        ep1 = Episode(
            media_id=show.id,
            season_id=s4.id,
            season_number=4,
            episode_number=1,
            title="盒刀 (Box Cutter)",
            still_url="https://image.tmdb.org/t/p/w500/ep1.jpg",
            rating=9.3,
            alist_file_path="/Quark/来自：分享/绝命毒师 第4季 4K/Breaking.Bad.S04E01.mkv",
            file_name="Breaking.Bad.S04E01.mkv",
            file_size=27444907564,
        )
        ep2 = Episode(
            media_id=show.id,
            season_id=s4.id,
            season_number=4,
            episode_number=2,
            title="三十八口径左轮",
            still_url="https://image.tmdb.org/t/p/w500/ep2.jpg",
            rating=8.4,
            alist_file_path="/Quark/来自：分享/绝命毒师 第4季 4K/Breaking.Bad.S04E02.mkv",
            file_name="Breaking.Bad.S04E02.mkv",
            file_size=26421989799,
        )
        db.session.add_all([ep1, ep2])
        db.session.commit()
        show_id = show.id
        ep1_id = ep1.id

    # 1. Homepage renders Hero banner and TV section
    resp_home = client.get("/")
    assert resp_home.status_code == 200
    html_home = resp_home.data.decode("utf-8")
    assert "绝命毒师" in html_home

    # 2. Detail page renders Season selector, Season poster, and Episode still cards
    resp_detail = client.get(f"/media/{show_id}")
    assert resp_detail.status_code == 200
    html_detail = resp_detail.data.decode("utf-8")
    assert "盒刀 (Box Cutter)" in html_detail
    assert "第 4 季" in html_detail

    # 3. Progress tracking API updates episode watched status & percentage
    resp_prog = client.post(
        "/api/progress",
        json={"media_id": show_id, "episode_id": ep1_id, "season_number": 4, "episode_number": 1},
    )
    assert resp_prog.status_code == 200
    prog_data = resp_prog.get_json()
    assert prog_data["ok"] is True
    assert prog_data["episode"]["is_watched"] is True
    assert prog_data["media"]["progress_percent"] == 50

    # 4. Admin update API switches logo/title/season
    resp_adm = client.post(
        f"/api/admin/media/{show_id}/update",
        json={"title": "绝命毒师 (4K 典藏版)", "logo_url": "https://example.com/new-logo.png"},
    )
    assert resp_adm.status_code == 200
    assert resp_adm.get_json()["item"]["title"] == "绝命毒师 (4K 典藏版)"


def test_player_connector_check():
    """Verify MPC-HC connector checks path cleanly."""
    player = PlayerConnector()
    info = player.test_connection()
    assert "player_path" in info
