"""Centralised logging configuration.

Configured once by the application factory, before extensions initialise, so
that startup problems are captured too. Console output is always on; a
rotating file log is added except under tests (tests should not write files).
"""

import logging
import logging.config
import os
import time

from flask import g, request


def configure_logging(app):
    log_level = str(app.config.get("LOG_LEVEL", "INFO")).upper()
    if log_level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        log_level = "INFO"

    handlers = {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "stream": "ext://sys.stderr",
        }
    }
    root_handlers = ["console"]

    if not app.testing:
        log_dir = os.path.join(app.instance_path, "logs")
        os.makedirs(log_dir, exist_ok=True)
        handlers["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "standard",
            "filename": os.path.join(log_dir, "app.log"),
            "maxBytes": 1_000_000,
            "backupCount": 5,
            "encoding": "utf-8",
        }
        root_handlers.append("file")

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": (
                        "%(asctime)s %(levelname)-8s %(name)s "
                        "[%(module)s:%(lineno)d] %(message)s"
                    )
                }
            },
            "handlers": handlers,
            "root": {"level": log_level, "handlers": root_handlers},
            "loggers": {
                # Werkzeug's per-request lines are useful in dev, noisy above INFO.
                "werkzeug": {"level": "INFO"},
                # SQLAlchemy engine echo is controlled here rather than via
                # the ECHO flag so it obeys LOG_LEVEL=DEBUG uniformly.
                "sqlalchemy.engine": {
                    "level": "INFO" if log_level == "DEBUG" else "WARNING"
                },
            },
        }
    )

    _register_request_timing(app)
    app.logger.info("Logging configured (level=%s)", log_level)


def _register_request_timing(app):
    """Log method, path, status and duration for every request at DEBUG."""

    @app.before_request
    def _start_timer():
        g.request_started_at = time.perf_counter()

    @app.after_request
    def _log_request(response):
        started = g.pop("request_started_at", None)
        if started is not None and not request.path.startswith("/static"):
            duration_ms = (time.perf_counter() - started) * 1000
            app.logger.debug(
                "%s %s -> %s (%.1f ms)",
                request.method,
                request.path,
                response.status_code,
                duration_ms,
            )
        return response
