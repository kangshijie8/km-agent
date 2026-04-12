"""
Cognitive Core System for Kunming Agent

Enterprise-grade AI agent orchestration system integrating:
- Expert System: 55+ specialized agent types with factory pattern
- Swarm System: 6 topologies + 5 consensus algorithms with Queen coordination
- Learning System: SONA + 9 RL algorithms + ReasoningBank

This integration transforms Kunming from an AI companion into a powerful AI partner
with enterprise-grade multi-agent orchestration capabilities.

Note: Memory system has been migrated to plugins/memory/hnsw_local/

Quick Start:
    ```python
    from agent.cognitive import CognitiveCore
    from plugins.memory.hnsw_local import HnswMemoryPlugin

    # Initialize memory plugin separately
    memory = HnswMemoryPlugin()
    await memory.initialize()

    # Initialize Cognitive Core
    core = CognitiveCore()
    await core.initialize()

    # Use expert system
    agent = await core.experts.spawn_agent(AgentConfig(
        agent_type="coder",
        name="backend-coder"
    ))

    # Use swarm system
    await core.swarm.register_agent("agent-1", "coder")
    task = await core.swarm.allocate_task("Implement authentication")

    # Use learning system
    await core.learning.store_trajectory(trajectory)
    similar = await core.learning.search_similar_trajectories(embedding)

    # Use MCP tools
    # - cognitive_core_delegate: 智能任务委托
    # - cognitive_core_swarm_allocate: 蜂群任务分配
    # - cognitive_core_hive_mind_decide: 集体决策
    # - cognitive_core_create_skill: 创建技能
    ```

Architecture:
    The integration follows a modular design where each system can be used
    independently or together. All systems integrate with Kunming's existing
    infrastructure (AIAgent, delegate_tool, trajectory_compressor).

    Memory system (migrated to plugins/memory/hnsw_local/):
    - HnswMemoryPlugin: Vector-based semantic memory with HNSW indexing

    优化适配器层 (adapters/):
    - HybridMemoryProvider: 结合FTS5和HNSW的混合搜索
    - SmartDelegator: 根据任务复杂度智能选择执行策略
    - UnifiedLearningSystem: 整合skill_manage和SONA

    MCP工具层 (tools/):
    - cognitive_tools.py: MCP工具，统一入口

Based on: @claude-flow V3.5
"""

from typing import Optional
from dataclasses import dataclass

# Import expert system
from .experts import (
    AgentFactory, ExpertAgent, AgentConfig,
    create_agent_factory, list_all_agent_types,
    # Agent types
    CODER, REVIEWER, TESTER, PLANNER, RESEARCHER,
    QUEEN_COORDINATOR, HIERARCHICAL_COORDINATOR, MESH_COORDINATOR,
    BYZANTINE_COORDINATOR, RAFT_MANAGER, GOSSIP_COORDINATOR,
)

# Import swarm system
from .swarm import (
    QueenCoordinator, QueenCoordinatorConfig,
    SwarmConfig, SwarmTopology, ConsensusAlgorithm,
    SwarmAgent, TaskAllocation, HiveMindDecision,
)

# Import learning system
from .neural import (
    ReasoningBank, ReasoningBankConfig,
    ReasoningTrajectory, ReasoningStep,
    RLAlgorithmType, SONAArchitectureType,
    create_reasoning_bank,
)

# Import RL trainer
from .neural.rl_trainer import (
    RLTrainer, QLearningAgent, ExperienceBuffer,
    create_rl_trainer,
)

# Import adapters
from .adapters import (
    HybridMemoryProvider, HybridSearchResult, get_hybrid_memory_provider,
    SmartDelegator, TaskComplexity, TaskAnalysis, get_smart_delegator,
    UnifiedLearningSystem, LearningConfig, get_unified_learning,
)


@dataclass
class CognitiveCoreConfig:
    """Configuration for Cognitive Core integration"""
    experts_enabled: bool = True
    swarm_enabled: bool = True
    learning_enabled: bool = True

    # Subsystem configs
    swarm_config: Optional[QueenCoordinatorConfig] = None
    learning_config: Optional[ReasoningBankConfig] = None

    # Adapter configs
    use_hybrid_memory: bool = True
    use_smart_delegation: bool = True
    use_unified_learning: bool = True


class CognitiveCore:
    """
    Main integration class for Cognitive Core systems.

    Provides unified access to all Cognitive Core systems:
    - experts: AgentFactory for 55+ expert types
    - swarm: QueenCoordinator for multi-agent coordination
    - learning: ReasoningBank for trajectory learning

    Plus optimized adapters:
    - hybrid_memory: HybridMemoryProvider (FTS5 + HNSW)
    - smart_delegator: SmartDelegator (intelligent task routing)
    - unified_learning: UnifiedLearningSystem (skill + SONA)

    Note: Memory system has been migrated to plugins/memory/hnsw_local/

    Example:
        ```python
        core = CognitiveCore()
        await core.initialize()

        # All systems are accessible via attributes
        await core.experts.spawn_agent(...)
        await core.swarm.allocate_task(...)
        await core.learning.store_trajectory(...)

        # Use optimized adapters
        results = await core.hybrid_memory.search("API patterns")
        result = await core.smart_delegator.delegate("Implement auth")
        ```
    """

    def __init__(self, config: Optional[CognitiveCoreConfig] = None):
        """
        Initialize Cognitive Core integration.

        Args:
            config: Integration configuration
        """
        self.config = config or CognitiveCoreConfig()

        # Subsystems (initialized in initialize())
        self._experts: Optional[AgentFactory] = None
        self._swarm: Optional[QueenCoordinator] = None
        self._learning: Optional[ReasoningBank] = None

        # Optimized adapters
        self._hybrid_memory: Optional[HybridMemoryProvider] = None
        self._smart_delegator: Optional[SmartDelegator] = None
        self._unified_learning: Optional[UnifiedLearningSystem] = None

        self._initialized = False

    async def initialize(self) -> None:
        """Initialize all enabled subsystems and adapters"""
        if self._initialized:
            return

        # Initialize expert system
        if self.config.experts_enabled:
            from .experts import AgentFactory
            self._experts = AgentFactory()
            await self._experts.initialize()

        # Initialize swarm system
        if self.config.swarm_enabled:
            from .swarm import QueenCoordinator
            self._swarm = QueenCoordinator(self.config.swarm_config)
            await self._swarm.initialize()

        # Initialize learning system
        if self.config.learning_enabled:
            from .neural import ReasoningBank
            self._learning = ReasoningBank(self.config.learning_config)
            await self._learning.initialize()

        # Initialize optimized adapters
        if self.config.use_hybrid_memory:
            self._hybrid_memory = get_hybrid_memory_provider()
            await self._hybrid_memory.initialize()

        if self.config.use_smart_delegation:
            self._smart_delegator = get_smart_delegator()
            await self._smart_delegator.initialize()

        if self.config.use_unified_learning:
            self._unified_learning = get_unified_learning()
            await self._unified_learning.initialize()

        self._initialized = True

    async def shutdown(self) -> None:
        """Shutdown all subsystems"""
        if self._learning:
            await self._learning.shutdown()

        if self._swarm:
            await self._swarm.shutdown()

        if self._experts:
            await self._experts.shutdown()

        self._initialized = False

    @property
    def experts(self) -> AgentFactory:
        """Access expert system"""
        if not self._experts:
            raise RuntimeError("Expert system not enabled")
        return self._experts

    @property
    def swarm(self) -> QueenCoordinator:
        """Access swarm system"""
        if not self._swarm:
            raise RuntimeError("Swarm system not enabled")
        return self._swarm

    @property
    def learning(self) -> ReasoningBank:
        """Access learning system"""
        if not self._learning:
            raise RuntimeError("Learning system not enabled")
        return self._learning

    @property
    def hybrid_memory(self) -> HybridMemoryProvider:
        """Access hybrid memory provider (optimized adapter)"""
        if not self._hybrid_memory:
            raise RuntimeError("Hybrid memory not enabled")
        return self._hybrid_memory

    @property
    def smart_delegator(self) -> SmartDelegator:
        """Access smart delegator (optimized adapter)"""
        if not self._smart_delegator:
            raise RuntimeError("Smart delegator not enabled")
        return self._smart_delegator

    @property
    def unified_learning(self) -> UnifiedLearningSystem:
        """Access unified learning system (optimized adapter)"""
        if not self._unified_learning:
            raise RuntimeError("Unified learning not enabled")
        return self._unified_learning

    async def get_stats(self) -> dict:
        """Get statistics from all subsystems"""
        stats = {
            "initialized": self._initialized,
            "subsystems": {},
            "adapters": {}
        }

        if self._experts:
            exp_stats = await self._experts.get_factory_stats()
            stats["subsystems"]["experts"] = exp_stats

        if self._swarm:
            swarm_stats = await self._swarm.get_stats()
            stats["subsystems"]["swarm"] = swarm_stats.__dict__

        if self._learning:
            learning_stats = await self._learning.get_statistics()
            stats["subsystems"]["learning"] = learning_stats

        # Adapter stats
        if self._hybrid_memory:
            stats["adapters"]["hybrid_memory"] = {"initialized": True}

        if self._smart_delegator:
            stats["adapters"]["smart_delegator"] = {"initialized": True}

        if self._unified_learning:
            stats["adapters"]["unified_learning"] = {"initialized": True}

        return stats


# ===== Factory Functions =====

def create_cognitive(
    experts: bool = True,
    swarm: bool = True,
    learning: bool = True,
    use_adapters: bool = True
) -> CognitiveCore:
    """
    Create Cognitive Core integration with specified subsystems.

    Args:
        experts: Enable expert system
        swarm: Enable swarm system
        learning: Enable learning system
        use_adapters: Enable optimized adapters

    Returns:
        CognitiveCore instance
    """
    config = CognitiveCoreConfig(
        experts_enabled=experts,
        swarm_enabled=swarm,
        learning_enabled=learning,
        use_hybrid_memory=use_adapters,
        use_smart_delegation=use_adapters,
        use_unified_learning=use_adapters
    )
    return CognitiveCore(config)


# ===== MCP Tools Import =====
# 自动导入MCP工具（在模块加载时注册）
try:
    from .tools import cognitive_tools
except ImportError:
    pass  # 工具导入失败不影响核心功能


# ===== Version =====
__version__ = "3.5.0-kunming"

# ===== Exports =====
__all__ = [
    # Main integration
    "CognitiveCore", "CognitiveCoreConfig", "create_cognitive",

    # Expert system
    "AgentFactory", "ExpertAgent", "AgentConfig",
    "create_agent_factory", "list_all_agent_types",
    "CODER", "REVIEWER", "TESTER", "PLANNER", "RESEARCHER",
    "QUEEN_COORDINATOR", "HIERARCHICAL_COORDINATOR", "MESH_COORDINATOR",
    "BYZANTINE_COORDINATOR", "RAFT_MANAGER", "GOSSIP_COORDINATOR",

    # Swarm system
    "QueenCoordinator", "QueenCoordinatorConfig",
    "SwarmConfig", "SwarmTopology", "ConsensusAlgorithm",
    "SwarmAgent", "TaskAllocation", "HiveMindDecision",

    # Learning system
    "ReasoningBank", "ReasoningBankConfig",
    "ReasoningTrajectory", "ReasoningStep",
    "RLAlgorithmType", "SONAArchitectureType",
    "create_reasoning_bank",

    # RL trainer
    "RLTrainer", "QLearningAgent", "ExperienceBuffer",
    "create_rl_trainer",

    # Optimized adapters
    "HybridMemoryProvider", "HybridSearchResult", "get_hybrid_memory_provider",
    "SmartDelegator", "TaskComplexity", "TaskAnalysis", "get_smart_delegator",
    "UnifiedLearningSystem", "LearningConfig", "get_unified_learning",
]
