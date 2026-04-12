#!/bin/bash
set -e

# Kunming Agent Setup Script
# Usage: curl -sSL https://raw.githubusercontent.com/kunming-agent/kunming-agent/main/setup-kunming.sh | bash

REPO_URL="https://github.com/kunming-agent/kunming-agent.git"
INSTALL_DIR="${HOME}/.local/share/kunming-agent"
VENV_DIR="${INSTALL_DIR}/venv"
BIN_DIR="${HOME}/.local/bin"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Detect OS
detect_os() {
    case "$(uname -s)" in
        Linux*)     echo "linux";;
        Darwin*)    echo "macos";;
        CYGWIN*|MINGW*|MSYS*) echo "windows";;
        *)          echo "unknown";;
    esac
}

# Install dependencies for Linux
install_linux_deps() {
    log_info "Installing Linux dependencies..."
    
    if command_exists apt-get; then
        sudo apt-get update
        sudo apt-get install -y python3 python3-pip python3-venv git curl
    elif command_exists yum; then
        sudo yum install -y python3 python3-pip git curl
    elif command_exists dnf; then
        sudo dnf install -y python3 python3-pip git curl
    elif command_exists pacman; then
        sudo pacman -Sy python python-pip git curl
    else
        log_warn "Unknown package manager. Please install Python 3.8+, pip, git, and curl manually."
    fi
}

# Install dependencies for macOS
install_macos_deps() {
    log_info "Installing macOS dependencies..."
    
    if ! command_exists brew; then
        log_info "Installing Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi
    
    brew install python git curl
}

# Install dependencies
install_dependencies() {
    local os=$(detect_os)
    
    case $os in
        linux)
            install_linux_deps
            ;;
        macos)
            install_macos_deps
            ;;
        windows)
            log_warn "Windows detected. Please ensure Python 3.8+, git, and curl are installed."
            ;;
        *)
            log_warn "Unknown OS. Please ensure Python 3.8+, pip, git, and curl are installed."
            ;;
    esac
}

# Clone repository
clone_repo() {
    log_info "Cloning Kunming Agent repository..."
    
    if [ -d "$INSTALL_DIR" ]; then
        log_warn "Installation directory already exists. Updating..."
        cd "$INSTALL_DIR"
        git pull
    else
        mkdir -p "$INSTALL_DIR"
        git clone "$REPO_URL" "$INSTALL_DIR"
        cd "$INSTALL_DIR"
    fi
}

# Create virtual environment
setup_venv() {
    log_info "Setting up Python virtual environment..."
    
    if [ -d "$VENV_DIR" ]; then
        log_warn "Virtual environment already exists. Removing old environment..."
        rm -rf "$VENV_DIR"
    fi
    
    python3 -m venv "$VENV_DIR"
    source "${VENV_DIR}/bin/activate"
    
    log_info "Upgrading pip..."
    pip install --upgrade pip
    
    log_info "Installing Kunming Agent..."
    pip install -e .
}

# Create wrapper script
create_wrapper() {
    log_info "Creating km wrapper script..."
    
    mkdir -p "$BIN_DIR"
    
    cat > "${BIN_DIR}/km" << 'EOF'
#!/bin/bash
source "${HOME}/.local/share/kunming-agent/venv/bin/activate"
exec python -m kunming "$@"
EOF
    
    chmod +x "${BIN_DIR}/km"
}

# Add to PATH
add_to_path() {
    local shell_rc=""
    local current_shell="$(basename "$SHELL")"
    
    case "$current_shell" in
        bash)
            shell_rc="${HOME}/.bashrc"
            ;;
        zsh)
            shell_rc="${HOME}/.zshrc"
            ;;
        fish)
            shell_rc="${HOME}/.config/fish/config.fish"
            ;;
        *)
            shell_rc="${HOME}/.profile"
            ;;
    esac
    
    if [[ ":$PATH:" != *":${BIN_DIR}:"* ]]; then
        log_info "Adding ${BIN_DIR} to PATH in ${shell_rc}..."
        echo "export PATH=\"${BIN_DIR}:\$PATH\"" >> "$shell_rc"
        log_warn "Please restart your shell or run: source ${shell_rc}"
    fi
}

# Create config directory
setup_config() {
    log_info "Setting up configuration directory..."
    
    mkdir -p "${HOME}/.kunming"
    
    if [ ! -f "${HOME}/.kunming/config.yaml" ]; then
        cat > "${HOME}/.kunming/config.yaml" << 'EOF'
# Kunming Agent Configuration
# See documentation for all available options

default_model: anthropic/claude-3-5-sonnet-20241022
max_iterations: 50
enabled_toolsets:
  - core
disabled_toolsets: []
auto_approve: false
quiet_mode: false
save_trajectories: false
EOF
        log_success "Created default configuration at ${HOME}/.kunming/config.yaml"
    fi
}

# Main installation
main() {
    echo "=================================="
    echo "  Kunming Agent Setup"
    echo "=================================="
    echo ""
    
    # Check Python version
    if command_exists python3; then
        PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
        log_info "Found Python ${PYTHON_VERSION}"
    else
        log_error "Python 3 is not installed. Please install Python 3.8 or higher."
        exit 1
    fi
    
    # Install dependencies
    install_dependencies
    
    # Clone and setup
    clone_repo
    setup_venv
    create_wrapper
    add_to_path
    setup_config
    
    echo ""
    echo "=================================="
    log_success "Kunming Agent installed successfully!"
    echo "=================================="
    echo ""
    echo "Next steps:"
    echo "  1. Restart your shell or run: source ~/.bashrc (or ~/.zshrc)"
    echo "  2. Add your API keys to ~/.kunming/.env"
    echo "  3. Run 'km' to start using Kunming Agent"
    echo ""
    echo "For help, run: km --help"
    echo "Documentation: https://github.com/kunming-agent/kunming-agent"
}

# Run main function
main "$@"
