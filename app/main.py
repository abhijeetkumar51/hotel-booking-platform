"""Flask application factory."""

import logging
import sys

from flask import Flask

from app.config import Config
from app.database import close_pool, init_pool, init_schema
from app.routes import api


def create_app(config: Config | None = None) -> Flask:
    """Create and configure the Flask application."""
    # Structured logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )
    logger = logging.getLogger(__name__)

    app = Flask(__name__)

    if config is None:
        config = Config()

    app.config["SECRET_KEY"] = config.SECRET_KEY

    # Store config on app for later access
    app.hotel_config = config  # type: ignore[attr-defined]

    # Initialize database
    try:
        init_pool(config)
        init_schema()
        logger.info("Application started — database ready.")
    except Exception as exc:
        logger.error("Failed to initialize database: %s", exc)
        # Allow the app to start so /health still works; /ready will report 503
        pass

    # Register routes
    app.register_blueprint(api)

    # Teardown
    @app.teardown_appcontext
    def _shutdown(exc):  # noqa: ARG001
        pass  # pool is module-level; closed at process exit

    import atexit

    atexit.register(close_pool)

    return app

