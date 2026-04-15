"""Tests for get_tool_emoji function with SkinConfig integration."""

import pytest
from unittest.mock import MagicMock, patch as mock_patch


class TestGetToolEmoji:
    """Verify get_tool_emoji uses SkinConfig.tool_emojis correctly."""

    def test_no_skin_uses_registry_emoji(self):
        """When no skin is configured, use registry emoji."""
        from agent.display import get_tool_emoji
        mock_reg = MagicMock()
        mock_reg.get_emoji.return_value = "🔍"
        import sys
        mock_module = MagicMock()
        mock_module.registry = mock_reg
        with mock_patch("agent.display._get_skin", return_value=None), \
             mock_patch.dict(sys.modules, {"tools.registry": mock_module}):
            result = get_tool_emoji("web_search")
            assert result == "🔍"

    def test_skin_without_tool_emojis_uses_registry(self):
        """When skin has no tool_emojis, fall back to registry."""
        from agent.display import get_tool_emoji
        skin = MagicMock()
        skin.tool_emojis = {}
        mock_reg = MagicMock()
        mock_reg.get_emoji.return_value = "🔍"
        import sys
        mock_module = MagicMock()
        mock_module.registry = mock_reg
        with mock_patch("agent.display._get_skin", return_value=skin), \
             mock_patch.dict(sys.modules, {"tools.registry": mock_module}):
            result = get_tool_emoji("web_search")
            assert result == "🔍"

    def test_skin_override_for_matching_tool(self):
        """When skin has emoji for tool, use skin's emoji."""
        from agent.display import get_tool_emoji
        skin = MagicMock()
        skin.tool_emojis = {"terminal": "🖥️"}
        with mock_patch("agent.display._get_skin", return_value=skin):
            result = get_tool_emoji("terminal")
            assert result == "🖥️"

    def test_skin_override_only_for_matching_tool(self):
        """Skin override for one tool doesn't affect others."""
        from agent.display import get_tool_emoji
        skin = MagicMock()
        skin.tool_emojis = {"terminal": "🖥️"}
        mock_reg = MagicMock()
        mock_reg.get_emoji.return_value = "🔍"
        import sys
        mock_module = MagicMock()
        mock_module.registry = mock_reg
        with mock_patch("agent.display._get_skin", return_value=skin), \
             mock_patch.dict(sys.modules, {"tools.registry": mock_module}):
            assert get_tool_emoji("terminal") == "🖥️"  # skin override
            assert get_tool_emoji("web_search") == "🔍"  # registry fallback


class TestSkinConfigToolEmojis:
    """Verify SkinConfig handles tool_emojis field correctly."""

    def test_skin_config_has_tool_emojis_field(self):
        """SkinConfig has tool_emojis field defaulting to empty dict."""
        from kunming_cli.skin_engine import SkinConfig
        skin = SkinConfig(name="test")
        assert skin.tool_emojis == {}

    def test_skin_config_accepts_tool_emojis(self):
        """SkinConfig accepts tool_emojis parameter."""
        from kunming_cli.skin_engine import SkinConfig
        emojis = {"terminal": "🖥️", "web_search": "crystal_ball"}
        skin = SkinConfig(name="test", tool_emojis=emojis)
        assert skin.tool_emojis == emojis

    def test_build_skin_config_includes_tool_emojis(self):
        """_build_skin_config includes tool_emojis in built config."""
        from kunming_cli.skin_engine import _build_skin_config
        data = {
            "name": "custom",
            "tool_emojis": {"terminal": "dagger", "patch": "hammer"},
        }
        skin = _build_skin_config(data)
        assert skin.tool_emojis == {"terminal": "dagger", "patch": "hammer"}

    def test_build_skin_config_empty_tool_emojis_default(self):
        """_build_skin_config defaults to empty dict when tool_emojis not provided."""
        from kunming_cli.skin_engine import _build_skin_config
        data = {"name": "minimal"}
        skin = _build_skin_config(data)
        assert skin.tool_emojis == {}


class TestSkinYamlToolEmojis:
    """Verify tool_emojis can be loaded from YAML skin files."""

    def test_load_skin_with_tool_emojis(self, tmp_path):
        """Skin YAML with tool_emojis loads correctly."""
        from kunming_cli.skin_engine import load_skin
        import yaml
        
        skin_dir = tmp_path / "skins"
        skin_dir.mkdir()
        skin_file = skin_dir / "test.yaml"
        skin_data = {
            "name": "test",
            "tool_emojis": {"terminal": "🖥️", "web_search": "🔍"}
        }
        skin_file.write_text(yaml.dump(skin_data))
        
        # 修复: get_kunming_home已迁移到kunming_constants导入 [M17]
        with mock_patch("kunming_constants.get_kunming_home", return_value=tmp_path):
            skin = load_skin("test")
            assert skin.tool_emojis == {"terminal": "🖥️", "web_search": "🔍"}


class TestSkinEmojiEdgeCases:
    """Edge cases for skin emoji handling."""

    def test_empty_tool_name_falls_back_to_registry(self):
        """Empty tool name should fall back to registry."""
        from agent.display import get_tool_emoji
        skin = MagicMock()
        skin.tool_emojis = {"": "🖥️"}
        mock_reg = MagicMock()
        mock_reg.get_emoji.return_value = "🔧"
        import sys
        mock_module = MagicMock()
        mock_module.registry = mock_reg
        with mock_patch("agent.display._get_skin", return_value=skin), \
             mock_patch.dict(sys.modules, {"tools.registry": mock_module}):
            result = get_tool_emoji("")
            assert result == "🔧"

    def test_none_skin_falls_back_to_registry(self):
        """None skin should fall back to registry."""
        from agent.display import get_tool_emoji
        mock_reg = MagicMock()
        mock_reg.get_emoji.return_value = "🔧"
        import sys
        mock_module = MagicMock()
        mock_module.registry = mock_reg
        with mock_patch("agent.display._get_skin", return_value=None), \
             mock_patch.dict(sys.modules, {"tools.registry": mock_module}):
            result = get_tool_emoji("any_tool")
            assert result == "🔧"
