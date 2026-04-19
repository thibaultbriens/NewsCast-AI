"""AudioAssembler — Assembles WAV segments into a final MP3 using FFmpeg."""

import subprocess
import tempfile
from pathlib import Path

from src.utils import ensure_dir, get_logger, today_str

logger = get_logger("assembler")


class AudioAssembler:
    """Concatenates WAV segments and encodes them as MP3 via FFmpeg."""

    BITRATE = "128k"
    SAMPLE_RATE = 44100
    CHANNELS = 1  # Mono — sufficient for speech

    def __init__(self, config: dict):  # noqa: ARG002 (config reserved for future use)
        self.config = config

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def assemble(self, wav_paths: list[Path], topic_key: str | None = None) -> Path:
        """Concatenate WAV files and produce a normalised MP3."""
        if not wav_paths:
            raise ValueError("No WAV segments provided to assemble")

        output_path = self._output_path(topic_key)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as concat_file:
            concat_path = Path(concat_file.name)
            for wav in wav_paths:
                # FFmpeg concat demuxer requires 'file' lines with escaped paths
                escaped = str(wav.resolve()).replace("'", "'\\''")
                concat_file.write(f"file '{escaped}'\n")

        logger.info("Assembling %d segment(s) → %s", len(wav_paths), output_path)

        try:
            self._run_ffmpeg(concat_path, output_path)
        finally:
            concat_path.unlink(missing_ok=True)

        size_kb = output_path.stat().st_size // 1024
        logger.info("MP3 assembled: %s (%d KB)", output_path, size_kb)
        return output_path

    # ------------------------------------------------------------------
    # FFmpeg pipeline
    # ------------------------------------------------------------------

    def _run_ffmpeg(self, concat_list: Path, output_path: Path) -> None:
        cmd = [
            "ffmpeg",
            "-y",                          # Overwrite if exists
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_list),
            # Audio normalisation (EBU R128 loudness via dynaudnorm)
            "-af", "dynaudnorm",
            # MP3 encoding
            "-c:a", "libmp3lame",
            "-b:a", self.BITRATE,
            "-ar", str(self.SAMPLE_RATE),
            "-ac", str(self.CHANNELS),
            str(output_path),
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                check=True,
            )
            if result.stderr:
                logger.debug("FFmpeg stderr: %s", result.stderr[-500:])
        except subprocess.CalledProcessError as exc:
            logger.error("FFmpeg failed: %s\nstderr: %s", exc, exc.stderr[-1000:])
            raise
        except FileNotFoundError:
            raise RuntimeError(
                "FFmpeg not found. Install it with: sudo apt-get install -y ffmpeg"
            )

    # ------------------------------------------------------------------
    # Path helper
    # ------------------------------------------------------------------

    def _output_path(self, topic_key: str | None) -> Path:
        date_str = today_str()
        out_dir = ensure_dir(Path("output") / date_str)
        filename = f"{topic_key}_podcast.mp3" if topic_key else "podcast.mp3"
        return out_dir / filename
