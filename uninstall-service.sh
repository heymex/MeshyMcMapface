#!/bin/bash

# MeshyMcMapface SystemD Service Uninstaller
# Removes agent and/or server systemd services

# Exit on error, but allow cleanup
set -e
trap 'last_command=$current_command; current_command=$BASH_COMMAND' DEBUG
trap 'if [ $? -ne 0 ]; then print_error "Command \"$last_command\" failed with exit code $?"; fi' EXIT

INSTALL_DIR="/opt/meshymcmapface"
CONFIG_DIR="/etc/meshymcmapface"
LOG_DIR="/var/log/meshymcmapface"
DATA_DIR="/var/lib/meshymcmapface"
USER="meshyuser"

# Uninstallation flags
UNINSTALL_AGENT=false
UNINSTALL_SERVER=false
REMOVE_USER=false
REMOVE_DATA=false
REMOVE_CONFIG=false

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

show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --agent              Uninstall agent only"
    echo "  --server             Uninstall server only"
    echo "  --both               Uninstall both agent and server (default)"
    echo "  --remove-user        Remove the meshyuser system user"
    echo "  --remove-data        Remove data directory ($DATA_DIR)"
    echo "  --remove-config      Remove configuration directory ($CONFIG_DIR)"
    echo "  --purge              Complete removal (services, user, data, config)"
    echo "  -h, --help           Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 --agent           # Remove agent service only"
    echo "  $0 --server          # Remove server service only"
    echo "  $0 --both            # Remove both services but keep data/config"
    echo "  $0 --purge           # Complete removal of everything"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --agent)
            UNINSTALL_AGENT=true
            shift
            ;;
        --server)
            UNINSTALL_SERVER=true
            shift
            ;;
        --both)
            UNINSTALL_AGENT=true
            UNINSTALL_SERVER=true
            shift
            ;;
        --remove-user)
            REMOVE_USER=true
            shift
            ;;
        --remove-data)
            REMOVE_DATA=true
            shift
            ;;
        --remove-config)
            REMOVE_CONFIG=true
            shift
            ;;
        --purge)
            UNINSTALL_AGENT=true
            UNINSTALL_SERVER=true
            REMOVE_USER=true
            REMOVE_DATA=true
            REMOVE_CONFIG=true
            shift
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Default to both if neither specified
if [ "$UNINSTALL_AGENT" = false ] && [ "$UNINSTALL_SERVER" = false ]; then
    UNINSTALL_AGENT=true
    UNINSTALL_SERVER=true
fi

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    print_error "Please run this script as root (sudo)"
    exit 1
fi

if [ "$UNINSTALL_AGENT" = true ] && [ "$UNINSTALL_SERVER" = true ]; then
    print_status "Uninstalling MeshyMcMapface agent and server..."
elif [ "$UNINSTALL_AGENT" = true ]; then
    print_status "Uninstalling MeshyMcMapface agent only..."
else
    print_status "Uninstalling MeshyMcMapface server only..."
fi

# Stop and disable services
if [ "$UNINSTALL_AGENT" = true ]; then
    if systemctl is-active --quiet meshymcmapface-agent; then
        print_status "Stopping meshymcmapface-agent service..."
        systemctl stop meshymcmapface-agent
        print_success "Agent service stopped"
    fi

    if systemctl is-enabled --quiet meshymcmapface-agent 2>/dev/null; then
        print_status "Disabling meshymcmapface-agent service..."
        systemctl disable meshymcmapface-agent
        print_success "Agent service disabled"
    fi

    if [ -f "/etc/systemd/system/meshymcmapface-agent.service" ]; then
        print_status "Removing agent service file..."
        rm -f "/etc/systemd/system/meshymcmapface-agent.service"
        print_success "Agent service file removed"
    fi
fi

if [ "$UNINSTALL_SERVER" = true ]; then
    if systemctl is-active --quiet meshymcmapface-server; then
        print_status "Stopping meshymcmapface-server service..."
        systemctl stop meshymcmapface-server
        print_success "Server service stopped"
    fi

    if systemctl is-enabled --quiet meshymcmapface-server 2>/dev/null; then
        print_status "Disabling meshymcmapface-server service..."
        systemctl disable meshymcmapface-server
        print_success "Server service disabled"
    fi

    if [ -f "/etc/systemd/system/meshymcmapface-server.service" ]; then
        print_status "Removing server service file..."
        rm -f "/etc/systemd/system/meshymcmapface-server.service"
        print_success "Server service file removed"
    fi
fi

# Reload systemd
print_status "Reloading systemd daemon..."
systemctl daemon-reload
systemctl reset-failed 2>/dev/null || true

# Remove installation directory (always safe to remove as it's just code)
if [ -d "$INSTALL_DIR" ]; then
    print_status "Removing installation directory..."
    rm -rf "$INSTALL_DIR"
    print_success "Installation directory removed"
fi

# Remove log directory (safe to remove)
if [ -d "$LOG_DIR" ]; then
    print_status "Removing log directory..."
    rm -rf "$LOG_DIR"
    print_success "Log directory removed"
fi

# Optionally remove configuration directory
if [ "$REMOVE_CONFIG" = true ]; then
    if [ -d "$CONFIG_DIR" ]; then
        print_warning "Removing configuration directory (contains API keys and settings)..."
        rm -rf "$CONFIG_DIR"
        print_success "Configuration directory removed"
    fi
else
    if [ -d "$CONFIG_DIR" ]; then
        print_warning "Configuration directory preserved at $CONFIG_DIR"
        print_warning "Use --remove-config to remove it"
    fi
fi

# Optionally remove data directory
if [ "$REMOVE_DATA" = true ]; then
    if [ -d "$DATA_DIR" ]; then
        print_warning "Removing data directory (contains databases)..."
        rm -rf "$DATA_DIR"
        print_success "Data directory removed"
    fi
else
    if [ -d "$DATA_DIR" ]; then
        print_warning "Data directory preserved at $DATA_DIR"
        print_warning "Use --remove-data to remove it"
    fi
fi

# Optionally remove user
if [ "$REMOVE_USER" = true ]; then
    if id "$USER" &>/dev/null; then
        print_status "Removing system user $USER..."
        userdel "$USER" 2>/dev/null || true
        print_success "User $USER removed"
    fi
else
    if id "$USER" &>/dev/null; then
        print_warning "System user '$USER' preserved"
        print_warning "Use --remove-user to remove it"
    fi
fi

print_success "MeshyMcMapface uninstallation complete!"
echo
if [ "$REMOVE_CONFIG" = false ] || [ "$REMOVE_DATA" = false ] || [ "$REMOVE_USER" = false ]; then
    print_status "To completely remove all traces, run:"
    echo "  sudo $0 --purge"
fi
