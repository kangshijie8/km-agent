"""
Cognitive Core Integration Adapters - 优化适配器层

消除重复实现的核心模块，将Cognitive Core的4大系统与Kunming现有能力无缝融合
"""

from .delegate_adapter import (
    SmartDelegator,
    TaskComplexity,
    TaskAnalysis,
    get_smart_delegator
)

__all__ = [
    # Delegate Adapter
    'SmartDelegator',
    'TaskComplexity',
    'TaskAnalysis',
    'get_smart_delegator',
]
