#!/bin/bash

# MeshyMcMapface SystemD Service Installer
# Installs both agent and server as systemd services

# Exit on error, but allow cleanup
set -e
trap 'last_command=$current_command; current_command=$BASH_COMMAND' DEBUG
trap 'if [ $? -ne 0 ]; then print_error "Command \"$last_command\" failed with exit code $?"; fi' EXIT

INSTALL_DIR="/opt/meshymcmapface"
CONFIG_DIR="/etc/meshymcmapface"
LOG_DIR="/var/log/meshymcmapface"
DATA_DIR="/var/lib/meshymcmapface"
VENV_DIR="$INSTALL_DIR/venv"
USER="meshyuser"
GROUP="meshyuser"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    print_error "Please run this script as root (sudo)"
    exit 1
fi

# Check dependencies
if ! command -v python3 &>/dev/null; then
    print_error "python3 is not installed. Install with: apt install python3 python3-venv python3-pip"
    exit 1
fi

if ! command -v pip3 &>/dev/null; then
    print_error "pip3 is not installed. Install with: apt install python3-pip"
    exit 1
fi

if ! command -v rsync &>/dev/null; then
    print_error "rsync is not installed. Install with: apt install rsync"
    exit 1
fi

print_status "Installing MeshyMcMapface as systemd services..."

# Create user and group
if ! id "$USER" &>/dev/null; then
    print_status "Creating user $USER..."
    useradd --system --home-dir "$INSTALL_DIR" --shell /usr/sbin/nologin --comment "MeshyMcMapface Service User" "$USER"
    print_success "User $USER created"
else
    print_status "User $USER already exists"
fi

# Add user to dialout group for serial port access
if getent group dialout &>/dev/null; then
    print_status "Adding $USER to dialout group for serial port access..."
    usermod -a -G dialout "$USER"
    print_success "User added to dialout group"
else
    print_warning "dialout group not found - serial port access may not work"
fi

# Create directories
print_status "Creating directories..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$CONFIG_DIR"
mkdir -p "$LOG_DIR"
mkdir -p "$DATA_DIR"

# Copy application files selectively
print_status "Copying application files..."

# Stop services if running
systemctl stop meshymcmapface-agent 2>/dev/null || true
systemctl stop meshymcmapface-server 2>/dev/null || true

# Create list of files to copy (exclude venv, git, cache, etc.)
rsync -av --delete \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.pytest_cache' \
    --exclude='venv' \
    --exclude='.venv' \
    --exclude='*.egg-info' \
    --exclude='.DS_Store' \
    --exclude='*.log' \
    --exclude='*.db' \
    --exclude='*.db-journal' \
    "$SCRIPT_DIR/" "$INSTALL_DIR/"

chown -R "$USER:$GROUP" "$INSTALL_DIR"

# Set up configuration directory
chown -R "$USER:$GROUP" "$CONFIG_DIR"
chmod 750 "$CONFIG_DIR"

# Set up log directory
chown -R "$USER:$GROUP" "$LOG_DIR"
chmod 755 "$LOG_DIR"

# Set up data directory
chown -R "$USER:$GROUP" "$DATA_DIR"
chmod 750 "$DATA_DIR"

# Create virtual environment and install dependencies
print_status "Creating Python virtual environment..."
python3 -m venv "$VENV_DIR"
chown -R "$USER:$GROUP" "$VENV_DIR"

print_status "Installing Python dependencies in virtual environment..."
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

# Copy systemd service files
print_status "Installing systemd service files..."
cp "$INSTALL_DIR/systemd/meshymcmapface-agent.service" "/etc/systemd/system/"
cp "$INSTALL_DIR/systemd/meshymcmapface-server.service" "/etc/systemd/system/"

# Reload systemd
print_status "Reloading systemd daemon..."
systemctl daemon-reload

# Create sample configuration files if they don't exist
if [ ! -f "$CONFIG_DIR/agent.ini" ]; then
    print_status "Creating sample agent configuration..."
    "$VENV_DIR/bin/python3" "$INSTALL_DIR/mmm-agent-modular.py" --create-config --config "$CONFIG_DIR/agent.ini"
    chown "$USER:$GROUP" "$CONFIG_DIR/agent.ini"
    chmod 640 "$CONFIG_DIR/agent.ini"
fi

if [ ! -f "$CONFIG_DIR/server.ini" ]; then
    print_status "Creating sample server configuration..."
    "$VENV_DIR/bin/python3" "$INSTALL_DIR/mmm-server.py" --create-config --config "$CONFIG_DIR/server.ini"
    chown "$USER:$GROUP" "$CONFIG_DIR/server.ini"
    chmod 640 "$CONFIG_DIR/server.ini"
fi

print_success "MeshyMcMapface services installed successfully!"
echo
print_status "Next steps:"
echo "1. Edit configuration files:"
echo "   - Agent: $CONFIG_DIR/agent.ini"
echo "   - Server: $CONFIG_DIR/server.ini"
echo
echo "2. Enable and start services:"
echo "   sudo systemctl enable meshymcmapface-agent"
echo "   sudo systemctl start meshymcmapface-agent"
echo "   sudo systemctl enable meshymcmapface-server"
echo "   sudo systemctl start meshymcmapface-server"
echo
echo "3. Check service status:"
echo "   sudo systemctl status meshymcmapface-agent"
echo "   sudo systemctl status meshymcmapface-server"
echo
echo "4. View logs:"
echo "   sudo journalctl -u meshymcmapface-agent -f"
echo "   sudo journalctl -u meshymcmapface-server -f"
echo
print_warning "Remember to configure your Meshtastic device connection in $CONFIG_DIR/agent.ini"