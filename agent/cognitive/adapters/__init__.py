"""
Cognitive Core Integration Adapters - 优化适配器层

消除重复实现的核心模块，将Cognitive Core的4大系统与Kunming现有能力无缝融合
"""

from .memory_adapter import (
    HybridMemoryProvider,
    HybridSearchResult,
    get_hybrid_memory_provider
)

from .delegate_adapter import (
    SmartDelegator,
    TaskComplexity,
    TaskAnalysis,
    get_smart_delegator
)

from .learning_adapter import (
    UnifiedLearningSystem,
    LearningConfig,
    get_unified_learning
)

__all__ = [
    # Memory Adapter
    'HybridMemoryProvider',
    'HybridSearchResult',
    'get_hybrid_memory_provider',
    
    # Delegate Adapter
    'SmartDelegator',
    'TaskComplexity',
    'TaskAnalysis',
    'get_smart_delegator',
    
    # Learning Adapter
    'UnifiedLearningSystem',
    'LearningConfig',
    'get_unified_learning',
]
