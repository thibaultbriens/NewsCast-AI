"""PiperTTS — Converts a podcast script to WAV audio segments using Piper TTS."""

import subprocess
from pathlib import Path

from src.utils import ensure_dir, get_logger, today_str

logger = get_logger("tts")

VOICE_MAPPING: dict[str, str] = {
    "fr": "fr_FR-siwis-medium",
    "en": "en_US-lessac-medium",
}


class PiperTTS:
    """Converts text to speech using the Piper TTS binary."""

    def __init__(self, config: dict):
        self.config = config
        tts_cfg = config.get("tts", {})
        model_cfg = config.get("models", {})

        self.piper_binary: str = tts_cfg.get("piper_binary", "piper")
        self.voices_dir: Path = Path(tts_cfg.get("voices_dir", "piper-voices"))
        self.length_scale: float = float(tts_cfg.get("length_scale", 1.0))
        self.noise_scale: float = float(tts_cfg.get("noise_scale", 0.667))

        # Determine voice from config
        language: str = config["app"].get("language", "fr")
        voice_mapping: dict = tts_cfg.get("voice_mapping", VOICE_MAPPING)
        default_voice: str = model_cfg.get("tts_voice", VOICE_MAPPING.get(language, "fr_FR-siwis-medium"))
        self.voice_name: str = voice_mapping.get(language, default_voice)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def synthesize(self, script: str, topic_key: str) -> list[Path]:
        """Split script into paragraphs, synthesize each, and return WAV paths."""
        segments_dir = self._segments_dir(topic_key)
        paragraphs = self._split_paragraphs(script)

        if not paragraphs:
            raise ValueError("Script is empty after splitting into paragraphs")

        logger.info(
            "Synthesizing %d paragraph(s) for topic '%s' using voice '%s'",
            len(paragraphs),
            topic_key,
            self.voice_name,
        )

        wav_paths: list[Path] = []
        for idx, paragraph in enumerate(paragraphs, 1):
            out_file = segments_dir / f"segment_{idx:03d}.wav"
            self._run_piper(paragraph, out_file)
            wav_paths.append(out_file)
            logger.debug("Segment %03d synthesized → %s", idx, out_file)

        logger.info("TTS complete: %d segment(s) produced", len(wav_paths))
        return wav_paths

    # ------------------------------------------------------------------
    # Piper execution
    # ------------------------------------------------------------------

    def _run_piper(self, text: str, output_path: Path) -> None:
        model_file = self.voices_dir / f"{self.voice_name}.onnx"
        if not model_file.exists():
            raise FileNotFoundError(
                f"Piper voice model not found: {model_file}. "
                "Run install.sh to download voice models."
            )

        cmd = [
            self.piper_binary,
            "--model", str(model_file),
            "--output_file", str(output_path),
            "--length_scale", str(self.length_scale),
            "--noise_scale", str(self.noise_scale),
        ]

        try:
            result = subprocess.run(
                cmd,
                input=text,
                capture_output=True,
                text=True,
                timeout=120,
                check=True,
            )
            if result.stderr:
                logger.debug("Piper stderr: %s", result.stderr.strip())
        except subprocess.CalledProcessError as exc:
            logger.error("Piper failed for segment: %s\nstderr: %s", exc, exc.stderr)
            raise
        except FileNotFoundError:
            raise RuntimeError(
                f"Piper binary not found at '{self.piper_binary}'. "
                "Run install.sh to install Piper TTS."
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _split_paragraphs(script: str) -> list[str]:
        """Split script on double newlines, filtering empty paragraphs."""
        paragraphs = [p.strip() for p in script.split("\n\n")]
        return [p for p in paragraphs if p]

    def _segments_dir(self, topic_key: str) -> Path:
        date_str = today_str()
        path = Path("data") / "audio" / date_str / topic_key / "segments"
        ensure_dir(path)
        return path
