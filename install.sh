#!/usr/bin/env bash
# install.sh — NewsCast-AI installation script for Ubuntu 22.04 ARM64 (Oracle Cloud)
# Run as root or with sudo
set -euo pipefail

INSTALL_DIR="/opt/news-podcast"
SERVICE_USER="ubuntu"
PIPER_VERSION="2.0.0"
PIPER_ARCH="aarch64"  # ARM64
PIPER_RELEASE_URL="https://github.com/rhasspy/piper/releases/download/${PIPER_VERSION}/piper_linux_${PIPER_ARCH}.tar.gz"
VOICES_DIR="${INSTALL_DIR}/piper-voices"
PIPER_VOICES_BASE="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"

echo "=== NewsCast-AI Installation ==="
echo "Install directory: ${INSTALL_DIR}"

# ─── System Dependencies ────────────────────────────────────────────────────

echo "[1/6] Installing system dependencies..."
apt-get update -qq
apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-venv \
    python3-pip \
    ffmpeg \
    curl \
    tar \
    logrotate

# ─── Project Directory & Permissions ────────────────────────────────────────

echo "[2/6] Setting up project directory..."
mkdir -p "${INSTALL_DIR}"/{config,data/raw,data/scripts,data/audio,output,piper-voices,logs}
cp -r . "${INSTALL_DIR}/"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"
chmod 750 "${INSTALL_DIR}/data" "${INSTALL_DIR}/output"

# ─── Python Virtual Environment & Dependencies ──────────────────────────────

echo "[3/6] Installing Python dependencies..."
python3.11 -m venv "${INSTALL_DIR}/.venv"
"${INSTALL_DIR}/.venv/bin/pip" install --upgrade pip --quiet
"${INSTALL_DIR}/.venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt" --quiet


# ─── Ollama Installation ─────────────────────────────────────────────────────

echo "[4/6] Installing Ollama..."
if ! command -v ollama &>/dev/null; then
    curl -fsSL https://ollama.com/install.sh | sh
else
    echo "  Ollama already installed, skipping."
fi

# Enable and start ollama service
systemctl enable ollama
systemctl start ollama
echo "  Waiting for Ollama to start..."
sleep 5

# Pull the LLM model
echo "  Pulling llama3.1:8b model (this may take several minutes)..."
ollama pull llama3.1:8b

# ─── Piper TTS Installation ──────────────────────────────────────────────────

echo "[5/6] Installing Piper TTS..."
PIPER_TMP="/tmp/piper_install"
mkdir -p "${PIPER_TMP}"
curl -L "${PIPER_RELEASE_URL}" -o "${PIPER_TMP}/piper.tar.gz"
tar -xzf "${PIPER_TMP}/piper.tar.gz" -C "${PIPER_TMP}"
install -m 755 "${PIPER_TMP}/piper/piper" /usr/local/bin/piper
rm -rf "${PIPER_TMP}"
echo "  Piper installed at /usr/local/bin/piper"

# Download voice models
echo "  Downloading French voice (fr_FR-siwis-medium)..."
mkdir -p "${VOICES_DIR}"
curl -L "${PIPER_VOICES_BASE}/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx" \
    -o "${VOICES_DIR}/fr_FR-siwis-medium.onnx"
curl -L "${PIPER_VOICES_BASE}/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx.json" \
    -o "${VOICES_DIR}/fr_FR-siwis-medium.onnx.json"

echo "  Downloading English voice (en_US-lessac-medium)..."
curl -L "${PIPER_VOICES_BASE}/en/en_US/lessac/medium/en_US-lessac-medium.onnx" \
    -o "${VOICES_DIR}/en_US-lessac-medium.onnx"
curl -L "${PIPER_VOICES_BASE}/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json" \
    -o "${VOICES_DIR}/en_US-lessac-medium.onnx.json"

chown -R "${SERVICE_USER}:${SERVICE_USER}" "${VOICES_DIR}"

# ─── Systemd Services ────────────────────────────────────────────────────────

echo "[6/6] Installing systemd services..."

# Create secrets file with restricted permissions (never commit secrets to files in /etc)
SECRETS_DIR="/etc/news-podcast"
mkdir -p "${SECRETS_DIR}"
if [ ! -f "${SECRETS_DIR}/secrets.env" ]; then
    cat > "${SECRETS_DIR}/secrets.env" << 'SECRETS'
NEWSAPI_KEY=REPLACE_WITH_YOUR_NEWSAPI_KEY
DISCORD_WEBHOOK_URL=REPLACE_WITH_YOUR_DISCORD_WEBHOOK_URL
SECRETS
    chmod 600 "${SECRETS_DIR}/secrets.env"
    chown root:root "${SECRETS_DIR}/secrets.env"
    echo "  Created ${SECRETS_DIR}/secrets.env — EDIT IT with your API keys before use!"
fi

cp "${INSTALL_DIR}/systemd/news-podcast.service" /etc/systemd/system/
cp "${INSTALL_DIR}/systemd/news-podcast.timer" /etc/systemd/system/
cp "${INSTALL_DIR}/systemd/news-podcast-api.service" /etc/systemd/system/

systemctl daemon-reload

# Enable and start API server
systemctl enable news-podcast-api.service
systemctl start news-podcast-api.service

# Enable timer (does NOT start immediately — fires at 5:55 AM)
systemctl enable news-podcast.timer
systemctl start news-podcast.timer

# ─── Logrotate ───────────────────────────────────────────────────────────────

cat > /etc/logrotate.d/news-podcast << 'EOF'
/var/log/news-podcast*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 640 ubuntu ubuntu
}
EOF

# ─── Post-Install Instructions ───────────────────────────────────────────────

echo ""
echo "=== Installation Complete ==="
echo ""
echo "NEXT STEPS:"
echo "1. Edit ${INSTALL_DIR}/systemd/news-podcast.service and set your API keys:"
echo "   Environment=\"NEWSAPI_KEY=YOUR_KEY\""
echo "   Environment=\"DISCORD_WEBHOOK_URL=YOUR_WEBHOOK_URL\""
echo "   Then run: sudo systemctl daemon-reload"
echo ""
echo "2. (Optional) Test the pipeline manually:"
echo "   sudo -u ubuntu ${INSTALL_DIR}/.venv/bin/python3 ${INSTALL_DIR}/main.py all_topics"
echo ""
echo "3. Check API server status:"
echo "   sudo systemctl status news-podcast-api.service"
echo "   curl http://localhost:8000/health"
echo ""
echo "4. Check timer status:"
echo "   sudo systemctl list-timers news-podcast.timer"
