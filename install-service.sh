#!/bin/bash
set -e

# MeshyMcMapface SystemD Service Installer
# Installs both agent and server as systemd services

INSTALL_DIR="/opt/meshymcmapface"
CONFIG_DIR="/etc/meshymcmapface"
LOG_DIR="/var/log/meshymcmapface"
DATA_DIR="/var/lib/meshymcmapface"
USER="meshyuser"
GROUP="meshyuser"

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

print_status "Installing MeshyMcMapface as systemd services..."

# Create user and group
if ! id "$USER" &>/dev/null; then
    print_status "Creating user $USER..."
    useradd --system --home-dir "$INSTALL_DIR" --shell /bin/false --comment "MeshyMcMapface Service User" "$USER"
    print_success "User $USER created"
else
    print_status "User $USER already exists"
fi

# Create directories
print_status "Creating directories..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$CONFIG_DIR"
mkdir -p "$LOG_DIR"
mkdir -p "$DATA_DIR"

# Copy application files
print_status "Copying application files..."
cp -r . "$INSTALL_DIR/"
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

# Install Python dependencies
print_status "Installing Python dependencies..."
pip3 install -r "$INSTALL_DIR/requirements.txt"

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
    cd "$INSTALL_DIR"
    python3 mmm-agent-modular.py --create-config --config "$CONFIG_DIR/agent.ini"
    chown "$USER:$GROUP" "$CONFIG_DIR/agent.ini"
fi

if [ ! -f "$CONFIG_DIR/server.ini" ]; then
    print_status "Creating sample server configuration..."
    cd "$INSTALL_DIR"
    python3 mmm-server.py --create-config --config "$CONFIG_DIR/server.ini"
    chown "$USER:$GROUP" "$CONFIG_DIR/server.ini"
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