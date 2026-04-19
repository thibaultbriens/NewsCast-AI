"""Delivery — Sends the final podcast to Discord and logs availability."""

from datetime import datetime
from pathlib import Path

import requests

from src.utils import get_logger

logger = get_logger("delivery")


class Delivery:
    """Delivers the podcast MP3 via Discord webhook."""

    MAX_DISCORD_BYTES = 25 * 1024 * 1024  # 25 MB Discord limit

    def __init__(self, config: dict):
        self.config = config
        delivery_cfg = config.get("delivery", {})
        self.webhook_url: str = delivery_cfg.get("discord_webhook_url", "")
        self.server_host: str = delivery_cfg.get("server_host", "0.0.0.0")
        self.server_port: int = int(delivery_cfg.get("server_port", 8000))

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def deliver(self, mp3_path: Path, topic_name: str | None = None) -> bool:
        """Send podcast to Discord. Returns True on success."""
        if not mp3_path.exists():
            logger.error("MP3 file not found: %s", mp3_path)
            return False

        date_str = datetime.now().strftime("%Y-%m-%d")
        topic_label = f" — {topic_name}" if topic_name else ""
        message = f"📰 Votre briefing du {date_str}{topic_label} est prêt."

        success = self._send_discord(mp3_path, message)
        self._log_url(mp3_path, date_str)
        return success

    # ------------------------------------------------------------------
    # Discord
    # ------------------------------------------------------------------

    def _send_discord(self, mp3_path: Path, message: str) -> bool:
        if not self.webhook_url or self.webhook_url.startswith("${"):
            logger.warning("Discord webhook URL not configured — skipping Discord delivery")
            return False

        file_size = mp3_path.stat().st_size
        if file_size > self.MAX_DISCORD_BYTES:
            logger.warning(
                "MP3 file is %.1f MB — exceeds Discord 25 MB limit, skipping attachment",
                file_size / (1024 * 1024),
            )
            # Send text-only message with URL
            return self._send_discord_text(message)

        try:
            with open(mp3_path, "rb") as f:
                resp = requests.post(
                    self.webhook_url,
                    data={"content": message},
                    files={"file": (mp3_path.name, f, "audio/mpeg")},
                    timeout=60,
                )

            if resp.status_code == 204:
                logger.info("Discord delivery successful")
                return True
            else:
                logger.error(
                    "Discord webhook returned HTTP %d: %s", resp.status_code, resp.text[:200]
                )
                return False

        except requests.RequestException as exc:
            logger.error("Discord delivery failed: %s", exc)
            return False

    def _send_discord_text(self, message: str) -> bool:
        """Send a text-only message to Discord (no file attachment)."""
        try:
            resp = requests.post(
                self.webhook_url,
                json={"content": message},
                timeout=30,
            )
            if resp.status_code == 204:
                logger.info("Discord text-only delivery successful")
                return True
            logger.error("Discord text-only webhook returned HTTP %d", resp.status_code)
            return False
        except requests.RequestException as exc:
            logger.error("Discord text-only delivery failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Logging the download URL
    # ------------------------------------------------------------------

    def _log_url(self, mp3_path: Path, date_str: str) -> None:
        host = self.server_host if self.server_host != "0.0.0.0" else "<SERVER_IP>"
        url = f"http://{host}:{self.server_port}/podcasts/{date_str}.mp3"
        logger.info("Podcast available at: %s", url)
        logger.info("Direct file path: %s", mp3_path.resolve())
