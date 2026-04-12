"""
Cognitive Core System for Kunming Agent

Enterprise-grade AI agent orchestration system integrating:
- Memory System: HNSW vector indexing for 150x-12,500x faster semantic search
- Expert System: 55+ specialized agent types with factory pattern
- Swarm System: 6 topologies + 5 consensus algorithms with Queen coordination
- Learning System: SONA + 9 RL algorithms + ReasoningBank

This integration transforms Kunming from an AI companion into a powerful AI partner
with enterprise-grade multi-agent orchestration capabilities.

Quick Start:
    ```python
    from agent.cognitive import CognitiveCore
    
    # Initialize
    Cognitive Core = CognitiveCore()
    await Cognitive Core.initialize()
    
    # Use memory system
    entry = await Cognitive Core.memory.store_entry({
        "key": "api-pattern",
        "content": "REST API design patterns",
        "tags": ["api", "design"]
    })
    
    # Use expert system
    agent = await Cognitive Core.experts.spawn_agent(AgentConfig(
        agent_type="coder",
        name="backend-coder"
    ))
    
    # Use swarm system
    await Cognitive Core.swarm.register_agent("agent-1", "coder")
    task = await Cognitive Core.swarm.allocate_task("Implement authentication")
    
    # Use learning system
    await Cognitive Core.learning.store_trajectory(trajectory)
    similar = await Cognitive Core.learning.search_similar_trajectories(embedding)
    
    # Use MCP tools
    # - cognitive_memory_search: 混合记忆搜索
    # - Cognitive Core_delegate: 智能任务委托
    # - Cognitive Core_swarm_allocate: 蜂群任务分配
    # - Cognitive Core_hive_mind_decide: 集体决策
    # - Cognitive Core_create_skill: 创建技能
    ```

Architecture:
    The integration follows a modular design where each system can be used
    independently or together. All systems integrate with Kunming' existing
    infrastructure (MemoryManager, AIAgent, delegate_tool, trajectory_compressor).

    优化适配器层 (adapters/):
    - HybridMemoryProvider: 结合FTS5和HNSW的混合搜索
    - SmartDelegator: 根据任务复杂度智能选择执行策略
    - UnifiedLearningSystem: 整合skill_manage和SONA

    MCP工具层 (tools/):
    - cognitive_tools.py: 12个MCP工具，统一入口

Based on: @claude-flow V3.5
"""

from typing import Optional
from dataclasses import dataclass

# Import all subsystems (absolute imports for standalone execution)
from agent.cognitive.memory import (
    UnifiedMemoryService, UnifiedMemoryServiceConfig,
    MemoryEntry, MemoryEntryInput, MemoryQuery,
    HnswLite, SearchResult,
    create_in_memory_service, create_persistent_service,
)

from agent.cognitive.experts import (
    AgentFactory, ExpertAgent, AgentConfig,
    create_agent_factory, list_all_agent_types,
    # Agent types
    CODER, REVIEWER, TESTER, PLANNER, RESEARCHER,
    QUEEN_COORDINATOR, HIERARCHICAL_COORDINATOR, MESH_COORDINATOR,
    BYZANTINE_COORDINATOR, RAFT_MANAGER, GOSSIP_COORDINATOR,
)

from agent.cognitive.swarm import (
    QueenCoordinator, QueenCoordinatorConfig,
    SwarmConfig, SwarmTopology, ConsensusAlgorithm,
    SwarmAgent, TaskAllocation, HiveMindDecision,
)

from agent.cognitive.neural import (
    ReasoningBank, ReasoningBankConfig,
    ReasoningTrajectory, ReasoningStep,
    RLAlgorithmType, SONAArchitectureType,
    create_reasoning_bank,
)

# Import adapters
from agent.cognitive.adapters import (
    HybridMemoryProvider, HybridSearchResult, get_hybrid_memory_provider,
    SmartDelegator, TaskComplexity, TaskAnalysis, get_smart_delegator,
    UnifiedLearningSystem, LearningConfig, get_unified_learning,
)


@dataclass
class CognitiveCoreConfig:
    """Configuration for Cognitive Core integration"""
    memory_enabled: bool = True
    experts_enabled: bool = True
    swarm_enabled: bool = True
    learning_enabled: bool = True
    
    # Subsystem configs
    memory_config: Optional[UnifiedMemoryServiceConfig] = None
    swarm_config: Optional[QueenCoordinatorConfig] = None
    learning_config: Optional[ReasoningBankConfig] = None
    
    # Adapter configs
    use_hybrid_memory: bool = True
    use_smart_delegation: bool = True
    use_unified_learning: bool = True


class CognitiveCore:
    """
    Main integration class for Cognitive Core systems.
    
    Provides unified access to all four Cognitive Core systems:
    - memory: UnifiedMemoryService for semantic memory
    - experts: AgentFactory for 55+ expert types
    - swarm: QueenCoordinator for multi-agent coordination
    - learning: ReasoningBank for trajectory learning
    
    Plus optimized adapters:
    - hybrid_memory: HybridMemoryProvider (FTS5 + HNSW)
    - smart_delegator: SmartDelegator (intelligent task routing)
    - unified_learning: UnifiedLearningSystem (skill + SONA)
    
    Example:
        ```python
        Cognitive Core = CognitiveCore()
        await Cognitive Core.initialize()
        
        # All systems are accessible via attributes
        await Cognitive Core.memory.store_entry(...)
        await Cognitive Core.experts.spawn_agent(...)
        await Cognitive Core.swarm.allocate_task(...)
        await Cognitive Core.learning.store_trajectory(...)
        
        # Use optimized adapters
        results = await Cognitive Core.hybrid_memory.search("API patterns")
        result = await Cognitive Core.smart_delegator.delegate("Implement auth")
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
        self._memory: Optional[UnifiedMemoryService] = None
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
        
        # Initialize memory system
        if self.config.memory_enabled:
            from agent.cognitive.memory import UnifiedMemoryService
            self._memory = UnifiedMemoryService(self.config.memory_config)
            await self._memory.initialize()
        
        # Initialize expert system
        if self.config.experts_enabled:
            from agent.cognitive.experts import AgentFactory
            self._experts = AgentFactory()
            await self._experts.initialize()
        
        # Initialize swarm system
        if self.config.swarm_enabled:
            from agent.cognitive.swarm import QueenCoordinator
            self._swarm = QueenCoordinator(self.config.swarm_config)
            await self._swarm.initialize()
        
        # Initialize learning system
        if self.config.learning_enabled:
            from agent.cognitive.neural import ReasoningBank
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
        
        if self._memory:
            await self._memory.shutdown()
        
        self._initialized = False
    
    @property
    def memory(self) -> UnifiedMemoryService:
        """Access memory system"""
        if not self._memory:
            raise RuntimeError("Memory system not enabled")
        return self._memory
    
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
        
        if self._memory:
            mem_stats = await self._memory.get_stats()
            stats["subsystems"]["memory"] = {
                "total_entries": mem_stats.total_entries,
                "total_namespaces": mem_stats.total_namespaces,
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
    memory: bool = True,
    experts: bool = True,
    swarm: bool = True,
    learning: bool = True,
    use_adapters: bool = True
) -> CognitiveCore:
    """
    Create Cognitive Core integration with specified subsystems.
    
    Args:
        memory: Enable memory system
        experts: Enable expert system
        swarm: Enable swarm system
        learning: Enable learning system
        use_adapters: Enable optimized adapters
        
    Returns:
        CognitiveCore instance
    """
    config = CognitiveCoreConfig(
        memory_enabled=memory,
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
    from agent.cognitive.tools import cognitive_tools
except ImportError:
    pass  # tools import failure doesn't affect core functionality


# ===== Version =====
__version__ = "3.5.0-kunming"

# ===== Exports =====
__all__ = [
    # Main integration
    "CognitiveCore", "CognitiveCoreConfig", "create_cognitive",
    
    # Memory system
    "UnifiedMemoryService", "UnifiedMemoryServiceConfig",
    "MemoryEntry", "MemoryEntryInput", "MemoryQuery",
    "HnswLite", "SearchResult",
    "create_in_memory_service", "create_persistent_service",
    
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
    
    # Optimized adapters
    "HybridMemoryProvider", "HybridSearchResult", "get_hybrid_memory_provider",
    "SmartDelegator", "TaskComplexity", "TaskAnalysis", "get_smart_delegator",
    "UnifiedLearningSystem", "LearningConfig", "get_unified_learning",
]


# ============================================================
# Initialization Entry Point
# ============================================================

async def initialize_cognitive() -> None:
    """Initialize all Cognitive Core subsystems."""
    print("=" * 60)
    print("=                                                       =")
    print("  Cognitive Core System Initialization                    ")
    print("=                                                       =")
    print("=" * 60)
    print()
    
    try:
        core = CognitiveCore()
        await core.initialize()
        
        print()
        print("=" * 60)
        print(f"  All systems initialized successfully!              ")
        print(f"  Memory: {core.memory is not None}                 ")
        print(f"  Experts: {core.experts is not None}               ")
        print(f"  Swarm: {core.swarm is not None}                   ")
        print(f"  Learning: {core.learning is not None}             ")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n  Initialization failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    import asyncio
    asyncio.run(initialize_cognitive())
