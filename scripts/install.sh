#!/bin/bash
# Kunming Agent Installation Script
# Usage: curl -fsSL https://raw.githubusercontent.com/kunming-agent/kunming-agent/main/scripts/install.sh | bash

set -e

REPO_URL="https://github.com/kunming-agent/kunming-agent.git"
INSTALL_DIR="${HOME}/.local/share/kunming-agent"
VENV_DIR="${INSTALL_DIR}/venv"
BIN_DIR="${HOME}/.local/bin"
FORCE=false

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --force) FORCE=true; shift ;;
        --dir) INSTALL_DIR="$2"; shift 2 ;;
        *) log_error "Unknown option: $1"; exit 1 ;;
    esac
done

# Detect OS
detect_os() {
    case "$(uname -s)" in
        Linux*) echo "linux" ;;
        Darwin*) echo "macos" ;;
        *) echo "unknown" ;;
    esac
}

# Check dependencies
check_deps() {
    local missing=()
    
    if ! command -v python3 &> /dev/null; then
        missing+=("python3")
    fi
    
    if ! command -v git &> /dev/null; then
        missing+=("git")
    fi
    
    if ! command -v curl &> /dev/null; then
        missing+=("curl")
    fi
    
    if [ ${#missing[@]} -ne 0 ]; then
        log_error "Missing required tools: ${missing[*]}"
        log_info "Please install them and try again"
        exit 1
    fi
    
    # Check Python version
    local py_version=$(python3 --version 2>&1 | grep -oP '\d+\.\d+' | head -1)
    local major=$(echo "$py_version" | cut -d. -f1)
    local minor=$(echo "$py_version" | cut -d. -f2)
    
    if [ "$major" -lt 3 ] || ([ "$major" -eq 3 ] && [ "$minor" -lt 8 ]); then
        log_error "Python 3.8+ required, found $py_version"
        exit 1
    fi
    
    log_info "Found Python $py_version"
}

# Clone repository
clone_repo() {
    if [ -d "$INSTALL_DIR" ] && [ "$FORCE" = true ]; then
        log_warn "Removing existing installation..."
        rm -rf "$INSTALL_DIR"
    fi
    
    if [ -d "$INSTALL_DIR/.git" ]; then
        log_info "Updating existing repository..."
        cd "$INSTALL_DIR"
        git pull
    else
        log_info "Cloning Kunming Agent repository..."
        mkdir -p "$INSTALL_DIR"
        git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
    fi
}

# Setup virtual environment
setup_venv() {
    cd "$INSTALL_DIR"
    
    if [ -d "$VENV_DIR" ]; then
        log_warn "Removing old virtual environment..."
        rm -rf "$VENV_DIR"
    fi
    
    log_info "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    
    log_info "Installing dependencies..."
    source "${VENV_DIR}/bin/activate"
    pip install --upgrade pip
    pip install -e .
}

# Create wrapper script
create_wrapper() {
    log_info "Creating km wrapper..."
    
    mkdir -p "$BIN_DIR"
    
    cat > "${BIN_DIR}/km" << EOF
#!/bin/bash
source "${VENV_DIR}/bin/activate"
exec python -m kunming "\$@"
EOF
    
    chmod +x "${BIN_DIR}/km"
}

# Add to PATH
add_to_path() {
    if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
        local shell_rc=""
        case "$(basename "$SHELL")" in
            bash) shell_rc="$HOME/.bashrc" ;;
            zsh) shell_rc="$HOME/.zshrc" ;;
            fish) shell_rc="$HOME/.config/fish/config.fish" ;;
            *) shell_rc="$HOME/.profile" ;;
        esac
        
        log_info "Adding $BIN_DIR to PATH in $shell_rc"
        echo "export PATH=\"$BIN_DIR:\$PATH\"" >> "$shell_rc"
        log_warn "Please restart your shell or run: source $shell_rc"
    fi
}

# Setup config
setup_config() {
    local config_dir="$HOME/.kunming"
    local config_file="$config_dir/config.yaml"
    
    log_info "Setting up configuration..."
    mkdir -p "$config_dir"
    
    if [ ! -f "$config_file" ]; then
        cat > "$config_file" << 'EOF'
# Kunming Agent Configuration
default_model: anthropic/claude-3-5-sonnet-20241022
max_iterations: 50
enabled_toolsets:
  - core
disabled_toolsets: []
auto_approve: false
quiet_mode: false
save_trajectories: false
EOF
        log_success "Created default config at $config_file"
    fi
}

# Main
main() {
    echo "================================"
    echo "  Kunming Agent Installer"
    echo "================================"
    echo
    
    check_deps
    clone_repo
    setup_venv
    create_wrapper
    add_to_path
    setup_config
    
    echo
    log_success "Installation complete!"
    echo
    echo "Next steps:"
    echo "  1. Restart your terminal or run: source ~/.bashrc"
    echo "  2. Add API keys to ~/.kunming/.env"
    echo "  3. Run 'km' to start"
    echo
}

main "$@"
