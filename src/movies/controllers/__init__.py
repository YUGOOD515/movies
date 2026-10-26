"""Controllers package exports."""
from movies.controllers.api_controller import api_bp
from movies.controllers.page_controller import page_bp

__all__ = ["page_bp", "api_bp"]
