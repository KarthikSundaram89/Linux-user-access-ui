#!/bin/bash
# Enterprise Linux Access Portal - Installation Script
# For Amazon Linux 2023

set -euo pipefail

APP_DIR="/opt/linux-access-portal"
APP_USER="linuxportal"
APP_GROUP="linuxportal"

echo "============================================"
echo "  Enterprise Linux Access Portal Installer"
echo "============================================"
echo ""

# Check if running as root
if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: This script must be run as root"
    exit 1
fi

# Step 1: Install system dependencies
echo "[1/8] Installing system dependencies..."
dnf update -y
dnf install -y python3.11 python3.11-pip python3.11-devel \
    nodejs npm \
    nginx \
    gcc gcc-c++ make \
    openssl openssl-devel \
    libffi-devel \
    sqlite

# Step 2: Create application user
echo "[2/8] Creating application user..."
if ! id "$APP_USER" &>/dev/null; then
    useradd -r -s /sbin/nologin -d "$APP_DIR" "$APP_USER"
fi

# Step 3: Create directory structure
echo "[3/8] Creating directory structure..."
mkdir -p "$APP_DIR"/{backend/data,backend/logs,backend/data/ssh_keys,backend/data/uploads,frontend,venv}

# Step 4: Copy application files
echo "[4/8] Copying application files..."
cp -r backend/* "$APP_DIR/backend/"
cp -r frontend/* "$APP_DIR/frontend/"

# Step 5: Set up Python virtual environment
echo "[5/8] Setting up Python environment..."
python3.11 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/backend/requirements.txt"

# Step 6: Build frontend
echo "[6/8] Building frontend..."
cd "$APP_DIR/frontend"
npm install
npm run build

# Step 7: Set up configuration
echo "[7/8] Setting up configuration..."
if [ ! -f "$APP_DIR/backend/.env" ]; then
    cp "$APP_DIR/backend/.env.example" "$APP_DIR/backend/.env"
    # Generate secure secret keys
    SECRET_KEY=$(openssl rand -hex 32)
    SESSION_KEY=$(openssl rand -hex 32)
    sed -i "s/generate-with-openssl-rand-hex-32/$SECRET_KEY/" "$APP_DIR/backend/.env"
    sed -i "s/generate-another-secret-key/$SESSION_KEY/" "$APP_DIR/backend/.env"
    echo "  NOTE: Edit $APP_DIR/backend/.env with your Azure AD, SMTP, and other settings"
fi

# Step 8: Set permissions and install service
echo "[8/8] Setting permissions and installing service..."
chown -R "$APP_USER:$APP_GROUP" "$APP_DIR"
chmod 600 "$APP_DIR/backend/.env"
chmod 700 "$APP_DIR/backend/data/ssh_keys"

# Install systemd service
cp deployment/linux-access-portal.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable linux-access-portal

# Install nginx config
cp deployment/nginx.conf /etc/nginx/conf.d/linux-access-portal.conf
systemctl enable nginx

echo ""
echo "============================================"
echo "  Installation Complete!"
echo "============================================"
echo ""
echo "Next Steps:"
echo "  1. Edit configuration:  vi $APP_DIR/backend/.env"
echo "  2. Configure Azure AD settings (Tenant ID, Client ID, Client Secret)"
echo "  3. Configure SMTP settings"
echo "  4. Update nginx config with your domain and SSL certificates"
echo "  5. Start the service:   systemctl start linux-access-portal"
echo "  6. Start nginx:         systemctl start nginx"
echo "  7. Login at https://your-domain.com"
echo ""
echo "Emergency admin login:"
echo "  Username: admin"
echo "  Password: (set in .env - change immediately!)"
echo ""
