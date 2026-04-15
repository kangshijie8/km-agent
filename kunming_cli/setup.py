"""
Interactive setup wizard for Kunming Agent.

Modular wizard with independently-runnable sections:
  1. Model & Provider -choose your AI provider and model
  2. Terminal Backend -where your agent runs commands
  3. Agent Settings -iterations, compression, session reset
  4. Messaging Platforms -connect Telegram, Discord, etc.
  5. Tools -configure TTS, web search, image generation, etc.

Config files are stored in ~/.kunming/ for easy access.
"""

import importlib.util
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Optional, Dict, Any

from kunming_cli.nous_subscription import (
    apply_nous_provider_defaults,
    get_nous_subscription_features,
)
from tools.tool_backend_helpers import managed_nous_tools_enabled
from kunming_constants import get_optional_skills_dir

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.resolve()

_DOCS_BASE = "https://kunming-agent.kunming.dev/docs"


def _model_config_dict(config: Dict[str, Any]) -> Dict[str, Any]:
    current_model = config.get("model")
    if isinstance(current_model, dict):
        return dict(current_model)
    if isinstance(current_model, str) and current_model.strip():
        return {"default": current_model.strip()}
    return {}


def _set_default_model(config: Dict[str, Any], model_name: str) -> None:
    if not model_name:
        return
    model_cfg = _model_config_dict(config)
    model_cfg["default"] = model_name
    config["model"] = model_cfg


def _get_credential_pool_strategies(config: Dict[str, Any]) -> Dict[str, str]:
    strategies = config.get("credential_pool_strategies")
    return dict(strategies) if isinstance(strategies, dict) else {}


def _set_credential_pool_strategy(config: Dict[str, Any], provider: str, strategy: str) -> None:
    if not provider:
        return
    strategies = _get_credential_pool_strategies(config)
    strategies[provider] = strategy
    config["credential_pool_strategies"] = strategies


def _supports_same_provider_pool_setup(provider: str) -> bool:
    if not provider or provider == "custom":
        return False
    if provider == "openrouter":
        return True
    from kunming_cli.auth import PROVIDER_REGISTRY

    pconfig = PROVIDER_REGISTRY.get(provider)
    if not pconfig:
        return False
    return pconfig.auth_type in {"api_key", "oauth_device_code"}


# Default model lists per provider -used as fallback when the live
# /models endpoint can't be reached.
_DEFAULT_PROVIDER_MODELS = {
    "copilot-acp": [
        "copilot-acp",
    ],
    "copilot": [
        "gpt-5.4",
        "gpt-5.4-mini",
        "gpt-5-mini",
        "gpt-5.3-codex",
        "gpt-5.2-codex",
        "gpt-4.1",
        "gpt-4o",
        "gpt-4o-mini",
        "claude-opus-4.6",
        "claude-sonnet-4.6",
        "claude-sonnet-4.5",
        "claude-haiku-4.5",
        "gemini-2.5-pro",
        "grok-code-fast-1",
    ],
    "gemini": [
        "gemini-3.1-pro-preview", "gemini-3-flash-preview", "gemini-3.1-flash-lite-preview",
        "gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite",
        "gemma-4-31b-it", "gemma-4-26b-it",
    ],
    "zai": ["glm-5", "glm-4.7", "glm-4.5", "glm-4.5-flash"],
    "kimi-coding": ["kimi-k2.5", "kimi-k2-thinking", "kimi-k2-turbo-preview"],
    "minimax": ["MiniMax-M1", "MiniMax-M1-40k", "MiniMax-M1-80k", "MiniMax-M1-128k", "MiniMax-M1-256k", "MiniMax-M2.5", "MiniMax-M2.7"],
    "minimax-cn": ["MiniMax-M1", "MiniMax-M1-40k", "MiniMax-M1-80k", "MiniMax-M1-128k", "MiniMax-M1-256k", "MiniMax-M2.5", "MiniMax-M2.7"],
    "ai-gateway": ["anthropic/claude-opus-4.6", "anthropic/claude-sonnet-4.6", "openai/gpt-5", "google/gemini-3-flash"],
    "kilocode": ["anthropic/claude-opus-4.6", "anthropic/claude-sonnet-4.6", "openai/gpt-5.4", "google/gemini-3-pro-preview", "google/gemini-3-flash-preview"],
    "opencode-zen": ["gpt-5.4", "gpt-5.3-codex", "claude-sonnet-4-6", "gemini-3-flash", "glm-5", "kimi-k2.5", "minimax-m2.7"],
    "opencode-go": ["glm-5", "kimi-k2.5", "mimo-v2-pro", "mimo-v2-omni", "minimax-m2.5", "minimax-m2.7"],
    "huggingface": [
        "Qwen/Qwen3.5-397B-A17B", "Qwen/Qwen3-235B-A22B-Thinking-2507",
        "Qwen/Qwen3-Coder-480B-A35B-Instruct", "deepseek-ai/DeepSeek-R1-0528",
        "deepseek-ai/DeepSeek-V3.2", "moonshotai/Kimi-K2.5",
    ],
}


def _current_reasoning_effort(config: Dict[str, Any]) -> str:
    agent_cfg = config.get("agent")
    if isinstance(agent_cfg, dict):
        return str(agent_cfg.get("reasoning_effort") or "").strip().lower()
    return ""


def _set_reasoning_effort(config: Dict[str, Any], effort: str) -> None:
    agent_cfg = config.get("agent")
    if not isinstance(agent_cfg, dict):
        agent_cfg = {}
        config["agent"] = agent_cfg
    agent_cfg["reasoning_effort"] = effort


def _setup_copilot_reasoning_selection(
    config: Dict[str, Any],
    model_id: str,
    prompt_choice,
    *,
    catalog: Optional[list[dict[str, Any]]] = None,
    api_key: str = "",
) -> None:
    from kunming_cli.models import github_model_reasoning_efforts, normalize_copilot_model_id

    normalized_model = normalize_copilot_model_id(
        model_id,
        catalog=catalog,
        api_key=api_key,
    ) or model_id
    efforts = github_model_reasoning_efforts(normalized_model, catalog=catalog, api_key=api_key)
    if not efforts:
        return

    current_effort = _current_reasoning_effort(config)
    choices = list(efforts) + ["禁用推理", f"保持当前设置 ({current_effort or 'default'})"]

    if current_effort == "none":
        default_idx = len(efforts)
    elif current_effort in efforts:
        default_idx = efforts.index(current_effort)
    elif "medium" in efforts:
        default_idx = efforts.index("medium")
    else:
        default_idx = len(choices) - 1

    effort_idx = prompt_choice("选择推理强度：", choices, default_idx)
    if effort_idx < len(efforts):
        _set_reasoning_effort(config, efforts[effort_idx])
    elif effort_idx == len(efforts):
        _set_reasoning_effort(config, "none")


def _setup_provider_model_selection(config, provider_id, current_model, prompt_choice, prompt_fn):
    """Model selection for API-key providers with live /models detection.

    Tries the provider's /models endpoint first.  Falls back to a
    hardcoded default list with a warning if the endpoint is unreachable.
    Always offers a 'Custom model' escape hatch.
    """
    from kunming_cli.auth import PROVIDER_REGISTRY, resolve_api_key_provider_credentials
    from kunming_cli.config import get_env_value
    from kunming_cli.models import (
        copilot_model_api_mode,
        fetch_api_models,
        fetch_github_model_catalog,
        normalize_copilot_model_id,
        normalize_opencode_model_id,
        opencode_model_api_mode,
    )

    pconfig = PROVIDER_REGISTRY[provider_id]
    is_copilot_catalog_provider = provider_id in {"copilot", "copilot-acp"}

    # Resolve API key and base URL for the probe
    if is_copilot_catalog_provider:
        api_key = ""
        if provider_id == "copilot":
            creds = resolve_api_key_provider_credentials(provider_id)
            api_key = creds.get("api_key", "")
            base_url = creds.get("base_url", "") or pconfig.inference_base_url
        else:
            try:
                creds = resolve_api_key_provider_credentials("copilot")
                api_key = creds.get("api_key", "")
            except Exception:
                pass
            base_url = pconfig.inference_base_url
        catalog = fetch_github_model_catalog(api_key)
        current_model = normalize_copilot_model_id(
            current_model,
            catalog=catalog,
            api_key=api_key,
        ) or current_model
    else:
        api_key = ""
        for ev in pconfig.api_key_env_vars:
            api_key = get_env_value(ev) or os.getenv(ev, "")
            if api_key:
                break
        base_url_env = pconfig.base_url_env_var or ""
        base_url = (get_env_value(base_url_env) if base_url_env else "") or pconfig.inference_base_url
        catalog = None

    # Try live /models endpoint
    if is_copilot_catalog_provider and catalog:
        live_models = [item.get("id", "") for item in catalog if item.get("id")]
    else:
        live_models = fetch_api_models(api_key, base_url)

    if live_models:
        provider_models = live_models
        print_info(f"从 {pconfig.name} API 发现 {len(live_models)} 个模型")
    else:
        fallback_provider_id = "copilot" if provider_id == "copilot-acp" else provider_id
        provider_models = _DEFAULT_PROVIDER_MODELS.get(fallback_provider_id, [])
        if provider_models:
            print_warning(
                f"无法从 {pconfig.name} API 自动检测模型 -显示默认列表。\n"
                f"    如果所需模型未列出，请选择\"自定义模型\"。"
            )

    if provider_id in {"opencode-zen", "opencode-go"}:
        provider_models = [normalize_opencode_model_id(provider_id, mid) for mid in provider_models]
        current_model = normalize_opencode_model_id(provider_id, current_model)
        provider_models = list(dict.fromkeys(mid for mid in provider_models if mid))

    model_choices = list(provider_models)
    model_choices.append("自定义模型")
    model_choices.append(f"保持当前设置 ({current_model})")

    keep_idx = len(model_choices) - 1
    model_idx = prompt_choice("选择默认模型：", model_choices, keep_idx)

    selected_model = current_model

    if model_idx < len(provider_models):
        selected_model = provider_models[model_idx]
        if is_copilot_catalog_provider:
            selected_model = normalize_copilot_model_id(
                selected_model,
                catalog=catalog,
                api_key=api_key,
            ) or selected_model
        elif provider_id in {"opencode-zen", "opencode-go"}:
            selected_model = normalize_opencode_model_id(provider_id, selected_model)
        _set_default_model(config, selected_model)
    elif model_idx == len(provider_models):
        custom = prompt_fn("输入模型名称")
        if custom:
            if is_copilot_catalog_provider:
                selected_model = normalize_copilot_model_id(
                    custom,
                    catalog=catalog,
                    api_key=api_key,
                ) or custom
            elif provider_id in {"opencode-zen", "opencode-go"}:
                selected_model = normalize_opencode_model_id(provider_id, custom)
            else:
                selected_model = custom
            _set_default_model(config, selected_model)
    else:
        # "Keep current" selected -validate it's compatible with the new
        # provider.  OpenRouter-formatted names (containing "/") won't work
        # on direct-API providers and would silently break the gateway.
        if "/" in (current_model or "") and provider_models:
            print_warning(
                f"当前模型 \"{current_model}\" 看起来像是 OpenRouter 模型，"
                f"无法在 {pconfig.name} 上使用。"
                f"正在切换到 {provider_models[0]}。"
            )
            selected_model = provider_models[0]
            _set_default_model(config, provider_models[0])

    if provider_id == "copilot" and selected_model:
        model_cfg = _model_config_dict(config)
        model_cfg["api_mode"] = copilot_model_api_mode(
            selected_model,
            catalog=catalog,
            api_key=api_key,
        )
        config["model"] = model_cfg
        _setup_copilot_reasoning_selection(
            config,
            selected_model,
            prompt_choice,
            catalog=catalog,
            api_key=api_key,
        )
    elif provider_id in {"opencode-zen", "opencode-go"} and selected_model:
        model_cfg = _model_config_dict(config)
        model_cfg["api_mode"] = opencode_model_api_mode(provider_id, selected_model)
        config["model"] = model_cfg


# Import config helpers
from kunming_cli.config import (
    get_kunming_home,
    get_config_path,
    get_env_path,
    load_config,
    save_config,
    save_env_value,
    get_env_value,
    ensure_kunming_home,
)
# display_kunming_home imported lazily at call sites (stale-module safety during km update)

from kunming_cli.colors import Colors, color


def print_header(title: str):
    """Print a section header."""
    print()
    print(color(f"o{title}", Colors.CYAN, Colors.BOLD))


def print_info(text: str):
    """Print info text."""
    print(color(f"  {text}", Colors.DIM))


def print_success(text: str):
    """Print success message."""
    print(color(f"[OK]{text}", Colors.GREEN))


def print_warning(text: str):
    """Print warning message."""
    print(color(f"[!]{text}", Colors.YELLOW))


def print_error(text: str):
    """Print error message."""
    print(color(f"[FAIL]{text}", Colors.RED))


def is_interactive_stdin() -> bool:
    """Return True when stdin looks like a usable interactive TTY."""
    stdin = getattr(sys, "stdin", None)
    if stdin is None:
        return False
    try:
        return bool(stdin.isatty())
    except Exception:
        return False


def print_noninteractive_setup_guidance(reason: str | None = None) -> None:
    """Print guidance for headless/non-interactive setup flows."""
    print()
    print(color("[ON]km setup - 非交互模式", Colors.CYAN, Colors.BOLD))
    print()
    if reason:
        print_info(reason)
    print_info("交互式向导无法在此环境中使用。")
    print()
    print_info("请使用环境变量或配置命令来配置 Kunming：")
    print_info("  km config set model.provider custom")
    print_info("  km config set model.base_url http://localhost:8080/v1")
    print_info("  km config set model.default your-model-name")
    print()
    print_info("或在环境中设置 OPENROUTER_API_KEY / OPENAI_API_KEY。")
    print_info("在交互式终端中运行 'km setup' 以使用完整向导。")
    print()


def prompt(question: str, default: str = None, password: bool = False) -> str:
    """Prompt for input with optional default."""
    if default:
        display = f"{question} [{default}]: "
    else:
        display = f"{question}: "

    try:
        if password:
            import getpass

            value = getpass.getpass(color(display, Colors.YELLOW))
        else:
            value = input(color(display, Colors.YELLOW))

        return value.strip() or default or ""
    except (KeyboardInterrupt, EOFError):
        print()
        sys.exit(1)


def _curses_prompt_choice(question: str, choices: list, default: int = 0) -> int:
    """Single-select menu using curses to avoid simple_term_menu rendering bugs."""
    try:
        import curses
        result_holder = [default]

        def _curses_menu(stdscr):
            curses.curs_set(0)
            if curses.has_colors():
                curses.start_color()
                curses.use_default_colors()
                curses.init_pair(1, curses.COLOR_GREEN, -1)
                curses.init_pair(2, curses.COLOR_YELLOW, -1)
            cursor = default
            scroll_offset = 0

            while True:
                stdscr.clear()
                max_y, max_x = stdscr.getmaxyx()

                # Rows available for list items: rows 2..(max_y-2) inclusive.
                visible = max(1, max_y - 3)

                # Scroll the viewport so the cursor is always visible.
                if cursor < scroll_offset:
                    scroll_offset = cursor
                elif cursor >= scroll_offset + visible:
                    scroll_offset = cursor - visible + 1
                scroll_offset = max(0, min(scroll_offset, max(0, len(choices) - visible)))

                try:
                    stdscr.addnstr(
                        0,
                        0,
                        question,
                        max_x - 1,
                        curses.A_BOLD | (curses.color_pair(2) if curses.has_colors() else 0),
                    )
                except curses.error:
                    pass

                for row, i in enumerate(range(scroll_offset, min(scroll_offset + visible, len(choices)))):
                    y = row + 2
                    if y >= max_y - 1:
                        break
                    arrow = ">" if i == cursor else " "
                    line = f" {arrow}  {choices[i]}"
                    attr = curses.A_NORMAL
                    if i == cursor:
                        attr = curses.A_BOLD
                        if curses.has_colors():
                            attr |= curses.color_pair(1)
                    try:
                        stdscr.addnstr(y, 0, line, max_x - 1, attr)
                    except curses.error:
                        pass

                stdscr.refresh()
                key = stdscr.getch()
                if key in (curses.KEY_UP, ord("k")):
                    cursor = (cursor - 1) % len(choices)
                elif key in (curses.KEY_DOWN, ord("j")):
                    cursor = (cursor + 1) % len(choices)
                elif key in (curses.KEY_ENTER, 10, 13):
                    result_holder[0] = cursor
                    return
                elif key in (27, ord("q")):
                    return

        curses.wrapper(_curses_menu)
        return result_holder[0]
    except Exception:
        return -1



def prompt_choice(question: str, choices: list, default: int = 0) -> int:
    """Prompt for a choice from a list with arrow key navigation.

    Escape keeps the current default (skips the question).
    Ctrl+C exits the wizard.
    """
    idx = _curses_prompt_choice(question, choices, default)
    if idx >= 0:
        if idx == default:
            print_info("  已跳过（保持当前设置）")
            print()
            return default
        print()
        return idx

    print(color(question, Colors.YELLOW))
    for i, choice in enumerate(choices):
        marker = "o" if i == default else "x"
        if i == default:
            print(color(f"  {marker} {choice}", Colors.GREEN))
        else:
            print(f"  {marker} {choice}")

    print_info(f"  回车使用默认值 ({default + 1})  Ctrl+C 退出")

    while True:
        try:
            value = input(
                color(f"  选择 [1-{len(choices)}] ({default + 1}): ", Colors.DIM)
            )
            if not value:
                return default
            idx = int(value) - 1
            if 0 <= idx < len(choices):
                return idx
            print_error(f"请输入 1 到 {len(choices)} 之间的数字")
        except ValueError:
            print_error("请输入数字")
        except (KeyboardInterrupt, EOFError):
            print()
            sys.exit(1)


def prompt_yes_no(question: str, default: bool = True) -> bool:
    """Prompt for yes/no. Ctrl+C exits, empty input returns default."""
    default_str = "Y/n" if default else "y/N"

    while True:
        try:
            value = (
                input(color(f"{question} [{default_str}]: ", Colors.YELLOW))
                .strip()
                .lower()
            )
        except (KeyboardInterrupt, EOFError):
            print()
            sys.exit(1)

        if not value:
            return default
        if value in ("y", "yes"):
            return True
        if value in ("n", "no"):
            return False
        print_error("请输入 'y' 或 'n'")


def prompt_checklist(title: str, items: list, pre_selected: list = None) -> list:
    """
    Display a multi-select checklist and return the indices of selected items.

    Each item in `items` is a display string. `pre_selected` is a list of
    indices that should be checked by default. A "Continue -> option is
    appended at the end -the user toggles items with Space and confirms
    with Enter on "Continue ->.

    Falls back to a numbered toggle interface when simple_term_menu is
    unavailable.

    Returns:
        List of selected indices (not including the Continue option).
    """
    if pre_selected is None:
        pre_selected = []

    from kunming_cli.curses_ui import curses_checklist

    chosen = curses_checklist(
        title,
        items,
        set(pre_selected),
        cancel_returns=set(pre_selected),
    )
    return sorted(chosen)


def _prompt_api_key(var: dict):
    """Display a nicely formatted API key input screen for a single env var."""
    tools = var.get("tools", [])
    tools_str = ", ".join(tools[:3])
    if len(tools) > 3:
        tools_str += f" 等 {len(tools) - 3} 项"

    print()
    print(color(f"  --- {var.get('description', var['name'])} ---", Colors.CYAN))
    print()
    if tools_str:
        print_info(f"  启用工具: {tools_str}")
    if var.get("url"):
        print_info(f"  获取密钥: {var['url']}")
    print()

    if var.get("password"):
        value = prompt(f"  {var.get('prompt', var['name'])}", password=True)
    else:
        value = prompt(f"  {var.get('prompt', var['name'])}")

    if value:
        save_env_value(var["name"], value)
        print_success("  [OK] 已保存")
    else:
        print_warning("  已跳过（稍后可通过 'km setup' 配置）")


def _print_setup_summary(config: dict, kunming_home):
    """Print the setup completion summary."""
    # Tool availability summary
    print()
    print_header("工具可用性摘要")

    tool_status = []
    subscription_features = get_nous_subscription_features(config)

    # Vision -use the same runtime resolver as the actual vision tools
    try:
        from agent.auxiliary_client import get_available_vision_backends

        _vision_backends = get_available_vision_backends()
    except Exception:
        _vision_backends = []

    if _vision_backends:
        tool_status.append(("视觉（图像分析）", True, None))
    else:
        tool_status.append(("视觉（图像分析）", False, "运行 'km setup' 进行配置"))

    # Mixture of Agents -requires OpenRouter specifically (calls multiple models)
    if get_env_value("OPENROUTER_API_KEY"):
        tool_status.append(("多模型混合", True, None))
    else:
        tool_status.append(("多模型混合", False, "OPENROUTER_API_KEY"))

    # Web tools (Exa, Parallel, Firecrawl, or Tavily)
    if subscription_features.web.managed_by_nous:
        tool_status.append(("网页搜索与提取（Nous 订阅）", True, None))
    elif subscription_features.web.available:
        label = "网页搜索与提取"
        if subscription_features.web.current_provider:
            label = f"网页搜索与提取（{subscription_features.web.current_provider}）"
        tool_status.append((label, True, None))
    else:
        tool_status.append(("网页搜索与提取", False, "EXA_API_KEY, PARALLEL_API_KEY, FIRECRAWL_API_KEY/FIRECRAWL_API_URL 或 TAVILY_API_KEY"))

    # Browser tools (local Chromium, Camofox, Browserbase, Browser Use, or Firecrawl)
    browser_provider = subscription_features.browser.current_provider
    if subscription_features.browser.managed_by_nous:
        tool_status.append(("浏览器自动化（Nous Browser Use）", True, None))
    elif subscription_features.browser.available:
        label = "浏览器自动化"
        if browser_provider:
            label = f"浏览器自动化（{browser_provider}）"
        tool_status.append((label, True, None))
    else:
        missing_browser_hint = "npm install -g agent-browser，设置 CAMOFOX_URL，或配置 Browser Use 或 Browserbase"
        if browser_provider == "Browserbase":
            missing_browser_hint = (
                "npm install -g agent-browser 并设置 "
                "BROWSERBASE_API_KEY/BROWSERBASE_PROJECT_ID"
            )
        elif browser_provider == "Browser Use":
            missing_browser_hint = (
                "npm install -g agent-browser 并设置 BROWSER_USE_API_KEY"
            )
        elif browser_provider == "Camofox":
            missing_browser_hint = "CAMOFOX_URL"
        elif browser_provider == "Local browser":
            missing_browser_hint = "npm install -g agent-browser"
        tool_status.append(
            ("浏览器自动化", False, missing_browser_hint)
        )

    # FAL (image generation)
    if subscription_features.image_gen.managed_by_nous:
        tool_status.append(("图像生成（Nous 订阅）", True, None))
    elif subscription_features.image_gen.available:
        tool_status.append(("图像生成", True, None))
    else:
        tool_status.append(("图像生成", False, "FAL_KEY"))

    # TTS -show configured provider
    tts_provider = config.get("tts", {}).get("provider", "edge")
    if subscription_features.tts.managed_by_nous:
        tool_status.append(("文字转语音（OpenAI via Nous 订阅）", True, None))
    elif tts_provider == "elevenlabs" and get_env_value("ELEVENLABS_API_KEY"):
        tool_status.append(("文字转语音（ElevenLabs）", True, None))
    elif tts_provider == "openai" and (
        get_env_value("VOICE_TOOLS_OPENAI_KEY") or get_env_value("OPENAI_API_KEY")
    ):
        tool_status.append(("文字转语音（OpenAI）", True, None))
    elif tts_provider == "minimax" and get_env_value("MINIMAX_API_KEY"):
        tool_status.append(("文字转语音（MiniMax）", True, None))
    elif tts_provider == "neutts":
        try:
            import importlib.util
            neutts_ok = importlib.util.find_spec("neutts") is not None
        except Exception:
            neutts_ok = False
        if neutts_ok:
            tool_status.append(("文字转语音（NeuTTS 本地）", True, None))
        else:
            tool_status.append(("文字转语音（NeuTTS — 未安装）", False, "运行 'km setup tts'"))
    else:
        tool_status.append(("文字转语音（Edge TTS）", True, None))

    if subscription_features.modal.managed_by_nous:
        tool_status.append(("Modal 执行（Nous 订阅）", True, None))
    elif config.get("terminal", {}).get("backend") == "modal":
        if subscription_features.modal.direct_override:
            tool_status.append(("Modal 执行（直接 Modal）", True, None))
        else:
            tool_status.append(("Modal 执行", False, "运行 'km setup terminal'"))
    elif managed_nous_tools_enabled() and subscription_features.nous_auth_present:
        tool_status.append(("Modal 执行（可选，via Nous 订阅）", True, None))

    # Tinker + WandB (RL training)
    if get_env_value("TINKER_API_KEY") and get_env_value("WANDB_API_KEY"):
        tool_status.append(("RL 训练（Tinker）", True, None))
    elif get_env_value("TINKER_API_KEY"):
        tool_status.append(("RL 训练（Tinker）", False, "WANDB_API_KEY"))
    else:
        tool_status.append(("RL 训练（Tinker）", False, "TINKER_API_KEY"))

    # Home Assistant
    if get_env_value("HASS_TOKEN"):
        tool_status.append(("智能家居（Home Assistant）", True, None))

    # Skills Hub
    if get_env_value("GITHUB_TOKEN"):
        tool_status.append(("技能中心（GitHub）", True, None))
    else:
        tool_status.append(("技能中心（GitHub）", False, "GITHUB_TOKEN"))

    # Terminal (always available if system deps met)
    tool_status.append(("终端/命令执行", True, None))

    # Task planning (always available, in-memory)
    tool_status.append(("任务规划（待办）", True, None))

    # Skills (always available -- bundled skills + user-created skills)
    tool_status.append(("技能（查看、创建、编辑）", True, None))

    # Print status
    available_count = sum(1 for _, avail, _ in tool_status if avail)
    total_count = len(tool_status)

    print_info(f"{available_count}/{total_count} 个工具类别可用：")
    print()

    for name, available, missing_var in tool_status:
        if available:
            print(f"   {color('[OK]', Colors.GREEN)} {name}")
        else:
            print(
                f"   {color('[X]', Colors.RED)} {name} {color(f'(缺少 {missing_var})', Colors.DIM)}"
            )

    print()

    disabled_tools = [(name, var) for name, avail, var in tool_status if not avail]
    if disabled_tools:
        print_warning(
            "部分工具未启用。运行 'km setup tools' 进行配置，"
        )
        from kunming_constants import display_kunming_home as _dhh
        print_warning(f"或直接编辑 {_dhh()}/.env 添加缺少的 API 密钥。")
        print()

    # Done banner
    print()
    print(
        color(
            "+---------------------------------------------------------+",
            Colors.GREEN,
        )
    )
    print(
        color(
            "|             [OK] 设置完成！                              |",
            Colors.GREEN,
        )
    )
    print(
        color(
            "+---------------------------------------------------------+",
            Colors.GREEN,
        )
    )
    print()

    # Show file locations prominently
    from kunming_constants import display_kunming_home as _dhh
    print(color(f"[FILES] 所有文件位于 {_dhh()}/:", Colors.CYAN, Colors.BOLD))
    print()
    print(f"   {color('设置文件:', Colors.YELLOW)}  {get_config_path()}")
    print(f"   {color('API 密钥:', Colors.YELLOW)}  {get_env_path()}")
    print(
        f"   {color('数据:', Colors.YELLOW)}      {kunming_home}/cron/, sessions/, logs/"
    )
    print()

    print(color("-" * 60, Colors.DIM))
    print()
    print(color("ð To edit your configuration:", Colors.CYAN, Colors.BOLD))
    print()
    print(f"   {color('km setup', Colors.GREEN)}          重新运行完整向导")
    print(f"   {color('km setup model', Colors.GREEN)}    更改模型/提供商")
    print(f"   {color('km setup terminal', Colors.GREEN)} 更改终端后端")
    print(f"   {color('km setup gateway', Colors.GREEN)}  配置消息平台")
    print(f"   {color('km setup tools', Colors.GREEN)}    配置工具提供商")
    print()
    print(f"   {color('km config', Colors.GREEN)}         查看当前设置")
    print(
        f"   {color('km config edit', Colors.GREEN)}    在编辑器中打开配置"
    )
    print(f"   {color('km config set <key> <value>', Colors.GREEN)}")
    print("                          设置特定值")
    print()
    print("   或直接编辑文件：")
    print(f"   {color(f'nano {get_config_path()}', Colors.DIM)}")
    print(f"   {color(f'nano {get_env_path()}', Colors.DIM)}")
    print()

    print(color("-" * 60, Colors.DIM))
    print()
    print(color("ð Ready to go!", Colors.CYAN, Colors.BOLD))
    print()
    print(f"   {color('km', Colors.GREEN)}              开始对话")
    print(f"   {color('km gateway', Colors.GREEN)}      启动消息网关")
    print(f"   {color('km doctor', Colors.GREEN)}       检查问题")
    print()


def _prompt_container_resources(config: dict):
    """Prompt for container resource settings (Docker, Singularity, Modal, Daytona)."""
    terminal = config.setdefault("terminal", {})

    print()
    print_info("容器资源配置：")

    # Persistence
    current_persist = terminal.get("container_persistent", True)
    persist_label = "yes" if current_persist else "no"
    print_info("  持久化文件系统可在会话间保留文件。")
    print_info("  设为 'no' 则使用每次重置的临时沙箱。")
    persist_str = prompt(
        "  是否持久化文件系统？(yes/no)", persist_label
    )
    terminal["container_persistent"] = persist_str.lower() in ("yes", "true", "y", "1")

    # CPU
    current_cpu = terminal.get("container_cpu", 1)
    cpu_str = prompt("  CPU 核心数", str(current_cpu))
    try:
        terminal["container_cpu"] = float(cpu_str)
    except ValueError:
        pass

    # Memory
    current_mem = terminal.get("container_memory", 5120)
    mem_str = prompt("  内存（MB，5120 = 5GB）", str(current_mem))
    try:
        terminal["container_memory"] = int(mem_str)
    except ValueError:
        pass

    # Disk
    current_disk = terminal.get("container_disk", 51200)
    disk_str = prompt("  磁盘（MB，51200 = 50GB）", str(current_disk))
    try:
        terminal["container_disk"] = int(disk_str)
    except ValueError:
        pass


# Tool categories and provider config are now in tools_config.py (shared
# between `km tools` and `km setup tools`).


# =============================================================================
# Section 1: Model & Provider Configuration
# =============================================================================



def setup_model_provider(config: dict, *, quick: bool = False):
    """Configure the inference provider and default model.

    Delegates to ``cmd_model()`` (the same flow used by ``km model``)
    for provider selection, credential prompting, and model picking.
    This ensures a single code path for all provider setup -any new
    provider added to ``km model`` is automatically available here.

    When *quick* is True, skips credential rotation, vision, and TTS
    configuration -used by the streamlined first-time quick setup.
    """
    from kunming_cli.config import load_config, save_config

    print_header("推理提供商")
    print_info("选择如何连接到您的主聊天模型。")
    print_info(f"   指南: {_DOCS_BASE}/integrations/providers")
    print()

    # Delegate to the shared km model flow -handles provider picker,
    # credential prompting, model selection, and config persistence.
    from kunming_cli.main import select_provider_and_model
    try:
        select_provider_and_model()
    except (SystemExit, KeyboardInterrupt):
        print()
        print_info("提供商设置已跳过。")
    except Exception as exc:
        logger.debug("select_provider_and_model error during setup: %s", exc)
        print_warning(f"提供商设置遇到错误: {exc}")
        print_info("稍后可以重试: km model")

    # Re-sync the wizard's config dict from what cmd_model saved to disk.
    # This is critical: cmd_model writes to disk via its own load/save cycle,
    # and the wizard's final save_config(config) must not overwrite those
    # changes with stale values (#4172).
    _refreshed = load_config()
    config["model"] = _refreshed.get("model", config.get("model"))
    if _refreshed.get("custom_providers"):
        config["custom_providers"] = _refreshed["custom_providers"]

    # Derive the selected provider for downstream steps (vision setup).
    selected_provider = None
    _m = config.get("model")
    if isinstance(_m, dict):
        selected_provider = _m.get("provider")

    nous_subscription_selected = selected_provider == "nous"

    # -- Same-provider fallback & rotation setup (full setup only) --
    if not quick and _supports_same_provider_pool_setup(selected_provider):
        try:
            from types import SimpleNamespace
            from agent.credential_pool import load_pool
            from kunming_cli.auth_commands import auth_add_command

            pool = load_pool(selected_provider)
            entries = pool.entries()
            entry_count = len(entries)
            manual_count = sum(1 for entry in entries if str(getattr(entry, "source", "")).startswith("manual"))
            auto_count = entry_count - manual_count
            print()
            print_header("同提供商凭据轮换")
            print_info(
                "Kunming 可以为同一提供商保存多个凭据，并在"
            )
            print_info(
                "凭据耗尽或被限流时自动切换。这样可以保持"
            )
            print_info(
                "主提供商不变，同时减少配额问题导致的中断。"
            )
            print()
            if auto_count > 0:
                print_info(
                    f"{selected_provider} 当前凭据池: {entry_count} 个 "
                    f"({manual_count} 个手动, {auto_count} 个从环境变量/共享认证自动检测)"
                )
            else:
                print_info(f"{selected_provider} 当前凭据池: {entry_count} 个")

            while prompt_yes_no("是否添加同提供商的备用凭据？", False):
                auth_add_command(
                    SimpleNamespace(
                        provider=selected_provider,
                        auth_type="",
                        label=None,
                        api_key=None,
                        portal_url=None,
                        inference_url=None,
                        client_id=None,
                        scope=None,
                        no_browser=False,
                        timeout=15.0,
                        insecure=False,
                        ca_bundle=None,
                        min_key_ttl_seconds=5 * 60,
                    )
                )
                pool = load_pool(selected_provider)
                entry_count = len(pool.entries())
                print_info(f"提供商凭据池现有 {entry_count} 个凭据。")

            if entry_count > 1:
                strategy_labels = [
                    "优先填充/粘性 -持续使用第一个健康凭据直到耗尽",
                    "轮询 -每次选择后切换到下一个健康凭据",
                    "随机 -每次随机选择一个健康凭据",
                ]
                current_strategy = _get_credential_pool_strategies(config).get(selected_provider, "fill_first")
                default_strategy_idx = {
                    "fill_first": 0,
                    "round_robin": 1,
                    "random": 2,
                }.get(current_strategy, 0)
                strategy_idx = prompt_choice(
                    "选择同提供商轮换策略：",
                    strategy_labels,
                    default_strategy_idx,
                )
                strategy_value = ["fill_first", "round_robin", "random"][strategy_idx]
                _set_credential_pool_strategy(config, selected_provider, strategy_value)
                print_success(f"已保存 {selected_provider} 轮换策略: {strategy_value}")
            else:
                _set_credential_pool_strategy(config, selected_provider, "fill_first")
        except Exception as exc:
            logger.debug("Could not configure same-provider fallback in setup: %s", exc)

    # -- Vision & Image Analysis Setup (full setup only) --
    if quick:
        _vision_needs_setup = False
    else:
        try:
            from agent.auxiliary_client import get_available_vision_backends
            _vision_backends = set(get_available_vision_backends())
        except Exception:
            _vision_backends = set()

        _vision_needs_setup = not bool(_vision_backends)

        if selected_provider in _vision_backends:
            _vision_needs_setup = False

    if _vision_needs_setup:
        _prov_names = {
            "nous-api": "Nous Portal API key",
            "copilot": "GitHub Copilot",
            "copilot-acp": "GitHub Copilot ACP",
            "zai": "Z.AI / GLM",
            "kimi-coding": "Kimi / Moonshot",
            "minimax": "MiniMax",
            "minimax-cn": "MiniMax CN",
            "anthropic": "Anthropic",
            "ai-gateway": "AI Gateway",
            "custom": "your custom endpoint",
        }
        _prov_display = _prov_names.get(selected_provider, selected_provider or "your provider")

        print()
        print_header("视觉与图像分析（可选）")
        print_info(f"视觉功能使用独立的多模态后端。{_prov_display}")
        print_info("目前无法为 Kunming 自动提供视觉后端，")
        print_info("请现在选择一个后端或跳过稍后配置。")
        print()

        _vision_choices = [
            "OpenRouter -使用 Gemini（openrouter.ai/keys 有免费额度）",
            "OpenAI 兼容端点 -自定义 Base URL、API 密钥和视觉模型",
            "暂时跳过",
        ]
        _vision_idx = prompt_choice("配置视觉功能：", _vision_choices, 2)

        if _vision_idx == 0:  # OpenRouter
            _or_key = prompt("  OpenRouter API 密钥", password=True).strip()
            if _or_key:
                save_env_value("OPENROUTER_API_KEY", _or_key)
                print_success("OpenRouter 密钥已保存 -视觉将使用 Gemini")
            else:
                print_info("已跳过 -视觉功能不可用")
        elif _vision_idx == 1:  # OpenAI-compatible endpoint
            _base_url = prompt("  Base URL (blank for OpenAI)").strip() or "https://api.openai.com/v1"
            _api_key_label = "  API 密钥"
            if "api.openai.com" in _base_url.lower():
                _api_key_label = "  OpenAI API 密钥"
            _oai_key = prompt(_api_key_label, password=True).strip()
            if _oai_key:
                save_env_value("OPENAI_API_KEY", _oai_key)
                # Save vision base URL to config (not .env -only secrets go there)
                _vaux = config.setdefault("auxiliary", {}).setdefault("vision", {})
                _vaux["base_url"] = _base_url
                if "api.openai.com" in _base_url.lower():
                    _oai_vision_models = ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano"]
                    _vm_choices = _oai_vision_models + ["使用默认 (gpt-4o-mini)"]
                    _vm_idx = prompt_choice("选择视觉模型：", _vm_choices, 0)
                    _selected_vision_model = (
                        _oai_vision_models[_vm_idx]
                        if _vm_idx < len(_oai_vision_models)
                        else "gpt-4o-mini"
                    )
                else:
                    _selected_vision_model = prompt("  视觉模型（留空使用主模型/自定义默认值）").strip()
                save_env_value("AUXILIARY_VISION_MODEL", _selected_vision_model)
                print_success(
                    f"视觉已配置 {_base_url}"
                    + (f" ({_selected_vision_model})" if _selected_vision_model else "")
                )
            else:
                print_info("已跳过 -视觉功能不可用")
        else:
            print_info("已跳过 -稍后可通过 'km setup' 添加或配置 AUXILIARY_VISION_* 设置")


    if selected_provider == "nous" and nous_subscription_selected:
        changed_defaults = apply_nous_provider_defaults(config)
        current_tts = str(config.get("tts", {}).get("provider") or "edge")
        if "tts" in changed_defaults:
            print_success("TTS 提供商已设为: OpenAI TTS（通过您的 Nous 订阅）")
        else:
            print_info(f"保持现有 TTS 提供商: {current_tts}")

    save_config(config)

    if not quick and selected_provider != "nous":
        _setup_tts_provider(config)


# =============================================================================
# Section 1b: TTS Provider Configuration
# =============================================================================


def _check_espeak_ng() -> bool:
    """Check if espeak-ng is installed."""
    import shutil
    return shutil.which("espeak-ng") is not None or shutil.which("espeak") is not None


def _install_neutts_deps() -> bool:
    """Install NeuTTS dependencies with user approval. Returns True on success."""
    import subprocess
    import sys

    # Check espeak-ng
    if not _check_espeak_ng():
        print()
        print_warning("NeuTTS requires espeak-ng for phonemization.")
        if sys.platform == "darwin":
            print_info("Install with: brew install espeak-ng")
        elif sys.platform == "win32":
            print_info("Install with: choco install espeak-ng")
        else:
            print_info("Install with: sudo apt install espeak-ng")
        print()
        if prompt_yes_no("Install espeak-ng now?", True):
            try:
                if sys.platform == "darwin":
                    subprocess.run(["brew", "install", "espeak-ng"], check=True)
                elif sys.platform == "win32":
                    subprocess.run(["choco", "install", "espeak-ng", "-y"], check=True)
                else:
                    subprocess.run(["sudo", "apt", "install", "-y", "espeak-ng"], check=True)
                print_success("espeak-ng installed")
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                print_warning(f"Could not install espeak-ng automatically: {e}")
                print_info("Please install it manually and re-run setup.")
                return False
        else:
            print_warning("espeak-ng is required for NeuTTS. Install it manually before using NeuTTS.")

    # Install neutts Python package
    print()
    print_info("Installing neutts Python package...")
    print_info("This will also download the TTS model (~300MB) on first use.")
    print()
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-U", "neutts[all]", "--quiet"],
            check=True, timeout=300,
        )
        print_success("neutts installed successfully")
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print_error(f"Failed to install neutts: {e}")
        print_info("Try manually: python -m pip install -U neutts[all]")
        return False


def _setup_tts_provider(config: dict):
    """Interactive TTS provider selection with install flow for NeuTTS."""
    tts_config = config.get("tts", {})
    current_provider = tts_config.get("provider", "edge")
    subscription_features = get_nous_subscription_features(config)

    provider_labels = {
        "edge": "Edge TTS",
        "elevenlabs": "ElevenLabs",
        "openai": "OpenAI TTS",
        "minimax": "MiniMax TTS",
        "neutts": "NeuTTS",
    }
    current_label = provider_labels.get(current_provider, current_provider)

    print()
    print_header("文字转语音提供商（可选）")
    print_info(f"当前: {current_label}")
    print()

    choices = []
    providers = []
    if managed_nous_tools_enabled() and subscription_features.nous_auth_present:
        choices.append("Nous 订阅（托管 OpenAI TTS，从订阅计费）")
        providers.append("nous-openai")
    choices.extend(
        [
            "Edge TTS（免费，云端，无需配置）",
            "ElevenLabs（高品质，需要 API 密钥）",
            "OpenAI TTS（优质，需要 API 密钥）",
            "MiniMax TTS（高品质，支持语音克隆，需要 API 密钥）",
            "NeuTTS（本地设备，免费，约 300MB 模型下载）",
        ]
    )
    providers.extend(["edge", "elevenlabs", "openai", "minimax", "neutts"])
    choices.append(f"保持当前设置 ({current_label})")
    keep_current_idx = len(choices) - 1
    idx = prompt_choice("选择 TTS 提供商：", choices, keep_current_idx)

    if idx == keep_current_idx:
        return

    selected = providers[idx]
    selected_via_nous = selected == "nous-openai"
    if selected == "nous-openai":
        selected = "openai"
        print_info("OpenAI TTS 将使用托管的 Nous 网关，从您的订阅计费。")
        if get_env_value("VOICE_TOOLS_OPENAI_KEY") or get_env_value("OPENAI_API_KEY"):
            print_warning(
                "直接 OpenAI 凭据仍然已配置，在从 ~/.kunming/.env 移除之前可能优先使用。"
            )

    if selected == "neutts":
        # Check if already installed
        try:
            import importlib.util
            already_installed = importlib.util.find_spec("neutts") is not None
        except Exception:
            already_installed = False

        if already_installed:
            print_success("NeuTTS 已安装")
        else:
            print()
            print_info("NeuTTS 需要：")
            print_info("  -Python 包: neutts（约 50MB 安装 + 首次使用约 300MB 模型）")
            print_info("  -系统包: espeak-ng（音素化工具）")
            print()
            if prompt_yes_no("是否现在安装 NeuTTS 依赖？", True):
                if not _install_neutts_deps():
                    print_warning("NeuTTS 安装未完成。回退到 Edge TTS。")
                    selected = "edge"
            else:
                print_info("跳过安装。手动安装后将 tts.provider 设为 'neutts'。")
                selected = "edge"

    elif selected == "elevenlabs":
        existing = get_env_value("ELEVENLABS_API_KEY")
        if not existing:
            print()
            api_key = prompt("ElevenLabs API 密钥", password=True)
            if api_key:
                save_env_value("ELEVENLABS_API_KEY", api_key)
                print_success("ElevenLabs API 密钥已保存")
            else:
                print_warning("未提供 API 密钥。回退到 Edge TTS。")
                selected = "edge"

    elif selected == "openai" and not selected_via_nous:
        existing = get_env_value("VOICE_TOOLS_OPENAI_KEY") or get_env_value("OPENAI_API_KEY")
        if not existing:
            print()
            api_key = prompt("OpenAI TTS API 密钥", password=True)
            if api_key:
                save_env_value("VOICE_TOOLS_OPENAI_KEY", api_key)
                print_success("OpenAI TTS API 密钥已保存")
            else:
                print_warning("未提供 API 密钥。回退到 Edge TTS。")
                selected = "edge"

    elif selected == "minimax":
        existing = get_env_value("MINIMAX_API_KEY")
        if not existing:
            print()
            api_key = prompt("MiniMax TTS API 密钥", password=True)
            if api_key:
                save_env_value("MINIMAX_API_KEY", api_key)
                print_success("MiniMax TTS API 密钥已保存")
            else:
                print_warning("未提供 API 密钥。回退到 Edge TTS。")
                selected = "edge"

    # Save the selection
    if "tts" not in config:
        config["tts"] = {}
    config["tts"]["provider"] = selected
    save_config(config)
    print_success(f"TTS 提供商已设为: {provider_labels.get(selected, selected)}")


def setup_tts(config: dict):
    """Standalone TTS setup (for 'km setup tts')."""
    _setup_tts_provider(config)


# =============================================================================
# Section 2: Terminal Backend Configuration
# =============================================================================


def setup_terminal_backend(config: dict):
    """Configure the terminal execution backend."""
    import platform as _platform
    import shutil

    print_header("终端后端")
    print_info("选择 Kunming 运行 Shell 命令和代码的位置。")
    print_info("这会影响工具执行、文件访问和隔离性。")
    print_info(f"   指南: {_DOCS_BASE}/developer-guide/environments")
    print()

    current_backend = config.get("terminal", {}).get("backend", "local")
    is_linux = _platform.system() == "Linux"

    # Build backend choices with descriptions
    terminal_choices = [
        "本地 - 直接在本机运行（默认）",
        "Docker - 隔离容器，可配置资源",
        "Modal - 无服务器云沙箱",
        "SSH - 在远程机器上运行",
        "Daytona - 持久化云端开发环境",
    ]
    idx_to_backend = {0: "local", 1: "docker", 2: "modal", 3: "ssh", 4: "daytona"}
    backend_to_idx = {"local": 0, "docker": 1, "modal": 2, "ssh": 3, "daytona": 4}

    next_idx = 5
    if is_linux:
        terminal_choices.append("Singularity/Apptainer - HPC 友好容器")
        idx_to_backend[next_idx] = "singularity"
        backend_to_idx["singularity"] = next_idx
        next_idx += 1

    # Add keep current option
    keep_current_idx = next_idx
    terminal_choices.append(f"保持当前设置 ({current_backend})")
    idx_to_backend[keep_current_idx] = current_backend

    terminal_idx = prompt_choice(
        "选择终端后端：", terminal_choices, keep_current_idx
    )

    selected_backend = idx_to_backend.get(terminal_idx)

    if terminal_idx == keep_current_idx:
        print_info(f"保持当前后端: {current_backend}")
        return

    config.setdefault("terminal", {})["backend"] = selected_backend

    if selected_backend == "local":
        print_success("终端后端: 本地")
        print_info("命令直接在本机运行。")

        # CWD for messaging
        print()
        print_info("消息会话的工作目录：")
        print_info("  通过 Telegram/Discord 使用 Kunming 时，这是")
        print_info(
            "  代理的启动目录。CLI 模式始终使用当前目录。"
        )
        current_cwd = config.get("terminal", {}).get("cwd", "")
        cwd = prompt("  消息会话工作目录", current_cwd or str(Path.home()))
        if cwd:
            config["terminal"]["cwd"] = cwd

        # Sudo support
        print()
        existing_sudo = get_env_value("SUDO_PASSWORD")
        if existing_sudo:
            print_info("Sudo 密码: 已配置")
        else:
            if prompt_yes_no(
                "启用 sudo 支持？（存储密码用于 apt install 等）", False
            ):
                sudo_pass = prompt("  Sudo 密码", password=True)
                if sudo_pass:
                    save_env_value("SUDO_PASSWORD", sudo_pass)
                    print_success("Sudo 密码已保存")

    elif selected_backend == "docker":
        print_success("终端后端: Docker")

        # Check if Docker is available
        docker_bin = shutil.which("docker")
        if not docker_bin:
            print_warning("未在 PATH 中找到 Docker！")
            print_info("安装 Docker: https://docs.docker.com/get-docker/")
        else:
            print_info(f"已找到 Docker: {docker_bin}")

        # Docker image
        current_image = config.get("terminal", {}).get(
            "docker_image", "nikolaik/python-nodejs:python3.11-nodejs20"
        )
        image = prompt("  Docker 镜像", current_image)
        config["terminal"]["docker_image"] = image
        save_env_value("TERMINAL_DOCKER_IMAGE", image)

        _prompt_container_resources(config)

    elif selected_backend == "singularity":
        print_success("终端后端: Singularity/Apptainer")

        # Check if singularity/apptainer is available
        sing_bin = shutil.which("apptainer") or shutil.which("singularity")
        if not sing_bin:
            print_warning("未在 PATH 中找到 Singularity/Apptainer！")
            print_info(
                "安装: https://apptainer.org/docs/admin/main/installation.html"
            )
        else:
            print_info(f"已找到: {sing_bin}")

        current_image = config.get("terminal", {}).get(
            "singularity_image", "docker://nikolaik/python-nodejs:python3.11-nodejs20"
        )
        image = prompt("  容器镜像", current_image)
        config["terminal"]["singularity_image"] = image
        save_env_value("TERMINAL_SINGULARITY_IMAGE", image)

        _prompt_container_resources(config)

    elif selected_backend == "modal":
        print_success("终端后端: Modal")
        print_info("无服务器云沙箱。每次会话获得独立容器。")
        from tools.managed_tool_gateway import is_managed_tool_gateway_ready
        from tools.tool_backend_helpers import normalize_modal_mode

        managed_modal_available = bool(
            managed_nous_tools_enabled()
            and
            get_nous_subscription_features(config).nous_auth_present
            and is_managed_tool_gateway_ready("modal")
        )
        modal_mode = normalize_modal_mode(config.get("terminal", {}).get("modal_mode"))
        use_managed_modal = False
        if managed_modal_available:
            modal_choices = [
                "使用我的 Nous 订阅",
                "使用我自己的 Modal 账户",
            ]
            if modal_mode == "managed":
                default_modal_idx = 0
            elif modal_mode == "direct":
                default_modal_idx = 1
            else:
                default_modal_idx = 1 if get_env_value("MODAL_TOKEN_ID") else 0
            modal_mode_idx = prompt_choice(
                "选择 Modal 执行的计费方式：",
                modal_choices,
                default_modal_idx,
            )
            use_managed_modal = modal_mode_idx == 0

        if use_managed_modal:
            config["terminal"]["modal_mode"] = "managed"
            print_info("Modal 执行将使用托管的 Nous 网关，从您的订阅计费。")
            if get_env_value("MODAL_TOKEN_ID") or get_env_value("MODAL_TOKEN_SECRET"):
                print_info(
                    "直接 Modal 凭据仍然已配置，但此后端已固定为托管模式。"
                )
        else:
            config["terminal"]["modal_mode"] = "direct"
            print_info("需要 Modal 账户: https://modal.com")

            # Check if modal SDK is installed
            try:
                __import__("modal")
            except ImportError:
                print_info("正在安装 modal SDK...")
                import subprocess

                uv_bin = shutil.which("uv")
                if uv_bin:
                    result = subprocess.run(
                        [
                            uv_bin,
                            "pip",
                            "install",
                            "--python",
                            sys.executable,
                            "modal",
                        ],
                        capture_output=True,
                        text=True,
                    )
                else:
                    result = subprocess.run(
                        [sys.executable, "-m", "pip", "install", "modal"],
                        capture_output=True,
                        text=True,
                    )
                if result.returncode == 0:
                    print_success("modal SDK 已安装")
                else:
                    print_warning("安装失败 -请手动运行: pip install modal")

            # Modal token
            print()
            print_info("Modal 认证：")
            print_info("  获取 Token: https://modal.com/settings")
            existing_token = get_env_value("MODAL_TOKEN_ID")
            if existing_token:
                print_info("  Modal Token: 已配置")
                if prompt_yes_no("  更新 Modal 凭据？", False):
                    token_id = prompt("    Modal Token ID", password=True)
                    token_secret = prompt("    Modal Token Secret", password=True)
                    if token_id:
                        save_env_value("MODAL_TOKEN_ID", token_id)
                    if token_secret:
                        save_env_value("MODAL_TOKEN_SECRET", token_secret)
            else:
                token_id = prompt("    Modal Token ID", password=True)
                token_secret = prompt("    Modal Token Secret", password=True)
                if token_id:
                    save_env_value("MODAL_TOKEN_ID", token_id)
                if token_secret:
                    save_env_value("MODAL_TOKEN_SECRET", token_secret)

        _prompt_container_resources(config)

    elif selected_backend == "daytona":
        print_success("终端后端: Daytona")
        print_info("持久化云端开发环境。")
        print_info("每次会话获得独立沙箱，文件系统持久化。")
        print_info("注册地址: https://daytona.io")

        # Check if daytona SDK is installed
        try:
            __import__("daytona")
        except ImportError:
            print_info("正在安装 daytona SDK...")
            import subprocess

            uv_bin = shutil.which("uv")
            if uv_bin:
                result = subprocess.run(
                    [uv_bin, "pip", "install", "--python", sys.executable, "daytona"],
                    capture_output=True,
                    text=True,
                )
            else:
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "daytona"],
                    capture_output=True,
                    text=True,
                )
            if result.returncode == 0:
                print_success("daytona SDK 已安装")
            else:
                print_warning("安装失败 -请手动运行: pip install daytona")
                if result.stderr:
                    print_info(f"  Error: {result.stderr.strip().splitlines()[-1]}")

        # Daytona API key
        print()
        existing_key = get_env_value("DAYTONA_API_KEY")
        if existing_key:
            print_info("  Daytona API 密钥: 已配置")
            if prompt_yes_no("  更新 API 密钥？", False):
                api_key = prompt("    Daytona API 密钥", password=True)
                if api_key:
                    save_env_value("DAYTONA_API_KEY", api_key)
                    print_success("    已更新")
        else:
            api_key = prompt("    Daytona API 密钥", password=True)
            if api_key:
                save_env_value("DAYTONA_API_KEY", api_key)
                print_success("    已配置")

        # Daytona image
        current_image = config.get("terminal", {}).get(
            "daytona_image", "nikolaik/python-nodejs:python3.11-nodejs20"
        )
        image = prompt("  沙箱镜像", current_image)
        config["terminal"]["daytona_image"] = image
        save_env_value("TERMINAL_DAYTONA_IMAGE", image)

        _prompt_container_resources(config)

    elif selected_backend == "ssh":
        print_success("终端后端: SSH")
        print_info("通过 SSH 在远程机器上运行命令。")

        # SSH host
        current_host = get_env_value("TERMINAL_SSH_HOST") or ""
        host = prompt("  SSH 主机（主机名或 IP）", current_host)
        if host:
            save_env_value("TERMINAL_SSH_HOST", host)

        # SSH user
        current_user = get_env_value("TERMINAL_SSH_USER") or ""
        user = prompt("  SSH 用户", current_user or os.getenv("USER", ""))
        if user:
            save_env_value("TERMINAL_SSH_USER", user)

        # SSH port
        current_port = get_env_value("TERMINAL_SSH_PORT") or "22"
        port = prompt("  SSH 端口", current_port)
        if port and port != "22":
            save_env_value("TERMINAL_SSH_PORT", port)

        # SSH key
        current_key = get_env_value("TERMINAL_SSH_KEY") or ""
        default_key = str(Path.home() / ".ssh" / "id_rsa")
        ssh_key = prompt("  SSH 私钥路径", current_key or default_key)
        if ssh_key:
            save_env_value("TERMINAL_SSH_KEY", ssh_key)

        # Test connection
        if host and prompt_yes_no("  测试 SSH 连接？", True):
            print_info("  正在测试连接...")
            import subprocess

            ssh_cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5"]
            if ssh_key:
                ssh_cmd.extend(["-i", ssh_key])
            if port and port != "22":
                ssh_cmd.extend(["-p", port])
            ssh_cmd.append(f"{user}@{host}" if user else host)
            ssh_cmd.append("echo ok")
            result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                print_success("  SSH 连接成功！")
            else:
                print_warning(f"  SSH 连接失败: {result.stderr.strip()}")
                print_info("  请检查 SSH 密钥和主机设置。")

    # Sync terminal backend to .env so terminal_tool picks it up directly.
    # config.yaml is the source of truth, but terminal_tool reads TERMINAL_ENV.
    save_env_value("TERMINAL_ENV", selected_backend)
    if selected_backend == "modal":
        save_env_value("TERMINAL_MODAL_MODE", config["terminal"].get("modal_mode", "auto"))
    save_config(config)
    print()
    print_success(f"终端后端已设为: {selected_backend}")


# =============================================================================
# Section 3: Agent Settings
# =============================================================================


def _apply_default_agent_settings(config: dict):
    """Apply recommended defaults for all agent settings without prompting."""
    config.setdefault("agent", {})["max_turns"] = 90
    save_env_value("KUNMING_MAX_ITERATIONS", "90")

    config.setdefault("display", {})["tool_progress"] = "all"

    config.setdefault("compression", {})["enabled"] = True
    config["compression"]["threshold"] = 0.50

    config.setdefault("session_reset", {}).update({
        "mode": "both",
        "idle_minutes": 1440,
        "at_hour": 4,
    })

    save_config(config)
    print_success("已应用推荐默认值：")
    print_info("  最大迭代次数: 90")
    print_info("  工具进度显示: all")
    print_info("  压缩阈值: 0.50")
    print_info("  会话重置: 不活跃 (1440 分钟) + 每日 (4:00)")
    print_info("  稍后运行 `km setup agent` 自定义。")


def setup_agent_settings(config: dict):
    """Configure agent behavior: iterations, progress display, compression, session reset."""

    print_header("代理设置")
    print_info(f"   指南: {_DOCS_BASE}/user-guide/configuration")
    print()

    # -- Max Iterations --
    current_max = get_env_value("KUNMING_MAX_ITERATIONS") or str(
        config.get("agent", {}).get("max_turns", 90)
    )
    print_info("每次对话的最大工具调用迭代次数。")
    print_info("越高 = 可处理更复杂任务，但消耗更多 Token。")
    print_info("默认 90，适用于大多数任务。探索性任务建议 150+。")

    max_iter_str = prompt("最大迭代次数", current_max)
    try:
        max_iter = int(max_iter_str)
        if max_iter > 0:
            save_env_value("KUNMING_MAX_ITERATIONS", str(max_iter))
            config.setdefault("agent", {})["max_turns"] = max_iter
            config.pop("max_turns", None)
            print_success(f"最大迭代次数已设为 {max_iter}")
    except ValueError:
        print_warning("无效数字，保持当前值")

    # -- Tool Progress Display --
    print_info("")
    print_info("工具进度显示")
    print_info("控制工具活动的显示程度（CLI 和消息平台）。")
    print_info("  off     - 静默，仅显示最终响应")
    print_info("  new     - 仅在工具名称变化时显示（减少噪音）")
    print_info("  all     - 显示每次工具调用及简短预览")
    print_info("  verbose - 完整参数、结果和调试日志")

    current_mode = config.get("display", {}).get("tool_progress", "all")
    mode = prompt("工具进度模式", current_mode)
    if mode.lower() in ("off", "new", "all", "verbose"):
        if "display" not in config:
            config["display"] = {}
        config["display"]["tool_progress"] = mode.lower()
        save_config(config)
        print_success(f"工具进度已设为: {mode.lower()}")
    else:
        print_warning(f"未知模式 '{mode}'，保持 '{current_mode}'")

    # -- Context Compression --
    print_header("上下文压缩")
    print_info("当上下文过长时自动摘要旧消息。")
    print_info(
        "阈值越高 = 越晚压缩（使用更多上下文）。阈值越低 = 越早压缩。"
    )

    config.setdefault("compression", {})["enabled"] = True

    current_threshold = config.get("compression", {}).get("threshold", 0.50)
    threshold_str = prompt("压缩阈值 (0.5-0.95)", str(current_threshold))
    try:
        threshold = float(threshold_str)
        if 0.5 <= threshold <= 0.95:
            config["compression"]["threshold"] = threshold
    except ValueError:
        pass

    print_success(
        f"上下文压缩阈值已设为 {config['compression'].get('threshold', 0.50)}"
    )

    # -- Session Reset Policy --
    print_header("会话重置策略")
    print_info(
        "消息平台会话（Telegram、Discord 等）会随时间积累上下文。"
    )
    print_info(
        "每条消息都会添加到对话历史中，这意味着 API 成本不断增长。"
    )
    print_info("")
    print_info(
        "为管理此问题，会话可以在一段不活跃时间后自动重置，"
    )
    print_info(
        "或在每天固定时间重置。重置时，代理会先将重要内容"
    )
    print_info(
        "保存到持久化记忆中 -但对话上下文会被清除。"
    )
    print_info("")
    print_info("您也可以随时在聊天中输入 /reset 手动重置。")
    print_info("")

    reset_choices = [
        "不活跃 + 每日重置（推荐 - 先触发者生效）",
        "仅不活跃重置（N 分钟无消息后重置）",
        "仅每日重置（每天固定时间重置）",
        "从不自动重置（上下文持续到 /reset 或压缩）",
        "保持当前设置",
    ]

    current_policy = config.get("session_reset", {})
    current_mode = current_policy.get("mode", "both")
    current_idle = current_policy.get("idle_minutes", 1440)
    current_hour = current_policy.get("at_hour", 4)

    default_reset = {"both": 0, "idle": 1, "daily": 2, "none": 3}.get(current_mode, 0)

    reset_idx = prompt_choice("会话重置模式：", reset_choices, default_reset)

    config.setdefault("session_reset", {})

    if reset_idx == 0:  # Both
        config["session_reset"]["mode"] = "both"
        idle_str = prompt("  不活跃超时（分钟）", str(current_idle))
        try:
            idle_val = int(idle_str)
            if idle_val > 0:
                config["session_reset"]["idle_minutes"] = idle_val
        except ValueError:
            pass
        hour_str = prompt("  每日重置时间（0-23，本地时间）", str(current_hour))
        try:
            hour_val = int(hour_str)
            if 0 <= hour_val <= 23:
                config["session_reset"]["at_hour"] = hour_val
        except ValueError:
            pass
        print_success(
            f"会话将在 {config['session_reset'].get('idle_minutes', 1440)} 分钟不活跃或每日 {config['session_reset'].get('at_hour', 4)}:00 时重置"
        )
    elif reset_idx == 1:  # Idle only
        config["session_reset"]["mode"] = "idle"
        idle_str = prompt("  不活跃超时（分钟）", str(current_idle))
        try:
            idle_val = int(idle_str)
            if idle_val > 0:
                config["session_reset"]["idle_minutes"] = idle_val
        except ValueError:
            pass
        print_success(
            f"会话将在 {config['session_reset'].get('idle_minutes', 1440)} 分钟不活跃后重置"
        )
    elif reset_idx == 2:  # Daily only
        config["session_reset"]["mode"] = "daily"
        hour_str = prompt("  每日重置时间（0-23，本地时间）", str(current_hour))
        try:
            hour_val = int(hour_str)
            if 0 <= hour_val <= 23:
                config["session_reset"]["at_hour"] = hour_val
        except ValueError:
            pass
        print_success(
            f"会话将在每日 {config['session_reset'].get('at_hour', 4)}:00 时重置"
        )
    elif reset_idx == 3:  # None
        config["session_reset"]["mode"] = "none"
        print_info(
            "会话从不自动重置。上下文仅通过压缩管理。"
        )
        print_warning(
            "长对话成本会持续增长。需要时请手动使用 /reset。"
        )
    # else: keep current (idx == 4)

    save_config(config)


# =============================================================================
# Section 4: Messaging Platforms (Gateway)
# =============================================================================


def _setup_telegram():
    """Configure Telegram bot credentials and allowlist."""
    print_header("Telegram")
    existing = get_env_value("TELEGRAM_BOT_TOKEN")
    if existing:
        print_info("Telegram: 已配置")
        if not prompt_yes_no("重新配置 Telegram？", False):
            # Check missing allowlist on existing config
            if not get_env_value("TELEGRAM_ALLOWED_USERS"):
                print_info("Telegram 未设置用户白名单 -任何人都可以使用你的机器人！")
                if prompt_yes_no("现在添加允许的用户？", True):
                    print_info("   查找你的 Telegram 用户 ID: 发消息给 @userinfobot")
                    allowed_users = prompt("允许的用户 ID（逗号分隔）")
                    if allowed_users:
                        save_env_value("TELEGRAM_ALLOWED_USERS", allowed_users.replace(" ", ""))
                        print_success("Telegram 白名单已配置")
            return

    print_info("通过 Telegram 上的 @BotFather 创建机器人")
    token = prompt("Telegram 机器人 Token", password=True)
    if not token:
        return
    save_env_value("TELEGRAM_BOT_TOKEN", token)
    print_success("Telegram Token 已保存")

    print()
    print_info("ð Security: Restrict who can use your bot")
    print_info("   查找你的 Telegram 用户 ID：")
    print_info("   1. 在 Telegram 上给 @userinfobot 发消息")
    print_info("   2. 它会回复你的数字 ID（例如 123456789）")
    print()
    allowed_users = prompt(
        "允许的用户 ID（逗号分隔，留空则开放访问）"
    )
    if allowed_users:
        save_env_value("TELEGRAM_ALLOWED_USERS", allowed_users.replace(" ", ""))
        print_success("Telegram 白名单已配置 -仅列出的用户可以使用机器人")
    else:
        print_info("未设置白名单 -任何找到你机器人的人都可以使用！")

    print()
    print_info("ðŸ“¬ Home Channel: where Kunming delivers cron job results,")
    print_info("   跨平台消息和通知的位置。")
    print_info("   对于 Telegram 私聊，这是你的用户 ID（同上）。")

    first_user_id = allowed_users.split(",")[0].strip() if allowed_users else ""
    if first_user_id:
        if prompt_yes_no(f"使用你的用户 ID ({first_user_id}) 作为主频道？", True):
            save_env_value("TELEGRAM_HOME_CHANNEL", first_user_id)
            print_success(f"Telegram 主频道已设为 {first_user_id}")
        else:
            home_channel = prompt("主频道 ID（或留空稍后在 Telegram 中使用 /set-home 设置）")
            if home_channel:
                save_env_value("TELEGRAM_HOME_CHANNEL", home_channel)
    else:
        print_info("   你也可以稍后在 Telegram 聊天中输入 /set-home 来设置。")
        home_channel = prompt("主频道 ID（留空稍后设置）")
        if home_channel:
            save_env_value("TELEGRAM_HOME_CHANNEL", home_channel)


def _setup_discord():
    """Configure Discord bot credentials and allowlist."""
    print_header("Discord")
    existing = get_env_value("DISCORD_BOT_TOKEN")
    if existing:
        print_info("Discord: 已配置")
        if not prompt_yes_no("重新配置 Discord？", False):
            if not get_env_value("DISCORD_ALLOWED_USERS"):
                print_info("Discord 未设置用户白名单 -任何人都可以使用你的机器人！")
                if prompt_yes_no("现在添加允许的用户？", True):
                    print_info("   查找 Discord ID: 启用开发者模式，右键点击名称 ->复制 ID")
                    allowed_users = prompt("允许的用户 ID（逗号分隔）")
                    if allowed_users:
                        cleaned_ids = _clean_discord_user_ids(allowed_users)
                        save_env_value("DISCORD_ALLOWED_USERS", ",".join(cleaned_ids))
                        print_success("Discord 白名单已配置")
            return

    print_info("在 https://discord.com/developers/applications 创建机器人")
    token = prompt("Discord 机器人 Token", password=True)
    if not token:
        return
    save_env_value("DISCORD_BOT_TOKEN", token)
    print_success("Discord Token 已保存")

    print()
    print_info("ð Security: Restrict who can use your bot")
    print_info("   查找你的 Discord 用户 ID：")
    print_info("   1. 在 Discord 设置中启用开发者模式")
    print_info("   2. 右键点击你的名称 ->复制 ID")
    print()
    print_info("   你也可以使用 Discord 用户名（网关启动时解析）。")
    print()
    allowed_users = prompt(
        "允许的用户 ID 或用户名（逗号分隔，留空则开放访问）"
    )
    if allowed_users:
        cleaned_ids = _clean_discord_user_ids(allowed_users)
        save_env_value("DISCORD_ALLOWED_USERS", ",".join(cleaned_ids))
        print_success("Discord 白名单已配置")
    else:
        print_info("未设置白名单 -你机器人所在服务器的任何人都可以使用！")

    print()
    print_info("ð¬ Home Channel: where Kunming delivers cron job results,")
    print_info("   跨平台消息和通知的位置。")
    print_info("   获取频道 ID: 右键点击频道 ->复制频道 ID")
    print_info("   （需要在 Discord 设置中启用开发者模式）")
    print_info("   你也可以稍后在 Discord 频道中输入 /set-home 来设置。")
    home_channel = prompt("主频道 ID（留空稍后使用 /set-home 设置）")
    if home_channel:
        save_env_value("DISCORD_HOME_CHANNEL", home_channel)


def _clean_discord_user_ids(raw: str) -> list:
    """Strip common Discord mention prefixes from a comma-separated ID string."""
    cleaned = []
    for uid in raw.replace(" ", "").split(","):
        uid = uid.strip()
        if uid.startswith("<@") and uid.endswith(">"):
            uid = uid.lstrip("<@!").rstrip(">")
        if uid.lower().startswith("user:"):
            uid = uid[5:]
        if uid:
            cleaned.append(uid)
    return cleaned


def _setup_slack():
    """Configure Slack bot credentials."""
    print_header("Slack")
    existing = get_env_value("SLACK_BOT_TOKEN")
    if existing:
        print_info("Slack: 已配置")
        if not prompt_yes_no("重新配置 Slack？", False):
            return

    print_info("创建 Slack 应用的步骤：")
    print_info("   1. 前往 https://api.slack.com/apps ->创建新应用（从零开始）")
    print_info("   2. 启用 Socket Mode: Settings ->Socket Mode ->Enable")
    print_info("      -创建带有 'connections:write' 权限的 App-Level Token")
    print_info("   3. 添加 Bot Token 权限: Features ->OAuth & Permissions")
    print_info("      必需权限: chat:write, app_mentions:read,")
    print_info("      channels:history, channels:read, im:history,")
    print_info("      im:read, im:write, users:read, files:write")
    print_info("      私有频道可选: groups:history")
    print_info("   4. 订阅事件: Features ->Event Subscriptions ->Enable")
    print_info("      必需事件: message.im, message.channels, app_mention")
    print_info("      私有频道可选: message.groups")
    print_warning("   [ON]没有 message.channels 权限，机器人只能在私聊中工作，")
    print_warning("     无法在公共频道中使用。")
    print_info("   5. 安装到工作区: Settings ->Install App")
    print_info("   6. 修改权限或事件后需要重新安装应用")
    print_info("   7. 安装后，邀请机器人到频道: /invite @YourBot")
    print()
    print_info("   完整指南: https://kunming-agent.kunming.dev/docs/user-guide/messaging/slack/")
    print()
    bot_token = prompt("Slack Bot Token (xoxb-...)", password=True)
    if not bot_token:
        return
    save_env_value("SLACK_BOT_TOKEN", bot_token)
    app_token = prompt("Slack App Token (xapp-...)", password=True)
    if app_token:
        save_env_value("SLACK_APP_TOKEN", app_token)
    print_success("Slack Token 已保存")

    print()
    print_info("ð Security: Restrict who can use your bot")
    print_info("   查找成员 ID: 点击用户名称 ->查看完整资料 ->... ->复制成员 ID")
    print()
    allowed_users = prompt(
        "允许的用户 ID（逗号分隔，留空则拒绝除配对用户外的所有人）"
    )
    if allowed_users:
        save_env_value("SLACK_ALLOWED_USERS", allowed_users.replace(" ", ""))
        print_success("Slack 白名单已配置")
    else:
        print_warning("未设置 Slack 白名单 -未配对用户默认将被拒绝。")
        print_info("   仅在有意开放工作区访问时设置 SLACK_ALLOW_ALL_USERS=true 或 GATEWAY_ALLOW_ALL_USERS=true。")


def _setup_matrix():
    """Configure Matrix credentials."""
    print_header("Matrix")
    existing = get_env_value("MATRIX_ACCESS_TOKEN") or get_env_value("MATRIX_PASSWORD")
    if existing:
        print_info("Matrix: 已配置")
        if not prompt_yes_no("重新配置 Matrix？", False):
            return

    print_info("支持任何 Matrix 主服务器（Synapse、Conduit、Dendrite 或 matrix.org）。")
    print_info("   1. 在主服务器上创建机器人用户，或使用你自己的账户")
    print_info("   2. 从 Element 获取访问令牌，或提供用户 ID + 密码")
    print()
    homeserver = prompt("主服务器 URL（例如 https://matrix.example.org）")
    if homeserver:
        save_env_value("MATRIX_HOMESERVER", homeserver.rstrip("/"))

    print()
    print_info("认证：提供访问令牌（推荐），或用户 ID + 密码。")
    token = prompt("访问令牌（留空使用密码登录）", password=True)
    if token:
        save_env_value("MATRIX_ACCESS_TOKEN", token)
        user_id = prompt("用户 ID (@bot:server -可选，将自动检测)")
        if user_id:
            save_env_value("MATRIX_USER_ID", user_id)
        print_success("Matrix 访问令牌已保存")
    else:
        user_id = prompt("用户 ID (@bot:server)")
        if user_id:
            save_env_value("MATRIX_USER_ID", user_id)
        password = prompt("密码", password=True)
        if password:
            save_env_value("MATRIX_PASSWORD", password)
            print_success("Matrix 凭据已保存")

    if token or get_env_value("MATRIX_PASSWORD"):
        print()
        want_e2ee = prompt_yes_no("启用端到端加密 (E2EE)？", False)
        if want_e2ee:
            save_env_value("MATRIX_ENCRYPTION", "true")
            print_success("E2EE 已启用")

        matrix_pkg = "matrix-nio[e2e]" if want_e2ee else "matrix-nio"
        try:
            __import__("nio")
        except ImportError:
            print_info(f"正在安装 {matrix_pkg}...")
            import subprocess
            uv_bin = shutil.which("uv")
            if uv_bin:
                result = subprocess.run(
                    [uv_bin, "pip", "install", "--python", sys.executable, matrix_pkg],
                    capture_output=True, text=True,
                )
            else:
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", matrix_pkg],
                    capture_output=True, text=True,
                )
            if result.returncode == 0:
                print_success(f"{matrix_pkg} 已安装")
            else:
                print_warning(f"安装失败 -请手动运行: pip install '{matrix_pkg}'")
                if result.stderr:
                    print_info(f"  错误: {result.stderr.strip().splitlines()[-1]}")

        print()
        print_info("ð Security: Restrict who can use your bot")
        print_info("   Matrix 用户 ID 格式如 @username:server")
        print()
        allowed_users = prompt("允许的用户 ID（逗号分隔，留空则开放访问）")
        if allowed_users:
            save_env_value("MATRIX_ALLOWED_USERS", allowed_users.replace(" ", ""))
            print_success("Matrix 白名单已配置")
        else:
            print_info("未设置白名单 -任何能给机器人发消息的人都可以使用！")

        print()
        print_info("ðŸ“¬ Home Room: where Kunming delivers cron job results and notifications.")
        print_info("   房间 ID 格式如 !abc123:server（在 Element 房间设置中查看）")
        print_info("   你也可以稍后在 Matrix 房间中输入 /set-home 来设置。")
        home_room = prompt("主房间 ID（留空稍后使用 /set-home 设置）")
        if home_room:
            save_env_value("MATRIX_HOME_ROOM", home_room)


def _setup_mattermost():
    """Configure Mattermost bot credentials."""
    print_header("Mattermost")
    existing = get_env_value("MATTERMOST_TOKEN")
    if existing:
        print_info("Mattermost: 已配置")
        if not prompt_yes_no("重新配置 Mattermost？", False):
            return

    print_info("支持任何自托管的 Mattermost 实例。")
    print_info("   1. 在 Mattermost 中: Integrations ->Bot Accounts ->Add Bot Account")
    print_info("   2. 复制机器人 Token")
    print()
    mm_url = prompt("Mattermost 服务器 URL（例如 https://mm.example.com）")
    if mm_url:
        save_env_value("MATTERMOST_URL", mm_url.rstrip("/"))
    token = prompt("机器人 Token", password=True)
    if not token:
        return
    save_env_value("MATTERMOST_TOKEN", token)
    print_success("Mattermost Token 已保存")

    print()
    print_info("ð Security: Restrict who can use your bot")
    print_info("   查找用户 ID: 点击你的头像 ->个人资料")
    print_info("   或使用 API: GET /api/v4/users/me")
    print()
    allowed_users = prompt("允许的用户 ID（逗号分隔，留空则开放访问）")
    if allowed_users:
        save_env_value("MATTERMOST_ALLOWED_USERS", allowed_users.replace(" ", ""))
        print_success("Mattermost 白名单已配置")
    else:
        print_info("未设置白名单 -任何能给机器人发消息的人都可以使用！")

    print()
    print_info("ðŸ“¬ Home Channel: where Kunming delivers cron job results and notifications.")
    print_info("   获取频道 ID: 点击频道名称 ->查看信息 ->复制 ID")
    print_info("   你也可以稍后在 Mattermost 频道中输入 /set-home 来设置。")
    home_channel = prompt("主频道 ID（留空稍后使用 /set-home 设置）")
    if home_channel:
        save_env_value("MATTERMOST_HOME_CHANNEL", home_channel)


def _setup_whatsapp():
    """Configure WhatsApp bridge."""
    print_header("WhatsApp")
    existing = get_env_value("WHATSAPP_ENABLED")
    if existing:
        print_info("WhatsApp: 已启用")
        return

    print_info("WhatsApp 通过内置桥接（Baileys）连接。")
    print_info("需要 Node.js。运行 'km whatsapp' 进行引导式设置。")
    print()
    if prompt_yes_no("现在启用 WhatsApp？", True):
        save_env_value("WHATSAPP_ENABLED", "true")
        print_success("WhatsApp 已启用")
        print_info("运行 'km whatsapp' 选择模式（独立机器人号码")
        print_info("或个人自聊）并通过二维码配对。")


def _setup_webhooks():
    """Configure webhook integration."""
    print_header("Webhooks")
    existing = get_env_value("WEBHOOK_ENABLED")
    if existing:
        print_info("Webhooks: 已配置")
        if not prompt_yes_no("重新配置 Webhooks？", False):
            return

    print()
    print_warning("[ON] Webhook 和 SMS 平台需要将网关端口暴露到互联网。")
    print_warning("   为安全起见，请在沙箱环境（Docker、VM 等）中运行网关，")
    print_warning("   以限制提示注入攻击的影响范围。")
    print()
    print_info("   完整指南: https://kunming-agent.kunming.dev/docs/user-guide/messaging/webhooks/")
    print()

    port = prompt("Webhook 端口（默认 8644）")
    if port:
        try:
            save_env_value("WEBHOOK_PORT", str(int(port)))
            print_success(f"Webhook 端口已设为 {port}")
        except ValueError:
            print_warning("无效端口号，使用默认值 8644")

    secret = prompt("全局 HMAC 密钥（所有路由共享）", password=True)
    if secret:
        save_env_value("WEBHOOK_SECRET", secret)
        print_success("Webhook 密钥已保存")
    else:
        print_warning("未设置密钥 -必须在 config.yaml 中配置每个路由的密钥")

    save_env_value("WEBHOOK_ENABLED", "true")
    print()
    print_success("Webhooks 已启用！后续步骤：")
    from kunming_constants import display_kunming_home as _dhh
    print_info(f"   1. 在 {_dhh()}/config.yaml 中定义 Webhook 路由")
    print_info("   2. 将你的服务（GitHub、GitLab 等）指向：")
    print_info("      http://your-server:8644/webhooks/<route-name>")
    print()
    print_info("   路由配置指南：")
    print_info("   https://kunming-agent.kunming.dev/docs/user-guide/messaging/webhooks/#configuring-routes")
    print()
    print_info("   在编辑器中打开配置:  km config edit")


# Platform registry for the gateway checklist
_GATEWAY_PLATFORMS = [
    ("Telegram", "TELEGRAM_BOT_TOKEN", _setup_telegram),
    ("Discord", "DISCORD_BOT_TOKEN", _setup_discord),
    ("Slack", "SLACK_BOT_TOKEN", _setup_slack),
    ("Matrix", "MATRIX_ACCESS_TOKEN", _setup_matrix),
    ("Mattermost", "MATTERMOST_TOKEN", _setup_mattermost),
    ("WhatsApp", "WHATSAPP_ENABLED", _setup_whatsapp),
    ("Webhooks (GitHub, GitLab, etc.)", "WEBHOOK_ENABLED", _setup_webhooks),
]


def setup_gateway(config: dict):
    """Configure messaging platform integrations."""
    print_header("消息平台")
    print_info("连接消息平台，随时随地与 Kunming 对话。")
    print_info("空格键切换选择，回车键确认。")
    print()

    # Build checklist items, pre-selecting already-configured platforms
    items = []
    pre_selected = []
    for i, (name, env_var, _func) in enumerate(_GATEWAY_PLATFORMS):
        # Matrix has two possible env vars
        is_configured = bool(get_env_value(env_var))
        if name == "Matrix" and not is_configured:
            is_configured = bool(get_env_value("MATRIX_PASSWORD"))
        label = f"{name}  (已配置)" if is_configured else name
        items.append(label)
        if is_configured:
            pre_selected.append(i)

    selected = prompt_checklist("选择要配置的平台：", items, pre_selected)

    if not selected:
        print_info("未选择任何平台。稍后运行 'km setup gateway' 进行配置。")
        return

    for idx in selected:
        name, _env_var, setup_func = _GATEWAY_PLATFORMS[idx]
        setup_func()

    # -- Gateway Service Setup --
    any_messaging = (
        get_env_value("TELEGRAM_BOT_TOKEN")
        or get_env_value("DISCORD_BOT_TOKEN")
        or get_env_value("SLACK_BOT_TOKEN")
        or get_env_value("MATTERMOST_TOKEN")
        or get_env_value("MATRIX_ACCESS_TOKEN")
        or get_env_value("MATRIX_PASSWORD")
        or get_env_value("WHATSAPP_ENABLED")
        or get_env_value("WEBHOOK_ENABLED")
    )
    if any_messaging:
        print()
        print_info("+" * 50)
        print_success("消息平台已配置！")

        # Check if any home channels are missing
        missing_home = []
        if get_env_value("TELEGRAM_BOT_TOKEN") and not get_env_value(
            "TELEGRAM_HOME_CHANNEL"
        ):
            missing_home.append("Telegram")
        if get_env_value("DISCORD_BOT_TOKEN") and not get_env_value(
            "DISCORD_HOME_CHANNEL"
        ):
            missing_home.append("Discord")
        if get_env_value("SLACK_BOT_TOKEN") and not get_env_value("SLACK_HOME_CHANNEL"):
            missing_home.append("Slack")

        if missing_home:
            print()
            print_warning(f"未设置主频道: {', '.join(missing_home)}")
            print_info("   没有主频道，定时任务和跨平台消息")
            print_info("   无法投递到这些平台。")
            print_info("   稍后在聊天中使用 /set-home 设置，或：")
            for plat in missing_home:
                print_info(
                    f"     km config set {plat.upper()}_HOME_CHANNEL <channel_id>"
                )

        # Offer to install the gateway as a system service
        import platform as _platform

        _is_linux = _platform.system() == "Linux"
        _is_macos = _platform.system() == "Darwin"

        from kunming_cli.gateway import (
            _is_service_installed,
            _is_service_running,
            has_conflicting_systemd_units,
            install_linux_gateway_from_setup,
            print_systemd_scope_conflict_warning,
            systemd_start,
            systemd_restart,
            launchd_install,
            launchd_start,
            launchd_restart,
        )

        service_installed = _is_service_installed()
        service_running = _is_service_running()

        print()
        if _is_linux and has_conflicting_systemd_units():
            print_systemd_scope_conflict_warning()
            print()

        if service_running:
            if prompt_yes_no("  重启网关以应用更改？", True):
                try:
                    if _is_linux:
                        systemd_restart()
                    elif _is_macos:
                        launchd_restart()
                except Exception as e:
                    print_error(f"  重启失败: {e}")
        elif service_installed:
            if prompt_yes_no("  启动网关服务？", True):
                try:
                    if _is_linux:
                        systemd_start()
                    elif _is_macos:
                        launchd_start()
                except Exception as e:
                    print_error(f"  启动失败: {e}")
        elif _is_linux or _is_macos:
            svc_name = "systemd" if _is_linux else "launchd"
            if prompt_yes_no(
                f"  将网关安装为 {svc_name} 服务？（后台运行，开机自启）",
                True,
            ):
                try:
                    installed_scope = None
                    did_install = False
                    if _is_linux:
                        installed_scope, did_install = install_linux_gateway_from_setup(force=False)
                    else:
                        launchd_install(force=False)
                        did_install = True
                    print()
                    if did_install and prompt_yes_no("  现在启动服务？", True):
                        try:
                            if _is_linux:
                                systemd_start(system=installed_scope == "system")
                            elif _is_macos:
                                launchd_start()
                        except Exception as e:
                            print_error(f"  启动失败: {e}")
                except Exception as e:
                    print_error(f"  安装失败: {e}")
                    print_info("  你可以手动尝试: km gateway install")
            else:
                print_info("  稍后安装: km gateway install")
                if _is_linux:
                    print_info("  或作为开机服务: sudo km gateway install --system")
                print_info("  或前台运行:  km gateway")
        else:
            print_info("启动网关使你的机器人上线：")
            print_info("   km gateway              # 前台运行")

        print_info("+" * 50)


# =============================================================================
# Section 5: Tool Configuration (delegates to unified tools_config.py)
# =============================================================================


def setup_tools(config: dict, first_install: bool = False):
    """Configure tools -delegates to the unified tools_command() in tools_config.py.

    Both `km setup tools` and `km tools` use the same flow:
    platform selection ->toolset toggles ->provider/API key configuration.

    Args:
        first_install: When True, uses the simplified first-install flow
            (no platform menu, prompts for all unconfigured API keys).
    """
    from kunming_cli.tools_config import tools_command

    tools_command(first_install=first_install, config=config)


# =============================================================================
# Post-Migration Section Skip Logic
# =============================================================================


def _get_section_config_summary(config: dict, section_key: str) -> Optional[str]:
    """Return a short summary if a setup section is already configured, else None.

    ``get_env_value`` is the module-level import from kunming_cli.config
    so that test patches on ``setup_mod.get_env_value`` take effect.
    """
    if section_key == "model":
        has_key = bool(
            get_env_value("OPENROUTER_API_KEY")
            or get_env_value("OPENAI_API_KEY")
            or get_env_value("ANTHROPIC_API_KEY")
        )
        if not has_key:
            # Check for OAuth providers
            try:
                from kunming_cli.auth import get_active_provider
                if get_active_provider():
                    has_key = True
            except Exception:
                pass
        if not has_key:
            return None
        model = config.get("model")
        if isinstance(model, str) and model.strip():
            return model.strip()
        if isinstance(model, dict):
            return str(model.get("default") or model.get("model") or "configured")
        return "configured"

    elif section_key == "terminal":
        backend = config.get("terminal", {}).get("backend", "local")
        return f"backend: {backend}"

    elif section_key == "agent":
        max_turns = config.get("agent", {}).get("max_turns", 90)
        return f"max turns: {max_turns}"

    elif section_key == "gateway":
        platforms = []
        if get_env_value("TELEGRAM_BOT_TOKEN"):
            platforms.append("Telegram")
        if get_env_value("DISCORD_BOT_TOKEN"):
            platforms.append("Discord")
        if get_env_value("SLACK_BOT_TOKEN"):
            platforms.append("Slack")
        if get_env_value("WHATSAPP_PHONE_NUMBER_ID"):
            platforms.append("WhatsApp")
        if get_env_value("SIGNAL_ACCOUNT"):
            platforms.append("Signal")
        if platforms:
            return ", ".join(platforms)
        return None  # No platforms configured -section must run

    elif section_key == "tools":
        tools = []
        if get_env_value("ELEVENLABS_API_KEY"):
            tools.append("TTS/ElevenLabs")
        if get_env_value("BROWSERBASE_API_KEY"):
            tools.append("Browser")
        if get_env_value("FIRECRAWL_API_KEY"):
            tools.append("Firecrawl")
        if tools:
            return ", ".join(tools)
        return None

    return None


def _skip_configured_section(
    config: dict, section_key: str, label: str
) -> bool:
    """Show an already-configured section summary and offer to skip.

    Returns True if the user chose to skip, False if the section should run.
    """
    summary = _get_section_config_summary(config, section_key)
    if not summary:
        return False
    print()
    print_success(f"  {label}: {summary}")
    return not prompt_yes_no(f"  重新配置 {label.lower()}？", default=False)


# =============================================================================
# Main Wizard Orchestrator
# =============================================================================

SETUP_SECTIONS = [
    ("model", "模型与提供商", setup_model_provider),
    ("tts", "文字转语音", setup_tts),
    ("terminal", "终端后端", setup_terminal_backend),
    ("gateway", "消息平台（网关）", setup_gateway),
    ("tools", "工具", setup_tools),
    ("agent", "代理设置", setup_agent_settings),
]

# The returning-user menu intentionally omits standalone TTS because model setup
# already includes TTS selection and tools setup covers the rest of the provider
# configuration. Keep this list in the same order as the visible menu entries.
RETURNING_USER_MENU_SECTION_KEYS = [
    "model",
    "terminal",
    "gateway",
    "tools",
    "agent",
]


def run_setup_wizard(args):
    """Run the interactive setup wizard.

    Supports full, quick, and section-specific setup:
      km setup           -full or quick (auto-detected)
      km setup model     -just model/provider
      km setup terminal  -just terminal backend
      km setup gateway   -just messaging platforms
      km setup tools     -just tool configuration
      km setup agent     -just agent settings
    """
    from kunming_cli.config import is_managed, managed_error
    if is_managed():
        managed_error("run setup wizard")
        return
    ensure_kunming_home()

    config = load_config()
    kunming_home = get_kunming_home()

    # Detect non-interactive environments (headless SSH, Docker, CI/CD)
    non_interactive = getattr(args, 'non_interactive', False)
    if not non_interactive and not is_interactive_stdin():
        non_interactive = True

    if non_interactive:
        print_noninteractive_setup_guidance(
            "运行在非交互环境中（未检测到 TTY）。"
        )
        return

    # Check if a specific section was requested
    section = getattr(args, "section", None)
    if section:
        for key, label, func in SETUP_SECTIONS:
            if key == section:
                print()
                print(
                    color(
                        "+---------------------------------------------------------+",
                        Colors.MAGENTA,
                    )
                )
                print(color(f"|    [ON] km setup - {label:<33s} |", Colors.MAGENTA))
                print(
                    color(
                        "+---------------------------------------------------------+",
                        Colors.MAGENTA,
                    )
                )
                func(config)
                save_config(config)
                print()
                print_success(f"{label} 配置完成！")
                return

        print_error(f"未知的设置区段: {section}")
        print_info(f"可用区段: {', '.join(k for k, _, _ in SETUP_SECTIONS)}")
        return

    # Check if this is an existing installation with a provider configured
    from kunming_cli.auth import get_active_provider

    active_provider = get_active_provider()
    is_existing = (
        bool(get_env_value("OPENROUTER_API_KEY"))
        or bool(get_env_value("OPENAI_BASE_URL"))
        or active_provider is not None
    )

    print()
    print(
        color(
            "+---------------------------------------------------------+",
            Colors.MAGENTA,
        )
    )
    print(
        color(
            "|            [ON] Kunming Agent 设置向导                  |",
            Colors.MAGENTA,
        )
    )
    print(
        color(
            "+---------------------------------------------------------+",
            Colors.MAGENTA,
        )
    )
    print(
        color(
            "| 让我们配置你的 Kunming Agent 安装。                     |",
            Colors.MAGENTA,
        )
    )
    print(
        color(
            "| 随时按 Ctrl+C 退出。                                    |",
            Colors.MAGENTA,
        )
    )
    print(
        color(
            "+---------------------------------------------------------+",
            Colors.MAGENTA,
        )
    )

    if is_existing:
        # -- Returning User Menu --
        print()
        print_header("欢迎回来！")
        print_success("你已经配置过 km 了。")
        print()

        menu_choices = [
            "快速设置 -仅配置缺少的项目",
            "完整设置 -重新配置所有内容",
            "---",
            "模型与提供商",
            "终端后端",
            "消息平台（网关）",
            "工具",
            "代理设置",
            "---",
            "退出",
        ]

        # Separator indices (not selectable, but prompt_choice doesn't filter them,
        # so we handle them below)
        choice = prompt_choice("你想做什么？", menu_choices, 0)

        if choice == 0:
            # Quick setup
            _run_quick_setup(config, kunming_home)
            return
        elif choice == 1:
            # Full setup -fall through to run all sections
            pass
        elif choice in (2, 8):
            # Separator -treat as exit
            print_info("退出。准备好后运行 'km setup'。")
            return
        elif choice == 9:
            print_info("退出。准备好后运行 'km setup'。")
            return
        elif 3 <= choice <= 7:
            # Individual section -map by key, not by position.
            # SETUP_SECTIONS includes TTS but the returning-user menu skips it,
            # so positional indexing (choice - 3) would dispatch the wrong section.
            section_key = RETURNING_USER_MENU_SECTION_KEYS[choice - 3]
            section = next((s for s in SETUP_SECTIONS if s[0] == section_key), None)
            if section:
                _, label, func = section
                func(config)
                save_config(config)
                _print_setup_summary(config, kunming_home)
            return
    else:
        # -- First-Time Setup --
        print()

        setup_mode = prompt_choice("你想如何设置 Kunming？", [
            "快速设置 -提供商、模型和消息（推荐）",
            "完整设置 -配置所有内容",
        ], 0)

        if setup_mode == 0:
            _run_first_time_quick_setup(config, kunming_home, is_existing)
            return

    # -- Full Setup -run all sections --
    print_header("配置文件位置")
    print_info(f"配置文件:  {get_config_path()}")
    print_info(f"密钥文件: {get_env_path()}")
    print_info(f"数据目录:  {kunming_home}")
    print_info(f"安装目录:  {PROJECT_ROOT}")
    print()
    print_info("你可以直接编辑这些文件，或使用 'km config edit'")

    # Section 1: Model & Provider
    setup_model_provider(config)

    # Section 2: Terminal Backend
    setup_terminal_backend(config)

    # Section 3: Agent Settings
    setup_agent_settings(config)

    # Section 4: Messaging Platforms
    setup_gateway(config)

    # Section 5: Tools
    setup_tools(config, first_install=not is_existing)

    # Save and show summary
    save_config(config)
    _print_setup_summary(config, kunming_home)

    _offer_launch_chat()


def _offer_launch_chat():
    """Prompt the user to jump straight into chat after setup."""
    print()
    if prompt_yes_no("现在启动 km 对话？", True):
        from kunming_cli.main import cmd_chat
        from types import SimpleNamespace
        cmd_chat(SimpleNamespace(
            query=None, resume=None, continue_last=None, model=None,
            provider=None, effort=None, skin=None, oneshot=False,
            quiet=False, verbose=False, toolsets=None, skills=None,
            yolo=False, source=None, worktree=False, checkpoints=False,
            pass_session_id=False, max_turns=None,
        ))


def _run_first_time_quick_setup(config: dict, kunming_home, is_existing: bool):
    """Streamlined first-time setup: provider + model only.

    Applies sensible defaults for TTS (Edge), terminal (local), agent
    settings, and tools -the user can customize later via
    ``km setup <section>``.
    """
    # Step 1: Model & Provider (essential -skips rotation/vision/TTS)
    setup_model_provider(config, quick=True)

    # Step 2: Apply defaults for everything else
    _apply_default_agent_settings(config)
    config.setdefault("terminal", {}).setdefault("backend", "local")

    save_config(config)

    # Step 3: Offer messaging gateway setup
    print()
    gateway_choice = prompt_choice(
        "连接消息平台？（Telegram、Discord 等）",
        [
            "现在设置消息平台（推荐）",
            "跳过 -稍后使用 'km setup gateway' 设置",
        ],
        0,
    )

    if gateway_choice == 0:
        setup_gateway(config)
        save_config(config)

    print()
    print_success("设置完成！你可以开始使用了。")
    print()
    print_info("  配置所有设置:    km setup")
    if gateway_choice != 0:
        print_info("  连接 Telegram/Discord:  km setup gateway")
    print()

    _print_setup_summary(config, kunming_home)

    _offer_launch_chat()


def _run_quick_setup(config: dict, kunming_home):
    """Quick setup -only configure items that are missing."""
    from kunming_cli.config import (
        get_missing_env_vars,
        get_missing_config_fields,
        check_config_version,
    )

    print()
    print_header("快速设置 -仅配置缺少的项目")

    # Check what's missing
    missing_required = [
        v for v in get_missing_env_vars(required_only=False) if v.get("is_required")
    ]
    missing_optional = [
        v for v in get_missing_env_vars(required_only=False) if not v.get("is_required")
    ]
    missing_config = get_missing_config_fields()
    current_ver, latest_ver = check_config_version()

    has_anything_missing = (
        missing_required
        or missing_optional
        or missing_config
        or current_ver < latest_ver
    )

    if not has_anything_missing:
        print_success("所有项目已配置！无需操作。")
        print()
        print_info("运行 'km setup' 并选择'完整设置'来重新配置，")
        print_info("或从菜单中选择特定区段。")
        return

    # Handle missing required env vars
    if missing_required:
        print()
        print_info(f"{len(missing_required)} 个必需设置缺失：")
        for var in missing_required:
            print(f"     -{var['name']}")
        print()

        for var in missing_required:
            print()
            print(color(f"  {var['name']}", Colors.CYAN))
            print_info(f"  {var.get('description', '')}")
            if var.get("url"):
                print_info(f"  获取密钥: {var['url']}")

            if var.get("password"):
                value = prompt(f"  {var.get('prompt', var['name'])}", password=True)
            else:
                value = prompt(f"  {var.get('prompt', var['name'])}")

            if value:
                save_env_value(var["name"], value)
                print_success(f"  已保存 {var['name']}")
            else:
                print_warning(f"  已跳过 {var['name']}")

    # Split missing optional vars by category
    missing_tools = [v for v in missing_optional if v.get("category") == "tool"]
    missing_messaging = [
        v
        for v in missing_optional
        if v.get("category") == "messaging" and not v.get("advanced")
    ]

    # -- Tool API keys (checklist) --
    if missing_tools:
        print()
        print_header("工具 API 密钥")

        checklist_labels = []
        for var in missing_tools:
            tools = var.get("tools", [])
            tools_str = f" ->{', '.join(tools[:2])}" if tools else ""
            checklist_labels.append(f"{var.get('description', var['name'])}{tools_str}")

        selected_indices = prompt_checklist(
            "你想配置哪些工具？",
            checklist_labels,
        )

        for idx in selected_indices:
            var = missing_tools[idx]
            _prompt_api_key(var)

    # -- Messaging platforms (checklist then prompt for selected) --
    if missing_messaging:
        print()
        print_header("消息平台")
        print_info("连接 Kunming 到消息应用，随时随地对话。")
        print_info("你可以稍后使用 'km setup gateway' 配置。")

        # Group by platform (preserving order)
        platform_order = []
        platforms = {}
        for var in missing_messaging:
            name = var["name"]
            if "TELEGRAM" in name:
                plat = "Telegram"
            elif "DISCORD" in name:
                plat = "Discord"
            elif "SLACK" in name:
                plat = "Slack"
            else:
                continue
            if plat not in platforms:
                platform_order.append(plat)
            platforms.setdefault(plat, []).append(var)

        platform_labels = [
            {
                "Telegram": "ð± Telegram",
                "Discord": "ð¬ Discord",
                "Slack": "ð¼ Slack",
            }.get(p, p)
            for p in platform_order
        ]

        selected_indices = prompt_checklist(
            "Which platforms would you like to set up?",
            platform_labels,
        )

        for idx in selected_indices:
            plat = platform_order[idx]
            vars_list = platforms[plat]
            emoji = {"Telegram": "ð±", "Discord": "ð¬", "Slack": "ð¼"}.get(plat, "")
            print()
            print(color(f"  --- {emoji} {plat} ---", Colors.CYAN))
            print()
            for var in vars_list:
                print_info(f"  {var.get('description', '')}")
                if var.get("url"):
                    print_info(f"  {var['url']}")
                if var.get("password"):
                    value = prompt(f"  {var.get('prompt', var['name'])}", password=True)
                else:
                    value = prompt(f"  {var.get('prompt', var['name'])}")
                if value:
                    save_env_value(var["name"], value)
                    print_success("  [OK]Saved")
                else:
                    print_warning("  Skipped")
                print()

    # Handle missing config fields
    if missing_config:
        print()
        print_info(
            f"Adding {len(missing_config)} new config option(s) with defaults..."
        )
        for field in missing_config:
            print_success(f"  Added {field['key']} = {field['default']}")

        # Update config version
        config["_config_version"] = latest_ver
        save_config(config)

    # Jump to summary
    _print_setup_summary(config, kunming_home)
