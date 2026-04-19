"""Utility functions for NewsCast-AI."""

import logging
import os
import re
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import yaml


def load_config(config_path: str = "config/config.yaml") -> dict:
    """Load and resolve environment variable references in config.yaml."""
    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Resolve ${ENV_VAR} patterns
    def replace_env(match: re.Match) -> str:
        var_name = match.group(1)
        return os.environ.get(var_name, match.group(0))

    content = re.sub(r"\$\{([^}]+)\}", replace_env, content)
    return yaml.safe_load(content)


def load_sources(sources_path: str = "config/sources.yaml") -> dict:
    """Load RSS sources configuration."""
    with open(sources_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_logger(name: str, log_dir: str = "logs", level: str = "INFO") -> logging.Logger:
    """Create a logger with both file and console handlers."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    log_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(log_level)

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (rotating, 10 MB max, 5 backups)
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = Path(log_dir) / f"{today}.log"
    file_handler = RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def today_str() -> str:
    """Return today's date as YYYY-MM-DD."""
    return datetime.now().strftime("%Y-%m-%d")


def ensure_dir(path: str | Path) -> Path:
    """Create directory if it doesn't exist and return the Path object."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def strip_html(text: str) -> str:
    """Remove HTML tags from a string."""
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", text).strip()


def truncate(text: str, max_chars: int = 500) -> str:
    """Truncate text to max_chars characters, adding ellipsis if needed."""
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "…"
