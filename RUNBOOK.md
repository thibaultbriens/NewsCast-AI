# RUNBOOK — NewsCast-AI Operations Guide

This document describes how to operate, monitor, and troubleshoot the NewsCast-AI system.

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Check System Status](#check-system-status)
3. [Manual Pipeline Run](#manual-pipeline-run)
4. [API Server Management](#api-server-management)
5. [Log Consultation](#log-consultation)
6. [Troubleshooting](#troubleshooting)
7. [Maintenance](#maintenance)

---

## 1. System Overview

| Component | Description |
|-----------|-------------|
| `news-podcast.timer` | Systemd timer — triggers pipeline daily at 05:55 |
| `news-podcast.service` | Systemd oneshot service — runs `main.py` |
| `news-podcast-api.service` | FastAPI server — serves MP3 files on port 8000 |
| `ollama.service` | Local LLM inference server on port 11434 |

---

## 2. Check System Status

### Timer & Services

```bash
# Check if the timer is active and see next trigger time
sudo systemctl list-timers news-podcast.timer

# Check timer status
sudo systemctl status news-podcast.timer

# Check last pipeline run
sudo systemctl status news-podcast.service

# Check API server
sudo systemctl status news-podcast-api.service

# Check Ollama
sudo systemctl status ollama
```

### Ollama Health

```bash
# Verify Ollama is responding
curl -s http://localhost:11434 && echo "Ollama OK"

# List available models
ollama list

# Pull model if missing
ollama pull llama3.1:8b
```

### API Health

```bash
# Check API health endpoint
curl -s http://localhost:8000/health | python3 -m json.tool

# Get the latest podcast URL
curl -s -I http://localhost:8000/latest

# Download today's podcast
curl -O http://localhost:8000/podcasts/$(date +%Y-%m-%d).mp3
```

---

## 3. Manual Pipeline Run

### Run the full pipeline

```bash
cd /opt/news-podcast

# Run with default topic (all_topics)
sudo -u ubuntu .venv/bin/python3 main.py

# Run a specific topic
sudo -u ubuntu .venv/bin/python3 main.py tech_enterprises
sudo -u ubuntu .venv/bin/python3 main.py geopolitique
sudo -u ubuntu .venv/bin/python3 main.py sport
sudo -u ubuntu .venv/bin/python3 main.py all_topics
```

### Available Topics

| Key | Name | Description |
|-----|------|-------------|
| `all_topics` | Briefing Complet | General news (default) |
| `tech_enterprises` | Actualité Tech | Technology news |
| `geopolitique` | Géopolitique Mondiale | World geopolitics |
| `sport` | Actualité Sportive | Sports news |

### Force re-run (bypass lock)

```bash
# If pipeline crashed and left a stale lock file
rm -f /tmp/news-podcast.lock
sudo -u ubuntu .venv/bin/python3 main.py
```

---

## 4. API Server Management

### Start / Stop / Restart

```bash
sudo systemctl start news-podcast-api.service
sudo systemctl stop news-podcast-api.service
sudo systemctl restart news-podcast-api.service
```

### Reload after config change

```bash
sudo systemctl daemon-reload
sudo systemctl restart news-podcast-api.service
```

### Update API keys in service

```bash
# Edit service file
sudo nano /etc/systemd/system/news-podcast.service

# Reload and restart
sudo systemctl daemon-reload
```

---

## 5. Log Consultation

### Application logs

```bash
# Today's application log
cat /opt/news-podcast/logs/$(date +%Y-%m-%d).log

# Follow live pipeline output
sudo journalctl -u news-podcast.service -f

# Follow API server logs
sudo journalctl -u news-podcast-api.service -f

# Last 50 lines of pipeline log
sudo tail -50 /var/log/news-podcast.log

# Last pipeline errors
sudo tail -50 /var/log/news-podcast-error.log
```

### Systemd journal

```bash
# All logs from news-podcast timer (last 24h)
sudo journalctl -u news-podcast.service --since "24 hours ago"

# All logs from news-podcast API (last 24h)
sudo journalctl -u news-podcast-api.service --since "24 hours ago"
```

---

## 6. Troubleshooting

### Pipeline produces no articles

1. Check NewsAPI key: `echo $NEWSAPI_KEY`
2. Verify network access: `curl -s https://newsapi.org/v2/top-headlines?country=fr&apiKey=TEST | head -c 200`
3. Check RSS fallback: `curl -s https://www.lemonde.fr/rss/une.xml | head -c 500`
4. Review fetcher logs: `grep -i "error\|warning" /opt/news-podcast/logs/$(date +%Y-%m-%d).log`

### Ollama not responding

```bash
sudo systemctl status ollama
sudo systemctl restart ollama
# Wait ~10 seconds then retry
curl http://localhost:11434
```

### Piper TTS binary missing

```bash
which piper || echo "Piper not in PATH"
ls -la /opt/news-podcast/piper-voices/
# Re-run the TTS installation section of install.sh
```

### FFmpeg not found

```bash
which ffmpeg || sudo apt-get install -y ffmpeg
```

### MP3 file not accessible via API

```bash
# Check the file exists
ls -la /opt/news-podcast/output/$(date +%Y-%m-%d)/

# Check API server is running
curl http://localhost:8000/health

# Check firewall (OCI Security List / iptables)
sudo iptables -L INPUT -n | grep 8000
```

### Duplicate pipeline execution

The system uses a lock file at `/tmp/news-podcast.lock`. If the file exists from a crashed run:

```bash
# Check if process is still running
cat /tmp/news-podcast.lock  # prints PID
ps aux | grep main.py

# If process is dead, remove stale lock
rm -f /tmp/news-podcast.lock
```

---

## 7. Maintenance

### Clean up old files (manual)

```bash
# Remove files older than 30 days
find /opt/news-podcast/output -type f -mtime +30 -delete
find /opt/news-podcast/data -type f -mtime +30 -delete
```

### Update Python dependencies

```bash
cd /opt/news-podcast
.venv/bin/pip install --upgrade -r requirements.txt
sudo systemctl restart news-podcast-api.service
```

### Update Ollama model

```bash
ollama pull llama3.1:8b
# Or switch to alternative
ollama pull gemma2:9b
# Then update config/config.yaml: models.llm: "gemma2:9b"
```

### Backup configuration

```bash
cp /opt/news-podcast/config/config.yaml ~/config.yaml.backup
```

### Check disk usage

```bash
du -sh /opt/news-podcast/{data,output,logs,piper-voices}
df -h /opt/news-podcast
```
