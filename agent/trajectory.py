"""Trajectory saving utilities and static helpers.

_convert_to_trajectory_format stays as an AIAgent method (batch_runner.py
calls agent._convert_to_trajectory_format). Only the static helpers and
the file-write logic live here.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from kunming_constants import get_kunming_home

logger = logging.getLogger(__name__)


# [优化: 消除重复标签检查逻辑] 提取公共的REASONING_SCRATCHPAD标签检查
# 原因：原代码中两个函数都重复检查了"<REASONING_SCRATCHPAD>" in content
# 修复方案：使用统一的标签常量，并提取公共检查逻辑

_SCRATCHPAD_OPEN_TAG = "<REASONING_SCRATCHPAD>"
_SCRATCHPAD_CLOSE_TAG = "</REASONING_SCRATCHPAD>"
_THINK_OPEN_TAG = "<think>"
_THINK_CLOSE_TAG = "</think>"


def _has_scratchpad_tag(content: str) -> bool:
    """Check if content contains REASONING_SCRATCHPAD open tag."""
    return bool(content) and _SCRATCHPAD_OPEN_TAG in content


def convert_scratchpad_to_think(content: str) -> str:
    """Convert <REASONING_SCRATCHPAD> tags to <think> tags."""
    # [修复] 使用统一的标签检查函数，避免重复逻辑
    if not _has_scratchpad_tag(content):
        return content
    return content.replace(_SCRATCHPAD_OPEN_TAG, _THINK_OPEN_TAG).replace(_SCRATCHPAD_CLOSE_TAG, _THINK_CLOSE_TAG)


def has_incomplete_scratchpad(content: str) -> bool:
    """Check if content has an opening <REASONING_SCRATCHPAD> without a closing tag."""
    # [修复] 使用统一的标签检查函数，避免重复逻辑
    if not _has_scratchpad_tag(content):
        return False
    return _SCRATCHPAD_CLOSE_TAG not in content


def save_trajectory(trajectory: List[Dict[str, Any]], model: str,
                    completed: bool, filename: str = None):
    """Append a trajectory entry to a JSONL file.

    Args:
        trajectory: The ShareGPT-format conversation list.
        model: Model name for metadata.
        completed: Whether the conversation completed successfully.
        filename: Override output filename. Defaults to trajectory_samples.jsonl
                  or failed_trajectories.jsonl based on ``completed``.
    """
    if filename is None:
        filename = "trajectory_samples.jsonl" if completed else "failed_trajectories.jsonl"

    filepath = Path(filename)
    if not filepath.is_absolute():
        filepath = get_kunming_home() / filepath

    entry = {
        "conversations": trajectory,
        "timestamp": datetime.now().isoformat(),
        "model": model,
        "completed": completed,
    }

    try:
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        logger.info("Trajectory saved to %s", filepath)
    except Exception as e:
        logger.warning("Failed to save trajectory: %s", e)
