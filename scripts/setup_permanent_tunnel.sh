#!/usr/bin/bash
# Market Intelligence Lab — Autonomous Cloudflare Tunnel Service Setup (Milestone B6.5)
# Configures a persistent named Cloudflare tunnel running as a Linux Mint / Ubuntu systemd daemon.
set -e

TUNNEL_NAME="${1:-market-lab-tunnel}"
CONFIG_DIR="/etc/cloudflared"
USER_CONFIG_DIR="$HOME/.cloudflared"

echo "================================================================="
echo " Market Intelligence Lab: Permanent Cloudflare Tunnel Daemon Setup"
echo " Milestone: B6.5 (Autonomous Infrastructure & Systemd Daemon)"
echo " Tunnel Target: http://localhost:8000"
echo " Named Tunnel: ${TUNNEL_NAME}"
echo "================================================================="

# 1. Verify cloudflared binary
if ! command -v cloudflared &> /dev/null; then
    echo "[!] cloudflared not found in PATH."
    echo "[*] Downloading and installing official cloudflared deb package..."
    TEMP_DEB="/tmp/cloudflared-linux-amd64.deb"
    curl -fsSL -o "$TEMP_DEB" https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
    sudo dpkg -i "$TEMP_DEB" || sudo apt-get install -f -y
    rm -f "$TEMP_DEB"
    echo "[✓] cloudflared successfully installed: $(cloudflared --version)"
else
    echo "[✓] cloudflared detected: $(cloudflared --version)"
fi

# 2. Check credentials & login status
mkdir -p "$USER_CONFIG_DIR"
if [ ! -f "$USER_CONFIG_DIR/cert.pem" ] && [ ! -f "$CONFIG_DIR/cert.pem" ]; then
    echo ""
    echo "[*] Cloudflare authentication certificate cert.pem not found."
    echo "[*] Opening Cloudflare browser login for domain association..."
    cloudflared tunnel login || true
fi

# 3. Create or inspect named tunnel
echo ""
echo "[*] Checking status of named tunnel: ${TUNNEL_NAME}..."
TUNNEL_INFO=$(cloudflared tunnel list | grep -w "$TUNNEL_NAME" || true)

if [ -z "$TUNNEL_INFO" ]; then
    echo "[*] Creating persistent named tunnel: ${TUNNEL_NAME}..."
    cloudflared tunnel create "$TUNNEL_NAME" || true
    TUNNEL_INFO=$(cloudflared tunnel list | grep -w "$TUNNEL_NAME" || true)
fi

TUNNEL_ID=$(echo "$TUNNEL_INFO" | awk '{print $1}')

if [ -n "$TUNNEL_ID" ]; then
    echo "[✓] Active Tunnel ID: ${TUNNEL_ID}"
    CRED_SRC="$USER_CONFIG_DIR/${TUNNEL_ID}.json"
else
    echo "[!] Warning: Named tunnel ID could not be retrieved automatically."
    echo "[!] Setting placeholder tunnel ID for template configuration."
    TUNNEL_ID="YOUR_TUNNEL_UUID"
    CRED_SRC="$CONFIG_DIR/${TUNNEL_ID}.json"
fi

# 4. Generate persistent systemd config file
echo ""
echo "[*] Generating Cloudflare systemd configuration..."
sudo mkdir -p "$CONFIG_DIR"

# Copy credentials if available
if [ -f "$CRED_SRC" ] && [ "$CRED_SRC" != "$CONFIG_DIR/${TUNNEL_ID}.json" ]; then
    sudo cp "$CRED_SRC" "$CONFIG_DIR/${TUNNEL_ID}.json"
    sudo chmod 600 "$CONFIG_DIR/${TUNNEL_ID}.json"
fi

CONFIG_FILE="/etc/cloudflared/config.yml"
sudo tee "$CONFIG_FILE" > /dev/null <<EOF
# Market Intelligence Lab - Autonomous Cloudflare Tunnel Configuration
tunnel: ${TUNNEL_ID}
credentials-file: /etc/cloudflared/${TUNNEL_ID}.json

ingress:
  # Map public endpoint to local FastAPI backend
  - hostname: market-lab-api.yourdomain.com
    service: http://localhost:8000
    originRequest:
      connectTimeout: 30s
      noTLSVerify: false
  # Catch-all status fallback
  - service: http_status:404
EOF

sudo chmod 644 "$CONFIG_FILE"
echo "[✓] Configuration written to $CONFIG_FILE"

# 5. Install systemd service daemon
echo ""
echo "[*] Configuring autonomous systemd daemon..."
if [ -f "/etc/systemd/system/cloudflared.service" ]; then
    echo "[✓] Existing cloudflared.service detected. Reloading daemon..."
    sudo systemctl daemon-reload
else
    echo "[*] Installing cloudflared system service..."
    sudo cloudflared service install || true
fi

# Enable and start systemd daemon
echo "[*] Enabling and starting cloudflared daemon..."
sudo systemctl enable cloudflared 2>/dev/null || true
sudo systemctl restart cloudflared 2>/dev/null || sudo systemctl start cloudflared 2>/dev/null || true

# 6. Status & Vercel Mapping Summary
echo ""
echo "================================================================="
echo " [✓] Cloudflare Autonomous Service Deployment Configured"
echo "================================================================="
echo " Systemd Service: sudo systemctl status cloudflared"
echo " Live Logs:       sudo journalctl -u cloudflared -f"
echo " Config File:     /etc/cloudflared/config.yml"
echo " Local Ingress:   http://localhost:8000"
echo ""
echo " Vercel Environment Configuration:"
echo " In your Vercel Project Settings -> Environment Variables, configure:"
echo "   NEXT_PUBLIC_API_URL = https://market-lab-api.yourdomain.com/api/v1"
echo "================================================================="
