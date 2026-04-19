#!/usr/bin/env python3
"""NewsCast-AI — Main pipeline orchestrator."""

import argparse
import os
import sys
import time
from pathlib import Path

import requests

# Ensure project root is on the Python path when run directly
sys.path.insert(0, str(Path(__file__).parent))

from src.assembler import AudioAssembler
from src.delivery import Delivery
from src.fetcher import NewsFetcher
from src.generator import ScriptGenerator
from src.tts import PiperTTS
from src.utils import get_logger, load_config, today_str

LOCK_FILE = Path("/tmp/news-podcast.lock")
DEFAULT_TOPIC = "all_topics"


def _acquire_lock() -> None:
    """Create lock file or exit if another instance is already running."""
    if LOCK_FILE.exists():
        try:
            pid = int(LOCK_FILE.read_text().strip())
        except (ValueError, OSError):
            pid = None

        if pid:
            # Check whether the process is actually alive
            proc_path = Path(f"/proc/{pid}")
            if proc_path.exists():
                print(f"[LOCK] Another instance is running (PID {pid}). Exiting.", file=sys.stderr)
                sys.exit(1)
            else:
                # Stale lock — process is dead
                LOCK_FILE.unlink(missing_ok=True)

    LOCK_FILE.write_text(str(os.getpid()))


def _release_lock() -> None:
    LOCK_FILE.unlink(missing_ok=True)


def _check_ollama(ollama_url: str, logger) -> bool:
    """Return True if Ollama is reachable."""
    try:
        resp = requests.get(ollama_url, timeout=10)
        if resp.status_code == 200:
            logger.info("Ollama is reachable at %s", ollama_url)
            return True
        logger.error("Ollama responded with HTTP %d", resp.status_code)
        return False
    except requests.RequestException as exc:
        logger.error("Cannot reach Ollama at %s: %s", ollama_url, exc)
        return False


def run_pipeline(topic_key: str, config_path: str = "config/config.yaml") -> None:
    """Execute the full podcast generation pipeline for the given topic."""
    start_time = time.time()
    config = load_config(config_path)
    log_level = config.get("app", {}).get("log_level", "INFO")
    logger = get_logger("main", level=log_level)

    logger.info("=== NewsCast-AI Pipeline Started ===")
    logger.info("Topic: %s | Date: %s", topic_key, today_str())

    # 1. Verify Ollama is available
    ollama_url: str = config.get("models", {}).get("ollama_url", "http://localhost:11434")
    if not _check_ollama(ollama_url, logger):
        logger.error("Ollama is not available — aborting pipeline")
        sys.exit(2)

    # 2. Fetch articles
    fetcher = NewsFetcher(config)
    articles = fetcher.fetch(topic_key)
    if not articles:
        logger.warning("No articles found for topic '%s' — aborting pipeline", topic_key)
        sys.exit(0)
    logger.info("Step 1/5 — Fetched %d article(s)", len(articles))

    # 3. Generate script
    generator = ScriptGenerator(config)
    script = generator.generate(articles, topic_key)
    logger.info("Step 2/5 — Script generated (%d chars)", len(script))

    # 4. Synthesize speech
    tts = PiperTTS(config)
    wav_paths = tts.synthesize(script, topic_key)
    logger.info("Step 3/5 — TTS: %d segment(s)", len(wav_paths))

    # 5. Assemble MP3
    assembler = AudioAssembler(config)
    mp3_path = assembler.assemble(wav_paths, topic_key)
    mp3_size_kb = mp3_path.stat().st_size // 1024
    logger.info("Step 4/5 — MP3 assembled: %s (%d KB)", mp3_path, mp3_size_kb)

    # 6. Deliver
    topic_name = config["topics"].get(topic_key, {}).get("name")
    delivery = Delivery(config)
    discord_ok = delivery.deliver(mp3_path, topic_name)
    logger.info("Step 5/5 — Discord delivery: %s", "OK" if discord_ok else "FAILED (non-blocking)")

    elapsed = time.time() - start_time
    logger.info("=== Pipeline completed in %.1f seconds ===", elapsed)


def main() -> None:
    parser = argparse.ArgumentParser(description="NewsCast-AI — Daily Podcast Generator")
    parser.add_argument(
        "topic",
        nargs="?",
        default=DEFAULT_TOPIC,
        help=f"Topic key from config.yaml (default: {DEFAULT_TOPIC})",
    )
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Path to config.yaml (default: config/config.yaml)",
    )
    args = parser.parse_args()

    _acquire_lock()
    try:
        run_pipeline(args.topic, args.config)
    finally:
        _release_lock()


if __name__ == "__main__":
    main()
