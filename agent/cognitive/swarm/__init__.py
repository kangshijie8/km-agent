"""
Cognitive Core Swarm System - Python Implementation

Enterprise-grade swarm coordination with 6 topologies and 5 consensus algorithms.
Provides hive-mind coordination through QueenCoordinator.

This module provides:
- 6 swarm topologies (hierarchical, mesh, centralized, decentralized, hybrid, adaptive)
- 5 consensus algorithms (Raft, Byzantine, Gossip, Paxos, hybrid)
- QueenCoordinator for central orchestration
- Collective intelligence workflows
- Hive mind decision making

Integration with Kunming:
    The swarm system integrates with Kunming's delegate_tool to enable
    true multi-agent coordination. It transforms Kunming from a single
    agent into a coordinated swarm of specialized agents.

Example:
    ```python
    from agent.cognitive.swarm import (
        QueenCoordinator, QueenCoordinatorConfig,
        SwarmConfig, SwarmTopology, ConsensusAlgorithm
    )
    
    # Initialize Queen
    config = QueenCoordinatorConfig(
        swarm_config=SwarmConfig(
            topology=SwarmTopology.HIERARCHICAL,
            consensus_algorithm=ConsensusAlgorithm.RAFT
        )
    )
    queen = QueenCoordinator(config)
    await queen.initialize()
    
    # Register agents
    await queen.register_agent("agent-1", "coder")
    await queen.register_agent("agent-2", "tester")
    
    # Allocate task
    task = await queen.allocate_task("Implement authentication")
    
    # Make hive mind decision
    decision = await queen.hive_mind_decide(
        question="Which architecture pattern?",
        options=["MVC", "MVVM"]
    )
    ```

Based on: @claude-flow/swarm V3.5
"""

# ===== Types =====
from .types import (
    # Enums
    SwarmTopology, ConsensusAlgorithm, SwarmAgentState, MessageType,
    
    # Data Classes
    SwarmAgent, SwarmMessage, TaskAllocation, ConsensusProposal,
    SwarmConfig, SwarmStats, TopologyInfo, ConsensusResult, HiveMindDecision,
    
    # Utilities
    get_topology_description, get_consensus_description,
    is_valid_topology, is_valid_consensus,
    get_all_topologies, get_all_consensus_algorithms,
)

# ===== Queen Coordinator =====
from .queen_coordinator import (
    QueenCoordinator,
    QueenCoordinatorConfig,
)

# ===== Version =====
__version__ = "3.5.0"

# ===== Exports =====
__all__ = [
    # Enums
    "SwarmTopology", "ConsensusAlgorithm", "SwarmAgentState", "MessageType",
    
    # Data Classes
    "SwarmAgent", "SwarmMessage", "TaskAllocation", "ConsensusProposal",
    "SwarmConfig", "SwarmStats", "TopologyInfo", "ConsensusResult", "HiveMindDecision",
    
    # Queen
    "QueenCoordinator", "QueenCoordinatorConfig",
    
    # Utilities
    "get_topology_description", "get_consensus_description",
    "is_valid_topology", "is_valid_consensus",
    "get_all_topologies", "get_all_consensus_algorithms",
]
