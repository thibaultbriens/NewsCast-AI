# NewsCast-AI

> **A fully local, automated daily news podcast generator.**  
> Fetches today's headlines, writes a broadcast-quality script with a local LLM, synthesizes speech with Piper TTS, assembles an MP3 with FFmpeg, and delivers it to your Discord channel — every morning at 05:55, with zero cloud dependency.

---

## Table of Contents

1. [Overview](#overview)
2. [How It Works](#how-it-works)
3. [Features](#features)
4. [Requirements](#requirements)
5. [Quick Start](#quick-start)
6. [Configuration](#configuration)
7. [Available Topics](#available-topics)
8. [API Reference](#api-reference)
9. [Project Structure](#project-structure)
10. [Running Manually](#running-manually)
11. [Scheduling with Systemd](#scheduling-with-systemd)
12. [Delivery Channels](#delivery-channels)
13. [Extending the Project](#extending-the-project)
14. [Troubleshooting](#troubleshooting)
15. [Contributing](#contributing)
16. [License](#license)

---

## Overview

NewsCast-AI is a self-hosted pipeline that turns raw news articles into a ready-to-listen MP3 podcast every morning. The entire stack runs locally — no proprietary AI APIs, no cloud speech synthesis, no external audio services. It is designed to run unattended on an always-on Linux server (e.g. an Oracle Cloud free-tier ARM64 VM) and deliver the result directly to your phone via Discord and a local HTTP server.

**Philosophy:** filesystem storage only, no database, no UI, minimal dependencies.

---

## How It Works

```
[05:55 AM] Systemd Timer fires
      │
      ▼
┌─────────────────┐
│  NewsFetcher    │ ◄── NewsAPI (primary) + RSS feeds (fallback)
│  Articles       │     Last 24 h · deduplication · HTML cleaning
└────────┬────────┘
         │ JSON articles
         ▼
┌─────────────────┐
│ ScriptGenerator │ ◄── Ollama  (llama3.1:8b running locally)
│  LLM Scripting  │     800-1 000 words · journalist tone
└────────┬────────┘
         │ Plain-text script
         ▼
┌─────────────────┐
│   PiperTTS      │ ◄── Piper TTS binary  (fr_FR-siwis-medium)
│  Speech Synth   │     Split on paragraphs · WAV segments
└────────┬────────┘
         │ WAV segments
         ▼
┌─────────────────┐
│ AudioAssembler  │ ◄── FFmpeg
│  MP3 Assembly   │     Concat · dynaudnorm · 128 kbps mono
└────────┬────────┘
         │ podcast.mp3
         ▼
┌─────────────────┐
│    Delivery     │ ──► Discord webhook  (file attachment)
│                 │ ──► FastAPI server   (http://IP:8000/podcasts/YYYY-MM-DD.mp3)
└─────────────────┘
```

---

## Features

- **100 % local inference** — Ollama + Piper TTS run on your own hardware; no tokens billed, no data sent to third parties.
- **Dual news sources** — NewsAPI is queried first; if unavailable or unconfigured, the system falls back to curated RSS feeds automatically.
- **Broadcast-quality script structure** — The LLM prompt enforces a five-part narrative: intro → three news dossiers → conclusion (800–1 000 words, ~5–6 minutes of speech).
- **Multiple topics** — Run one pipeline per topic (tech, geopolitics, sport, or a full briefing) by passing a single argument.
- **Concurrent-run protection** — A PID-checked lock file prevents accidental parallel executions.
- **Discord delivery** — The finished MP3 is posted as a file attachment to a private Discord channel.
- **HTTP API** — A lightweight FastAPI server exposes the archive so you can stream or download any episode from a phone browser.
- **Zero-downtime rotation** — Files are stored on disk under `output/YYYY-MM-DD/` and cleaned up after 30 days (configurable).
- **Structured logging** — Every pipeline step is logged with timestamps to both the console and daily rotating log files.

---

## Requirements

### Server

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| OS | Ubuntu 22.04 LTS | Ubuntu 22.04 LTS ARM64 |
| CPU | Any 64-bit | ARM64 (Ampere A1) |
| RAM | 8 GB | 24 GB |
| Disk | 10 GB free | 20 GB free |
| Python | 3.11 | 3.11+ |

### External services (optional)

| Service | Role | Required? |
|---------|------|-----------|
| [NewsAPI](https://newsapi.org) | Primary article source (free tier: 100 req/day) | No — RSS fallback available |
| Discord webhook | Podcast delivery notification | No — file stays on disk |

### Software installed by `install.sh`

- **FFmpeg 4.4+** — audio concatenation and encoding
- **[Ollama](https://ollama.com)** — local LLM runtime (pulls `llama3.1:8b` automatically)
- **[Piper TTS](https://github.com/rhasspy/piper)** — offline neural text-to-speech

---

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/thibaultbriens/NewsCast-AI.git
cd NewsCast-AI
```

### 2. Run the installer (as root)

The installer handles everything: system packages, Python virtualenv, Ollama, Piper TTS and voice models, systemd services, and secrets file creation.

```bash
sudo bash install.sh
```

This takes **5–15 minutes** on a fresh VM (most of the time is spent downloading the `llama3.1:8b` model, ~4.7 GB).

### 3. Set your API keys

```bash
sudo nano /etc/news-podcast/secrets.env
```

```ini
NEWSAPI_KEY=your_newsapi_key_here
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/your/webhook
```

> The file is owned by `root:root` with mode `600`. It is loaded by systemd at runtime and is never committed to the repository.

### 4. Verify the installation

```bash
# Check that Ollama is running
curl -s http://localhost:11434 && echo "Ollama OK"

# Check the API server
curl -s http://localhost:8000/health | python3 -m json.tool
```

### 5. Run a test pipeline

```bash
cd /opt/news-podcast
sudo -u ubuntu .venv/bin/python3 main.py all_topics
```

A podcast MP3 will appear under `output/YYYY-MM-DD/` and be posted to Discord (if configured).

---

## Configuration

All runtime behaviour is controlled by two YAML files.

### `config/config.yaml`

```yaml
app:
  language: "fr"          # ISO 639-1 — drives LLM prompt language and TTS voice selection
  timezone: "Europe/Paris"
  retention_days: 30      # How long to keep output files on disk
  log_level: "INFO"       # INFO or DEBUG

topics:
  all_topics:
    name: "Briefing Complet"
    queries: ["actualité", "politique", "économie", "sport", "technologie"]
    language: "fr"
    region: null           # null = worldwide; "fr" = France only (NewsAPI top-headlines)
    max_articles: 20

models:
  llm: "llama3.1:8b"      # Any model available in your Ollama instance
  tts_voice: "fr_FR-siwis-medium"
  ollama_url: "http://localhost:11434"
  llm_temperature: 0.7
  llm_num_predict: 1500
  llm_top_p: 0.9

tts:
  piper_binary: "piper"   # Path to Piper binary, or just "piper" if it is in PATH
  voices_dir: "piper-voices"
  length_scale: 1.0       # Speech speed — increase for slower delivery
  noise_scale: 0.667
  voice_mapping:
    fr: "fr_FR-siwis-medium"
    en: "en_US-lessac-medium"

delivery:
  discord_webhook_url: "${DISCORD_WEBHOOK_URL}"  # Resolved from environment
  server_port: 8000
  server_host: "0.0.0.0"

newsapi:
  api_key: "${NEWSAPI_KEY}"   # Resolved from environment
  base_url: "https://newsapi.org/v2"
```

> **Environment variables** — any `${VAR}` placeholder in the YAML is replaced at load-time with the matching environment variable. If the variable is not set, the placeholder is kept as-is (which disables the relevant feature gracefully).

### `config/sources.yaml`

Defines RSS feeds used when NewsAPI is unavailable or returns no results.

```yaml
rss_feeds:
  tech:
    - "https://www.lemonde.fr/technologies/rss_full.xml"
    - "https://techcrunch.com/feed/"
  geopolitique:
    - "https://www.lemonde.fr/international/rss_full.xml"
    - "https://feeds.bbci.co.uk/news/world/rss.xml"
  sport:
    - "https://www.lequipe.fr/rss/actu_rss.xml"
  all_topics:
    - "https://www.lemonde.fr/rss/une.xml"
    - "https://feeds.bbci.co.uk/news/rss.xml"
```

Add or remove feeds freely. The fetcher matches the topic key first, then falls back to `all_topics`.

---

## Available Topics

| CLI argument | Display name | Default queries |
|---|---|---|
| `all_topics` *(default)* | Briefing Complet | actualité, politique, économie, sport, technologie |
| `tech_enterprises` | Actualité Tech | Apple, Google, Microsoft, NVIDIA, OpenAI |
| `geopolitique` | Géopolitique Mondiale | géopolitique, diplomatie, conflit, ONU |
| `sport` | Actualité Sportive | football, NBA, JO, coupe du monde |

You can add your own topics by adding an entry under `topics:` in `config/config.yaml` — no code change required.

---

## API Reference

The FastAPI server runs on port `8000` and exposes three endpoints.

### `GET /podcasts/{date}.mp3`

Download the podcast for a specific date.

```
GET /podcasts/2026-04-19.mp3
```

| Response | Meaning |
|----------|---------|
| `200 OK` | Returns the MP3 file (`Content-Type: audio/mpeg`) |
| `400 Bad Request` | `date` is not in `YYYY-MM-DD` format |
| `404 Not Found` | No podcast was generated for that date |

**Example:**
```bash
# Stream on the server
curl http://localhost:8000/podcasts/2026-04-19.mp3 --output episode.mp3

# From a phone on the same network
open http://192.168.1.100:8000/podcasts/2026-04-19.mp3
```

---

### `GET /latest`

Redirects (`307`) to the most recent available podcast (looks back up to 30 days).

```bash
curl -L http://localhost:8000/latest --output latest.mp3
```

---

### `GET /health`

Returns the operational status of the API server and Ollama.

```bash
curl -s http://localhost:8000/health | python3 -m json.tool
```

```json
{
  "status": "ok",
  "ollama": "ok"
}
```

| `status` field | HTTP code | Meaning |
|---|---|---|
| `ok` | `200` | All systems operational |
| `degraded` | `503` | Ollama is unreachable |

---

## Project Structure

```
NewsCast-AI/
├── main.py                  # Pipeline entry point & CLI
├── requirements.txt         # Python dependencies
├── install.sh               # One-shot installer for Ubuntu ARM64
├── specs.md                 # Full technical specifications
├── RUNBOOK.md               # Operational runbook
│
├── config/
│   ├── config.yaml          # Main configuration (topics, models, delivery)
│   └── sources.yaml         # RSS fallback feeds
│
├── src/
│   ├── fetcher.py           # NewsFetcher — NewsAPI + RSS, dedup, cleaning
│   ├── generator.py         # ScriptGenerator — Ollama LLM scripting
│   ├── tts.py               # PiperTTS — text-to-speech via Piper binary
│   ├── assembler.py         # AudioAssembler — FFmpeg MP3 encoding
│   ├── delivery.py          # Delivery — Discord webhook
│   ├── api.py               # FastAPI HTTP server
│   └── utils.py             # Shared helpers (config, logging, text utils)
│
├── systemd/
│   ├── news-podcast.service      # Pipeline oneshot service
│   ├── news-podcast.timer        # Daily timer (05:55)
│   └── news-podcast-api.service  # FastAPI server daemon
│
├── piper-voices/            # Voice model files (.onnx) — populated by install.sh
│
├── data/                    # Runtime data (gitignored)
│   ├── raw/YYYY-MM-DD/      # Fetched articles (JSON)
│   ├── scripts/YYYY-MM-DD/  # Generated scripts (TXT)
│   └── audio/YYYY-MM-DD/    # WAV segments
│
├── output/                  # Final MP3 files (gitignored)
│   └── YYYY-MM-DD/
│       └── {topic}_podcast.mp3
│
└── logs/                    # Application logs (gitignored)
    └── YYYY-MM-DD.log
```

---

## Running Manually

```bash
cd /opt/news-podcast

# Default topic (all_topics)
sudo -u ubuntu .venv/bin/python3 main.py

# Specific topic
sudo -u ubuntu .venv/bin/python3 main.py tech_enterprises
sudo -u ubuntu .venv/bin/python3 main.py geopolitique
sudo -u ubuntu .venv/bin/python3 main.py sport

# Custom config file
sudo -u ubuntu .venv/bin/python3 main.py all_topics --config /path/to/my-config.yaml
```

If a previous run crashed and left a stale lock:

```bash
rm -f /tmp/news-podcast.lock
```

---

## Scheduling with Systemd

The installer registers three systemd units.

| Unit | Type | Trigger |
|------|------|---------|
| `news-podcast.timer` | Timer | Daily at 05:55 |
| `news-podcast.service` | Oneshot | Fired by the timer |
| `news-podcast-api.service` | Persistent | Starts at boot, auto-restarts |

```bash
# Verify next scheduled run
sudo systemctl list-timers news-podcast.timer

# Check last pipeline run status
sudo systemctl status news-podcast.service

# Restart the API server
sudo systemctl restart news-podcast-api.service

# View live pipeline logs
sudo journalctl -u news-podcast.service -f
```

To change the schedule, edit `/etc/systemd/system/news-podcast.timer` and run `sudo systemctl daemon-reload`.

---

## Delivery Channels

### Discord

Set `DISCORD_WEBHOOK_URL` in `/etc/news-podcast/secrets.env`. The MP3 is attached directly to the webhook message (Discord limit: 25 MB; a 6-minute podcast at 128 kbps is ~6 MB). If the file exceeds the limit, a text-only notification is sent instead.

### Direct HTTP download

The API server is accessible at `http://<SERVER_IP>:8000`. To expose it to the internet, open port `8000` in your firewall or OCI Security List. No authentication is required by default (MVP); a JWT middleware can be added for multi-user deployments.

---

## Extending the Project

### Adding a new topic

Edit `config/config.yaml` and add an entry under `topics:`:

```yaml
topics:
  finance:
    name: "Finance & Marchés"
    queries: ["bourse", "CAC 40", "crypto", "BCE", "inflation"]
    language: "fr"
    region: null
    max_articles: 15
```

Then run:

```bash
python3 main.py finance
```

### Switching the LLM

Any model available in your Ollama instance works. Update `models.llm` in `config/config.yaml`:

```yaml
models:
  llm: "gemma2:9b"    # or mistral, llama3.2:3b, etc.
```

Pull the model first: `ollama pull gemma2:9b`

### Adding a new language / voice

1. Download the Piper voice files (`.onnx` + `.onnx.json`) from [Hugging Face](https://huggingface.co/rhasspy/piper-voices) into `piper-voices/`.
2. Add a mapping in `config/config.yaml`:

```yaml
tts:
  voice_mapping:
    fr: "fr_FR-siwis-medium"
    en: "en_US-lessac-medium"
    de: "de_DE-thorsten-medium"    # ← new
```

3. Set `app.language: "de"` (or per-topic via `topics.<key>.language`).

### Adding an RSS feed

Edit `config/sources.yaml` and add the feed URL under the relevant topic key:

```yaml
rss_feeds:
  tech:
    - "https://www.lemonde.fr/technologies/rss_full.xml"
    - "https://arstechnica.com/feed/"    # ← new
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| "No articles found" | NewsAPI key invalid or quota exhausted | Check `NEWSAPI_KEY`; RSS fallback activates automatically |
| "Ollama is not available" | Ollama service not running | `sudo systemctl restart ollama` |
| "Piper binary not found" | Piper not installed or not in PATH | Re-run the TTS section of `install.sh` |
| "FFmpeg not found" | FFmpeg not installed | `sudo apt-get install -y ffmpeg` |
| Pipeline runs twice simultaneously | Stale lock file from a crash | `rm -f /tmp/news-podcast.lock` |
| Discord delivery fails | Wrong or expired webhook URL | Update `DISCORD_WEBHOOK_URL` in `/etc/news-podcast/secrets.env` |
| API returns 404 for today | Pipeline not yet run today | Run manually or check timer: `systemctl list-timers` |

For detailed diagnostics, see the [RUNBOOK](RUNBOOK.md).

---

## Contributing

Contributions are welcome. Please follow these steps:

1. **Fork** the repository and create a feature branch from `main`.
2. **Install** dev dependencies: `pip install -r requirements.txt`
3. **Make your changes** — keep modules focused on their single responsibility.
4. **Test** your changes by running the pipeline manually against a test topic.
5. **Open a pull request** with a clear description of what you changed and why.

### Areas where contributions are especially welcome

- Additional language / voice support
- New delivery channels (email, Telegram, ntfy, etc.)
- A `--dry-run` mode that generates the script without synthesising audio
- Docker / Podman compose setup
- Unit tests for the fetcher, generator, and assembler modules

---

## License

This project is released under the [MIT License](LICENSE).

---

*Built for personal use on [Oracle Cloud Infrastructure](https://www.oracle.com/cloud/free/) (ARM64 Ampere A1 free tier).*