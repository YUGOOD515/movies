"""CineVault AList Media Center — Flask MVC + Connector Application Factory."""
from __future__ import annotations

import os
from pathlib import Path

from flask import Flask

from movies.config import DEFAULT_SETTINGS, Config
from movies.controllers import api_bp, page_bp
from movies.extensions import db
from movies.models import Setting


def create_app(test_config: dict | None = None) -> Flask:
    """Create and configure the Flask MVC application."""
    pkg_dir = Path(__file__).resolve().parent
    app = Flask(
        __name__,
        template_folder=str(pkg_dir / "views"),
        static_folder=str(pkg_dir / "static"),
    )
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    db.init_app(app)

    app.register_blueprint(page_bp)
    app.register_blueprint(api_bp)

    with app.app_context():
        db.create_all()
        # Seed default settings from .env if not already stored in DB
        existing_keys = {row.key for row in Setting.query.all()}
        initial_seed = {
            k: v for k, v in DEFAULT_SETTINGS.items() if k not in existing_keys and v
        }
        if initial_seed:
            Setting.set_many(initial_seed)

    return app


def main() -> None:
    """Entrypoint for `uv run movies`."""
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    app = create_app()
    port = int(os.getenv("FLASK_PORT", "5000"))
    print(f"[CineVault] AList Media Center running at: http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
