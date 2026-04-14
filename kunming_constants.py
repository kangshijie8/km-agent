"""Shared constants for Kunming Agent.

Import-safe module with no dependencies — can be imported from anywhere
without risk of circular imports.
"""

import os
from pathlib import Path


def get_kunming_home() -> Path:
    """Return the Kunming home directory (default: ~/.kunming).

    Reads KUNMING_HOME env var, falls back to ~/.kunming.
    This is the single source of truth — all other copies should import this.
    """
    return Path(os.getenv("KUNMING_HOME", Path.home() / ".kunming"))


def _get_default_kunming_home() -> Path:
    """Return the default (pre-profile) KUNMING_HOME path.

    Always ``~/.kunming`` — anchored to the user's home,
    NOT to the current KUNMING_HOME (which may itself be a profile).
    """
    return Path.home() / ".kunming"


def get_optional_skills_dir(default: Path | None = None) -> Path:
    """Return the optional-skills directory, honoring package-manager wrappers.

    Packaged installs may ship ``optional-skills`` outside the Python package
    tree and expose it via ``KUNMING_OPTIONAL_SKILLS``.
    """
    override = os.getenv("KUNMING_OPTIONAL_SKILLS", "").strip()
    if override:
        return Path(override)
    if default is not None:
        return default
    return get_kunming_home() / "optional-skills"


def get_kunming_dir(new_subpath: str, old_name: str) -> Path:
    """Resolve a Kunming subdirectory with backward compatibility.

    New installs get the consolidated layout (e.g. ``cache/images``).
    Existing installs that already have the old path (e.g. ``image_cache``)
    keep using it — no migration required.

    Args:
        new_subpath: Preferred path relative to KUNMING_HOME (e.g. ``"cache/images"``).
        old_name: Legacy path relative to KUNMING_HOME (e.g. ``"image_cache"``).

    Returns:
        Absolute ``Path`` — old location if it exists on disk, otherwise the new one.
    """
    home = get_kunming_home()
    old_path = home / old_name
    if old_path.exists():
        return old_path
    return home / new_subpath


def display_kunming_home() -> str:
    """Return a user-friendly display string for the current KUNMING_HOME.

    Uses ``~/`` shorthand for readability::

        default:  ``~/.kunming``
        profile:  ``~/.kunming/profiles/coder``
        custom:   ``/opt/kunming-custom``

    Use this in **user-facing** print/log messages instead of hardcoding
    ``~/.kunming``.  For code that needs a real ``Path``, use
    :func:`get_kunming_home` instead.
    """
    home = get_kunming_home()
    try:
        return "~/" + str(home.relative_to(Path.home()))
    except ValueError:
        return str(home)


VALID_REASONING_EFFORTS = ("xhigh", "high", "medium", "low", "minimal")


def parse_reasoning_effort(effort: str) -> dict | None:
    """Parse a reasoning effort level into a config dict.

    Valid levels: "xhigh", "high", "medium", "low", "minimal", "none".
    Returns None when the input is empty or unrecognized (caller uses default).
    Returns {"enabled": False} for "none".
    Returns {"enabled": True, "effort": <level>} for valid effort levels.
    """
    if not effort or not effort.strip():
        return None
    effort = effort.strip().lower()
    if effort == "none":
        return {"enabled": False}
    if effort in VALID_REASONING_EFFORTS:
        return {"enabled": True, "effort": effort}
    return None


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODELS_URL = f"{OPENROUTER_BASE_URL}/models"
OPENROUTER_CHAT_URL = f"{OPENROUTER_BASE_URL}/chat/completions"

AI_GATEWAY_BASE_URL = "https://ai-gateway.vercel.sh/v1"
AI_GATEWAY_MODELS_URL = f"{AI_GATEWAY_BASE_URL}/models"
AI_GATEWAY_CHAT_URL = f"{AI_GATEWAY_BASE_URL}/chat/completions"

NOUS_API_BASE_URL = "https://inference-api.kunming.dev/v1"
NOUS_API_CHAT_URL = f"{NOUS_API_BASE_URL}/chat/completions"
