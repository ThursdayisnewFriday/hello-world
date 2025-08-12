#!/bin/bash

# Jamf License Reclamation Service Setup Script
# This script sets up the Jamf license reclamation system as a systemd service

set -e

# Configuration
SERVICE_NAME="jamf-license-reclamation"
SERVICE_USER="jamf-service"
INSTALL_DIR="/opt/jamf-license-reclamation"
LOG_DIR="/var/log/jamf-license-reclamation"
PYTHON_BIN="/usr/bin/python3"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root"
        exit 1
    fi
}

check_dependencies() {
    log_info "Checking dependencies..."
    
    # Check Python 3
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 is required but not installed"
        exit 1
    fi
    
    # Check pip
    if ! command -v pip3 &> /dev/null; then
        log_error "pip3 is required but not installed"
        exit 1
    fi
    
    # Check systemctl
    if ! command -v systemctl &> /dev/null; then
        log_error "systemctl is required but not installed (systemd system required)"
        exit 1
    fi
    
    log_info "All dependencies are available"
}

create_user() {
    if id "$SERVICE_USER" &>/dev/null; then
        log_info "User $SERVICE_USER already exists"
    else
        log_info "Creating service user: $SERVICE_USER"
        useradd --system --no-create-home --shell /bin/false "$SERVICE_USER"
    fi
}

setup_directories() {
    log_info "Setting up directories..."
    
    # Create install directory
    mkdir -p "$INSTALL_DIR"
    
    # Create log directory
    mkdir -p "$LOG_DIR"
    
    # Set ownership
    chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
    chown -R "$SERVICE_USER:$SERVICE_USER" "$LOG_DIR"
    
    # Set permissions
    chmod 755 "$INSTALL_DIR"
    chmod 755 "$LOG_DIR"
}

copy_files() {
    log_info "Copying application files..."
    
    # Copy Python files
    cp *.py "$INSTALL_DIR/"
    
    # Copy configuration files
    cp config.ini "$INSTALL_DIR/" 2>/dev/null || log_warn "config.ini not found, will need to be created"
    cp .env.example "$INSTALL_DIR/"
    cp requirements.txt "$INSTALL_DIR/"
    
    # Set ownership
    chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
    
    # Set permissions for sensitive files
    chmod 600 "$INSTALL_DIR/.env" 2>/dev/null || true
    chmod 644 "$INSTALL_DIR"/*.py
}

install_python_dependencies() {
    log_info "Installing Python dependencies..."
    
    # Install in system python (consider using virtual environment for production)
    pip3 install -r "$INSTALL_DIR/requirements.txt"
    
    log_info "Python dependencies installed"
}

create_systemd_service() {
    log_info "Creating systemd service..."
    
    cat > "/etc/systemd/system/${SERVICE_NAME}.service" << EOF
[Unit]
Description=Jamf License Reclamation Service
Documentation=https://github.com/your-org/jamf-license-reclamation
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
Environment=PYTHONPATH=$INSTALL_DIR
ExecStart=$PYTHON_BIN $INSTALL_DIR/main.py --daemon
ExecReload=/bin/kill -HUP \$MAINPID
Restart=always
RestartSec=10
TimeoutStopSec=30

# Security settings
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=$LOG_DIR $INSTALL_DIR
PrivateTmp=yes
ProtectControlGroups=yes
ProtectKernelModules=yes
ProtectKernelTunables=yes
RestrictRealtime=yes
RestrictNamespaces=yes

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=$SERVICE_NAME

[Install]
WantedBy=multi-user.target
EOF

    # Reload systemd
    systemctl daemon-reload
    
    log_info "Systemd service created"
}

setup_logrotate() {
    log_info "Setting up log rotation..."
    
    cat > "/etc/logrotate.d/${SERVICE_NAME}" << EOF
$LOG_DIR/*.log {
    daily
    missingok
    rotate 52
    compress
    delaycompress
    notifempty
    create 644 $SERVICE_USER $SERVICE_USER
    postrotate
        /bin/systemctl reload-or-restart $SERVICE_NAME > /dev/null 2>&1 || true
    endscript
}
EOF

    log_info "Log rotation configured"
}

setup_environment() {
    log_info "Setting up environment configuration..."
    
    if [[ ! -f "$INSTALL_DIR/.env" ]]; then
        cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
        chown "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR/.env"
        chmod 600 "$INSTALL_DIR/.env"
        
        log_warn "Environment file created at $INSTALL_DIR/.env"
        log_warn "Please edit this file with your Jamf and notification settings before starting the service"
    fi
    
    if [[ ! -f "$INSTALL_DIR/config.ini" ]]; then
        log_warn "Configuration file not found. Generating template..."
        sudo -u "$SERVICE_USER" "$PYTHON_BIN" "$INSTALL_DIR/main.py" --generate-config-template
        mv "$INSTALL_DIR/config_template.ini" "$INSTALL_DIR/config.ini"
        chown "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR/config.ini"
        
        log_warn "Configuration template created at $INSTALL_DIR/config.ini"
        log_warn "Please edit this file with your specific settings"
    fi
}

print_next_steps() {
    log_info "Installation completed successfully!"
    echo
    echo "Next steps:"
    echo "1. Edit the configuration file: $INSTALL_DIR/config.ini"
    echo "2. Edit the environment file: $INSTALL_DIR/.env"
    echo "3. Validate the configuration:"
    echo "   sudo -u $SERVICE_USER $PYTHON_BIN $INSTALL_DIR/main.py --validate-config"
    echo "4. Test the service:"
    echo "   sudo -u $SERVICE_USER $PYTHON_BIN $INSTALL_DIR/main.py --run-now --dry-run"
    echo "5. Enable and start the service:"
    echo "   systemctl enable $SERVICE_NAME"
    echo "   systemctl start $SERVICE_NAME"
    echo "6. Check service status:"
    echo "   systemctl status $SERVICE_NAME"
    echo "7. View logs:"
    echo "   journalctl -u $SERVICE_NAME -f"
}

main() {
    log_info "Starting Jamf License Reclamation service setup..."
    
    check_root
    check_dependencies
    create_user
    setup_directories
    copy_files
    install_python_dependencies
    create_systemd_service
    setup_logrotate
    setup_environment
    
    print_next_steps
}

# Handle script arguments
case "${1:-}" in
    --uninstall)
        log_info "Uninstalling Jamf License Reclamation service..."
        systemctl stop "$SERVICE_NAME" 2>/dev/null || true
        systemctl disable "$SERVICE_NAME" 2>/dev/null || true
        rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
        rm -f "/etc/logrotate.d/${SERVICE_NAME}"
        systemctl daemon-reload
        
        # Optionally remove directories (commented out for safety)
        # rm -rf "$INSTALL_DIR"
        # rm -rf "$LOG_DIR"
        # userdel "$SERVICE_USER" 2>/dev/null || true
        
        log_info "Service uninstalled (directories preserved for safety)"
        ;;
    --help|-h)
        echo "Usage: $0 [--uninstall|--help]"
        echo
        echo "Options:"
        echo "  (no options)   Install the service"
        echo "  --uninstall    Uninstall the service"
        echo "  --help         Show this help message"
        ;;
    "")
        main
        ;;
    *)
        log_error "Unknown option: $1"
        echo "Use --help for usage information"
        exit 1
        ;;
esac