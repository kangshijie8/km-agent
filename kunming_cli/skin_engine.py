#!/usr/bin/env python3
"""
Skin/Theme Engine for Kunming CLI

Provides data-driven visual customization for the CLI.
Skins are pure data - no code changes needed to add new skins.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Tuple, Optional
from pathlib import Path
import yaml
import logging

logger = logging.getLogger(__name__)

# Default skin configuration
DEFAULT_SKIN = {
    "name": "default",
    "description": "Classic km gold/kawaii theme",
    "colors": {
        "banner_border": "#D4A574",
        "banner_title": "#FFD700",
        "banner_accent": "#FFA500",
        "banner_dim": "#888888",
        "banner_text": "#FFFFFF",
        "response_border": "#D4A574",
    },
    "spinner": {
        "waiting_faces": ["(o_o)", "(O_o)", "(o_O)", "(-_-)", "(o.o)"],
        "thinking_faces": ["(o_o)", "(O_o)", "(o_O)", "(-_-)", "(o.o)"],
        "thinking_verbs": ["thinking", "processing", "analyzing"],
    },
    "branding": {
        "agent_name": "km agent",
        "welcome": "km agent ready",
        "goodbye": "km agent signing off",
        "response_label": " km ",
        "prompt_symbol": "❯",
        "help_header": "km commands",
    },
    "tool_prefix": ">",
    "tool_emojis": {},
    "banner_logo": "",
    "banner_hero": "",
}


@dataclass
class SkinConfig:
    """Configuration for a single skin/theme."""
    name: str
    description: str = ""
    colors: Dict[str, str] = field(default_factory=dict)
    spinner: Dict[str, Any] = field(default_factory=dict)
    branding: Dict[str, str] = field(default_factory=dict)
    tool_prefix: str = ">"
    tool_emojis: Dict[str, str] = field(default_factory=dict)
    banner_logo: str = ""
    banner_hero: str = ""

    def get_color(self, key: str, fallback: str = "") -> str:
        """Get a color value with fallback."""
        return self.colors.get(key, fallback)

    def get_spinner_list(self, key: str) -> List[str]:
        """Get a spinner list (faces, verbs, etc.)."""
        return self.spinner.get(key, [])

    def get_spinner_wings(self) -> List[Tuple[str, str]]:
        """Get spinner wing pairs, or empty list if none."""
        return self.spinner.get("wings", [])

    def get_tool_emoji(self, tool_name: str, fallback: str = "") -> str:
        """Get emoji for a specific tool, or fallback."""
        return self.tool_emojis.get(tool_name, fallback)

    def get_branding(self, key: str, fallback: str = "") -> str:
        """Get a branding value with fallback."""
        return self.branding.get(key, fallback)


# Global active skin cache
_active_skin: Optional[SkinConfig] = None
_active_skin_name: str = "default"

_BUILTIN_SKINS: Dict[str, dict] = {
    "default": DEFAULT_SKIN,
}

_skins_dir: Optional[Path] = None


def _deep_merge(base, override):
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _build_skin_config(data: dict) -> SkinConfig:
    """Build a SkinConfig from a dictionary. Alias for _load_skin_from_dict."""
    return _load_skin_from_dict(data)


def _load_skin_from_dict(data: dict) -> SkinConfig:
    """Load a SkinConfig from a dictionary."""
    return SkinConfig(
        name=data.get("name", "unnamed"),
        description=data.get("description", ""),
        colors=data.get("colors", {}),
        spinner=data.get("spinner", {}),
        branding=data.get("branding", {}),
        tool_prefix=data.get("tool_prefix", ">"),
        tool_emojis=data.get("tool_emojis", {}),
        banner_logo=data.get("banner_logo", ""),
        banner_hero=data.get("banner_hero", ""),
    )


def load_skin(name: str) -> SkinConfig:
    """Load a skin by name. Falls back to default if not found."""
    global _active_skin

    if name == "default":
        _active_skin = _load_skin_from_dict(DEFAULT_SKIN)
        return _active_skin

    # Try to load from user skins directory
    from kunming_cli.config import get_kunming_home
    skin_path = get_kunming_home() / "skins" / f"{name}.yaml"

    if skin_path.exists():
        try:
            with open(skin_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            if data:
                # Merge with default for missing values
                merged = _deep_merge(DEFAULT_SKIN, data)
                _active_skin = _load_skin_from_dict(merged)
                return _active_skin
        except Exception as e:
            logger.warning(f"Failed to load skin {name}: {e}")

    # Fall back to default
    _active_skin = _load_skin_from_dict(DEFAULT_SKIN)
    return _active_skin


def get_active_skin() -> SkinConfig:
    """Get the currently active skin."""
    global _active_skin
    if _active_skin is None:
        _active_skin = _load_skin_from_dict(DEFAULT_SKIN)
    return _active_skin


def get_active_skin_name() -> str:
    """Get the name of the currently active skin."""
    return _active_skin_name


def set_active_skin(name: str) -> None:
    """Set the active skin by name."""
    global _active_skin_name
    _active_skin_name = name
    load_skin(name)


def init_skin_from_config(config: dict) -> None:
    """Initialize skin from config dictionary."""
    skin_name = config.get("display", {}).get("skin", "default")
    load_skin(skin_name)


def list_available_skins() -> List[str]:
    """List all available skin names."""
    skins = ["default"]

    try:
        from kunming_cli.config import get_kunming_home
        skins_dir = get_kunming_home() / "skins"
        if skins_dir.exists():
            for f in skins_dir.iterdir():
                if f.suffix == ".yaml":
                    skins.append(f.stem)
    except Exception:
        pass

    return skins


def list_skins() -> List[dict]:
    """List all available skins with metadata."""
    result = []
    for name in list_available_skins():
        if name == "default":
            result.append({"name": "default", "source": "builtin"})
        else:
            result.append({"name": name, "source": "user"})
    return result


# Convenience functions for common skin values

def get_active_color(key: str, fallback: str = "") -> str:
    """Get a color from the active skin."""
    return get_active_skin().get_color(key, fallback)


def get_active_spinner_faces(key: str = "waiting_faces") -> List[str]:
    """Get spinner faces from the active skin."""
    return get_active_skin().get_spinner_list(key)


def get_active_spinner_verbs() -> List[str]:
    """Get spinner verbs from the active skin."""
    return get_active_skin().get_spinner_list("thinking_verbs")


def get_active_spinner_wings() -> List[Tuple[str, str]]:
    """Get spinner wings from the active skin."""
    return get_active_skin().get_spinner_wings()


def get_active_tool_prefix() -> str:
    """Get the tool output prefix from the active skin."""
    return get_active_skin().tool_prefix


def get_active_tool_emoji(tool_name: str, fallback: str = "") -> str:
    """Get emoji for a tool from the active skin."""
    return get_active_skin().get_tool_emoji(tool_name, fallback)


def get_active_agent_name(fallback: str = "Kunming Agent") -> str:
    """Get the agent name from the active skin."""
    return get_active_skin().branding.get("agent_name", fallback)


def get_active_welcome_message(fallback: str = "Welcome!") -> str:
    """Get the welcome message from the active skin."""
    return get_active_skin().branding.get("welcome", fallback)


def get_active_goodbye(fallback: str = "Goodbye!") -> str:
    """Get the goodbye message from the active skin."""
    return get_active_skin().branding.get("goodbye", fallback)


def get_active_response_label(fallback: str = " Kunming ") -> str:
    """Get the response box label from the active skin."""
    return get_active_skin().branding.get("response_label", fallback)


def get_active_prompt_symbol(fallback: str = ">") -> str:
    """Get the prompt symbol from the active skin."""
    return get_active_skin().branding.get("prompt_symbol", fallback)


def get_active_help_header(fallback: str = "Available Commands") -> str:
    """Get the help header from the active skin."""
    return get_active_skin().branding.get("help_header", fallback)


def get_active_banner_logo() -> str:
    """Get the banner logo from the active skin."""
    return get_active_skin().banner_logo


def get_active_banner_hero() -> str:
    """Get the banner hero art from the active skin."""
    return get_active_skin().banner_hero


def get_prompt_toolkit_style_overrides() -> dict:
    """Get prompt_toolkit style overrides from the active skin."""
    skin = get_active_skin()
    overrides = {}
    border_color = skin.get_color("response_border", "")
    if border_color:
        overrides["input-area"] = f"fg:{border_color}"
        overrides["placeholder"] = f"fg:{border_color}"
    prompt_symbol = skin.branding.get("prompt_symbol", "")
    if prompt_symbol:
        overrides["prompt"] = f"fg:{border_color}" if border_color else ""
    return overrides
