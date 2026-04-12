# Kunming Agent Windows Installation Script
# Run with: powershell -ExecutionPolicy Bypass -File install.ps1

param(
    [switch]$Force,
    [string]$InstallDir = "$env:LOCALAPPDATA\KunmingAgent"
)

$ErrorActionPreference = "Stop"

# Colors for output
function Write-Info { param($Message) Write-Host "[INFO] $Message" -ForegroundColor Cyan }
function Write-Success { param($Message) Write-Host "[SUCCESS] $Message" -ForegroundColor Green }
function Write-Warn { param($Message) Write-Host "[WARN] $Message" -ForegroundColor Yellow }
function Write-Error { param($Message) Write-Host "[ERROR] $Message" -ForegroundColor Red }

# Check if running as administrator
function Test-Admin {
    $currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    return $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# Check Python installation
function Test-Python {
    try {
        $pythonVersion = python --version 2>&1
        if ($pythonVersion -match "Python (\d+)\.(\d+)") {
            $major = [int]$matches[1]
            $minor = [int]$matches[2]
            if ($major -gt 3 -or ($major -eq 3 -and $minor -ge 8)) {
                Write-Info "Found Python $major.$minor"
                return $true
            }
        }
        Write-Error "Python 3.8 or higher is required. Found: $pythonVersion"
        return $false
    } catch {
        Write-Error "Python is not installed or not in PATH"
        return $false
    }
}

# Check Git installation
function Test-Git {
    try {
        $gitVersion = git --version 2>&1
        Write-Info "Found $gitVersion"
        return $true
    } catch {
        Write-Error "Git is not installed or not in PATH"
        Write-Info "Please install Git from: https://git-scm.com/download/win"
        return $false
    }
}

# Clone or update repository
function Clone-Repository {
    param([string]$TargetDir)
    
    $repoUrl = "https://github.com/kunming-agent/kunming-agent.git"
    
    if (Test-Path $TargetDir) {
        if ($Force) {
            Write-Warn "Removing existing installation at $TargetDir"
            Remove-Item -Recurse -Force $TargetDir
        } else {
            Write-Info "Updating existing installation..."
            Set-Location $TargetDir
            git pull
            return
        }
    }
    
    Write-Info "Cloning Kunming Agent repository..."
    git clone $repoUrl $TargetDir
}

# Setup Python virtual environment
function Setup-Venv {
    param([string]$ProjectDir)
    
    $venvDir = Join-Path $ProjectDir "venv"
    
    if (Test-Path $venvDir) {
        Write-Warn "Virtual environment already exists. Recreating..."
        Remove-Item -Recurse -Force $venvDir
    }
    
    Write-Info "Creating virtual environment..."
    python -m venv $venvDir
    
    Write-Info "Activating virtual environment..."
    $activateScript = Join-Path $venvDir "Scripts\Activate.ps1"
    . $activateScript
    
    Write-Info "Upgrading pip..."
    python -m pip install --upgrade pip
    
    Write-Info "Installing Kunming Agent..."
    Set-Location $ProjectDir
    pip install -e .
}

# Create km command wrapper
function Create-Wrapper {
    param(
        [string]$ProjectDir,
        [string]$BinDir = "$env:LOCALAPPDATA\Microsoft\WindowsApps"
    )
    
    $wrapperPath = Join-Path $BinDir "km.cmd"
    $venvPython = Join-Path $ProjectDir "venv\Scripts\python.exe"
    
    Write-Info "Creating km command wrapper..."
    
    $wrapperContent = @"
@echo off
"$venvPython" -m kunming %*
"@
    
    Set-Content -Path $wrapperPath -Value $wrapperContent
    Write-Success "Created km command at $wrapperPath"
}

# Setup configuration directory
function Setup-Config {
    $configDir = "$env:USERPROFILE\.kunming"
    $configFile = Join-Path $configDir "config.yaml"
    
    Write-Info "Setting up configuration directory..."
    
    if (-not (Test-Path $configDir)) {
        New-Item -ItemType Directory -Path $configDir -Force | Out-Null
    }
    
    if (-not (Test-Path $configFile)) {
        $defaultConfig = @"
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
"@
        Set-Content -Path $configFile -Value $defaultConfig
        Write-Success "Created default configuration at $configFile"
    }
}

# Add to PATH if needed
function Add-ToPath {
    param([string]$BinDir)
    
    $currentPath = [Environment]::GetEnvironmentVariable("PATH", "User")
    
    if ($currentPath -notlike "*$BinDir*") {
        Write-Info "Adding $BinDir to user PATH..."
        $newPath = "$currentPath;$BinDir"
        [Environment]::SetEnvironmentVariable("PATH", $newPath, "User")
        Write-Warn "Please restart your terminal for PATH changes to take effect"
    }
}

# Main installation function
function Install-KunmingAgent {
    Write-Info "Starting Kunming Agent installation..."
    Write-Info "Install directory: $InstallDir"
    
    # Pre-flight checks
    if (-not (Test-Python)) { exit 1 }
    if (-not (Test-Git)) { exit 1 }
    
    # Create installation directory
    if (-not (Test-Path $InstallDir)) {
        New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    }
    
    # Clone and setup
    Clone-Repository -TargetDir $InstallDir
    Setup-Venv -ProjectDir $InstallDir
    
    # Create wrapper and config
    $binDir = "$env:LOCALAPPDATA\Microsoft\WindowsApps"
    Create-Wrapper -ProjectDir $InstallDir -BinDir $binDir
    Setup-Config
    Add-ToPath -BinDir $binDir
    
    Write-Success "Kunming Agent installed successfully!"
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Yellow
    Write-Host "  1. Restart your terminal"
    Write-Host "  2. Add your API keys to %USERPROFILE%\.kunming\.env"
    Write-Host "  3. Run 'km' to start using Kunming Agent"
    Write-Host ""
    Write-Host "For help, run: km --help"
}

# Run installation
Install-KunmingAgent
