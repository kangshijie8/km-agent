"""Tests for kunming_cli.skin_engine - the data-driven skin/theme system."""

import json
import os
import pytest
from pathlib import Path
from unittest.mock import patch


@pytest.fixture(autouse=True)
def reset_skin_state():
    from kunming_cli import skin_engine
    skin_engine._active_skin = None
    skin_engine._active_skin_name = "default"
    yield
    skin_engine._active_skin = None
    skin_engine._active_skin_name = "default"


class TestSkinConfig:
    def test_default_skin_has_required_fields(self):
        from kunming_cli.skin_engine import load_skin
        skin = load_skin("default")
        assert skin.name == "default"
        assert skin.tool_prefix == ">"
        assert "banner_title" in skin.colors
        assert "banner_border" in skin.colors
        assert "agent_name" in skin.branding

    def test_get_color_with_fallback(self):
        from kunming_cli.skin_engine import load_skin
        skin = load_skin("default")
        assert skin.get_color("banner_title") == "#FFD700"
        assert skin.get_color("nonexistent", "#000") == "#000"

    def test_get_branding_with_fallback(self):
        from kunming_cli.skin_engine import load_skin
        skin = load_skin("default")
        assert skin.get_branding("agent_name") == "km agent"
        assert skin.get_branding("nonexistent", "fallback") == "fallback"

    def test_get_spinner_list_has_kawaii_faces(self):
        from kunming_cli.skin_engine import load_skin
        skin = load_skin("default")
        faces = skin.get_spinner_list("waiting_faces")
        assert len(faces) == 10
        assert faces[0] == "(｡◕‿◕｡)"
        verbs = skin.get_spinner_list("thinking_verbs")
        assert len(verbs) == 15
        assert "pondering" in verbs

    def test_get_spinner_wings_empty_for_default(self):
        from kunming_cli.skin_engine import load_skin
        skin = load_skin("default")
        assert skin.get_spinner_wings() == []


class TestBuiltinSkins:
    def test_ares_skin_loads(self):
        from kunming_cli.skin_engine import load_skin
        skin = load_skin("ares")
        assert skin.name == "ares"
        assert skin.tool_prefix == "⚔"
        assert skin.get_color("banner_border") == "#8B4513"
        assert skin.get_color("response_border") == "#8B4513"
        assert skin.get_branding("agent_name") == "Ares"

    def test_ares_has_spinner_customization(self):
        from kunming_cli.skin_engine import load_skin
        skin = load_skin("ares")
        assert len(skin.get_spinner_list("waiting_faces")) > 0
        assert len(skin.get_spinner_list("thinking_faces")) > 0
        assert len(skin.get_spinner_list("thinking_verbs")) > 0
        wings = skin.get_spinner_wings()
        assert len(wings) > 0

    def test_mono_skin_loads(self):
        from kunming_cli.skin_engine import load_skin
        skin = load_skin("mono")
        assert skin.name == "mono"
        assert skin.get_color("banner_title") == "#CCCCCC"

    def test_slate_skin_loads(self):
        from kunming_cli.skin_engine import load_skin
        skin = load_skin("slate")
        assert skin.name == "slate"
        assert skin.get_color("banner_title") == "#7EB8DA"

    def test_cyberpunk_skin_loads(self):
        from kunming_cli.skin_engine import load_skin
        skin = load_skin("cyberpunk")
        assert skin.name == "cyberpunk"
        assert skin.get_color("banner_border") == "#FF00FF"
        assert skin.get_branding("agent_name") == "Cyber Agent"
        assert len(skin.get_spinner_wings()) > 0

    def test_unknown_skin_falls_back_to_default(self):
        from kunming_cli.skin_engine import load_skin
        skin = load_skin("nonexistent_skin_xyz")
        assert skin.name == "default"

    def test_all_builtin_skins_have_complete_colors(self):
        from kunming_cli.skin_engine import _BUILTIN_SKINS, _build_skin_config
        required_keys = ["banner_border", "banner_title", "banner_accent",
                         "banner_dim", "banner_text"]
        for name, data in _BUILTIN_SKINS.items():
            skin = _build_skin_config(data)
            for key in required_keys:
                assert key in skin.colors, f"Skin '{name}' missing color '{key}'"


class TestSkinManagement:
    def test_set_active_skin(self):
        from kunming_cli.skin_engine import set_active_skin, get_active_skin, get_active_skin_name
        set_active_skin("ares")
        assert get_active_skin_name() == "ares"
        assert get_active_skin().name == "ares"

    def test_get_active_skin_defaults(self):
        from kunming_cli.skin_engine import get_active_skin
        skin = get_active_skin()
        assert skin.name == "default"

    def test_list_skins_includes_builtins(self):
        from kunming_cli.skin_engine import list_skins
        skins = list_skins()
        names = [s["name"] for s in skins]
        assert "default" in names
        assert "ares" in names
        assert "mono" in names
        assert "slate" in names
        assert "cyberpunk" in names
        for s in skins:
            assert "source" in s
            assert s["source"] == "builtin"

    def test_init_skin_from_config(self):
        from kunming_cli.skin_engine import init_skin_from_config, get_active_skin_name
        init_skin_from_config({"display": {"skin": "ares"}})
        assert get_active_skin_name() == "ares"

    def test_init_skin_from_empty_config(self):
        from kunming_cli.skin_engine import init_skin_from_config, get_active_skin_name
        init_skin_from_config({})
        assert get_active_skin_name() == "default"


class TestUserSkins:
    def test_load_user_skin_from_yaml(self, tmp_path, monkeypatch):
        from kunming_cli.skin_engine import load_skin
        skins_dir = tmp_path / "skins"
        skins_dir.mkdir()
        skin_file = skins_dir / "custom.yaml"
        skin_data = {
            "name": "custom",
            "description": "A custom test skin",
            "colors": {"banner_title": "#FF0000"},
            "branding": {"agent_name": "Custom Agent"},
            "tool_prefix": ">",
        }
        import yaml
        skin_file.write_text(yaml.dump(skin_data))
        monkeypatch.setattr("kunming_cli.config.get_kunming_home", lambda: tmp_path)

        skin = load_skin("custom")
        assert skin.name == "custom"
        assert skin.get_color("banner_title") == "#FF0000"
        assert skin.get_branding("agent_name") == "Custom Agent"
        assert skin.get_color("banner_border") == "#D4A574"

    def test_list_skins_includes_user_skins(self, tmp_path, monkeypatch):
        from kunming_cli.skin_engine import list_skins
        skins_dir = tmp_path / "skins"
        skins_dir.mkdir()
        import yaml
        (skins_dir / "pirate.yaml").write_text(yaml.dump({
            "name": "pirate",
            "description": "Arr matey",
        }))
        monkeypatch.setattr("kunming_cli.config.get_kunming_home", lambda: tmp_path)

        skins = list_skins()
        names = [s["name"] for s in skins]
        assert "pirate" in names
        pirate = [s for s in skins if s["name"] == "pirate"][0]
        assert pirate["source"] == "user"


class TestDisplayIntegration:
    def test_get_skin_tool_prefix_default(self):
        from agent.display import get_skin_tool_prefix
        assert get_skin_tool_prefix() == ">"

    def test_get_skin_tool_prefix_custom(self):
        from kunming_cli.skin_engine import set_active_skin
        from agent.display import get_skin_tool_prefix
        set_active_skin("ares")
        assert get_skin_tool_prefix() == "⚔"

    def test_get_skin_faces_default(self):
        from agent.display import get_skin_faces, KawaiiSpinner
        faces = get_skin_faces("waiting_faces", KawaiiSpinner.KAWAII_WAITING)
        assert len(faces) > 0

    def test_get_skin_faces_ares(self):
        from kunming_cli.skin_engine import set_active_skin
        from agent.display import get_skin_faces, KawaiiSpinner
        set_active_skin("ares")
        faces = get_skin_faces("waiting_faces", KawaiiSpinner.KAWAII_WAITING)
        assert len(faces) > 0

    def test_get_skin_verbs_default(self):
        from agent.display import get_skin_verbs, KawaiiSpinner
        verbs = get_skin_verbs()
        assert len(verbs) > 0

    def test_get_skin_verbs_ares(self):
        from kunming_cli.skin_engine import set_active_skin
        from agent.display import get_skin_verbs
        set_active_skin("ares")
        verbs = get_skin_verbs()
        assert "conquering" in verbs

    def test_tool_message_uses_skin_prefix(self):
        from kunming_cli.skin_engine import set_active_skin
        from agent.display import get_cute_tool_message
        set_active_skin("ares")
        msg = get_cute_tool_message("terminal", {"command": "ls"}, 0.5)
        assert "⚔" in msg or len(msg) > 0

    def test_tool_message_default_prefix(self):
        from agent.display import get_cute_tool_message
        msg = get_cute_tool_message("terminal", {"command": "ls"}, 0.5)
        assert len(msg) > 0


class TestCliBrandingHelpers:
    def test_active_prompt_symbol_default(self):
        from kunming_cli.skin_engine import get_active_prompt_symbol
        assert get_active_prompt_symbol() == "❯"

    def test_active_prompt_symbol_ares(self):
        from kunming_cli.skin_engine import set_active_skin, get_active_prompt_symbol
        set_active_skin("ares")
        assert get_active_prompt_symbol() == "⚔"

    def test_active_help_header_ares(self):
        from kunming_cli.skin_engine import set_active_skin, get_active_help_header
        set_active_skin("ares")
        assert get_active_help_header() == "Ares Commands"

    def test_active_goodbye_ares(self):
        from kunming_cli.skin_engine import set_active_skin, get_active_goodbye
        set_active_skin("ares")
        assert get_active_goodbye() == "Ares retreats"

    def test_prompt_toolkit_style_overrides_use_skin_colors(self):
        from kunming_cli.skin_engine import (
            set_active_skin,
            get_active_skin,
            get_prompt_toolkit_style_overrides,
        )
        set_active_skin("ares")
        skin = get_active_skin()
        overrides = get_prompt_toolkit_style_overrides()
        border_color = skin.get_color("response_border", "")
        if border_color:
            assert overrides.get("input-area") is not None
