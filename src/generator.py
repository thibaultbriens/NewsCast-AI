"""ScriptGenerator — Transforms news articles into a podcast script using Ollama."""

import json
from datetime import datetime
from pathlib import Path

import requests

from src.utils import ensure_dir, get_logger, today_str

logger = get_logger("generator")

SYSTEM_PROMPT = """Tu es un journaliste professionnel rédigeant le script d'un podcast d'actualité \
matinal de 5 à 6 minutes. Le public est un particulier curieux mais non spécialiste.

CONTRAINTES ABSOLUES :
- Langue : {language} (ex: Français)
- Durée : 800 à 1000 mots (correspond à ~5-6 minutes de parole)
- Format : Texte brut, aucun markdown, aucun titre de section explicite
- Structure narrative obligatoire :
  1. INTRO (60-80 mots) : Date du jour, accroche, présentation des 3 sujets principaux
  2. DOSSIER 1 (200-250 mots) : Sujet le plus important. Contexte, fait clé, implication
  3. DOSSIER 2 (200-250 mots) : Deuxième sujet. Angle différent ou actualité complémentaire
  4. DOSSIER 3 (150-200 mots) : Troisième sujet ou actualité rapide
  5. CONCLUSION (60-80 mots) : Récap des points clés, transition vers la journée

TON : Professionnel mais accessible. Pas de jargon. Transitions naturelles entre sujets.
INTERDICTION : Ne mentionne pas que tu es une IA. Ne cite pas "selon les articles".
Raconte l'actualité comme un journaliste le ferait à l'antenne.

ARTICLES SOURCE :
{articles}"""


class ScriptGenerator:
    """Generates a podcast script from articles using a local Ollama LLM."""

    def __init__(self, config: dict):
        self.config = config
        model_cfg = config.get("models", {})
        self.ollama_url: str = model_cfg.get("ollama_url", "http://localhost:11434")
        self.model: str = model_cfg.get("llm", "llama3.1:8b")
        self.temperature: float = float(model_cfg.get("llm_temperature", 0.7))
        self.num_predict: int = int(model_cfg.get("llm_num_predict", 1500))
        self.top_p: float = float(model_cfg.get("llm_top_p", 0.9))

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def generate(self, articles: list[dict], topic_key: str) -> str:
        """Generate a podcast script from the given articles."""
        if not articles:
            raise ValueError("Cannot generate script: no articles provided")

        language = self.config["app"].get("language", "fr")
        articles_text = self._format_articles(articles)
        prompt = SYSTEM_PROMPT.format(language=language, articles=articles_text)

        logger.info(
            "Generating script for topic '%s' using model '%s' (%d articles)",
            topic_key,
            self.model,
            len(articles),
        )

        script = self._call_ollama(prompt)
        logger.info("Script generated: %d characters", len(script))

        out_path = self._save(script, topic_key)
        logger.info("Script saved to %s", out_path)
        return script

    # ------------------------------------------------------------------
    # Ollama API call
    # ------------------------------------------------------------------

    def _call_ollama(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.num_predict,
                "top_p": self.top_p,
            },
        }

        try:
            resp = requests.post(
                f"{self.ollama_url}/api/generate",
                json=payload,
                timeout=300,
            )
            resp.raise_for_status()
            data = resp.json()

            tokens = data.get("eval_count")
            if tokens:
                logger.info("Ollama generated %d tokens", tokens)

            return data.get("response", "").strip()

        except requests.RequestException as exc:
            logger.error("Ollama API call failed: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_articles(articles: list[dict]) -> str:
        lines: list[str] = []
        for i, art in enumerate(articles, 1):
            title = art.get("title", "Sans titre")
            description = art.get("description", "")
            source = art.get("source", "")
            published = art.get("published_at", "")
            lines.append(
                f"[{i}] {title}\n"
                f"Source: {source} | Publié: {published}\n"
                f"{description}\n"
            )
        return "\n".join(lines)

    def _save(self, script: str, topic_key: str) -> Path:
        date_str = today_str()
        out_dir = ensure_dir(Path("data") / "scripts" / date_str)
        out_file = out_dir / f"{topic_key}_script.txt"
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(script)
        return out_file
