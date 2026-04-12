"""
Cognitive Core Swarm System Types - Python Implementation

Type definitions for swarm coordination with 6 topologies and 5 consensus algorithms.
Provides hive-mind coordination through QueenCoordinator.

Based on: @claude-flow/swarm/src/index.ts
"""

from typing import Dict, List, Optional, Any, Callable, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto


# ===== Topology Types =====

class SwarmTopology(Enum):
    """Swarm network topology types"""
    HIERARCHICAL = "hierarchical"      # Tree-like structure with Queen at root
    MESH = "mesh"                      # Fully connected mesh network
    CENTRALIZED = "centralized"        # Star topology with central coordinator
    DECENTRALIZED = "decentralized"    # Peer-to-peer without central authority
    HYBRID = "hybrid"                  # Combination of multiple topologies
    ADAPTIVE = "adaptive"              # Dynamically adjusts based on workload


# ===== Consensus Algorithms =====

class ConsensusAlgorithm(Enum):
    """Distributed consensus algorithms"""
    RAFT = "raft"                      # Raft consensus for leader election
    BYZANTINE = "byzantine"            # Byzantine fault tolerance
    GOSSIP = "gossip"                  # Gossip protocol for information spread
    PAXOS = "paxos"                    # Paxos consensus algorithm
    HYBRID_CONSENSUS = "hybrid"        # Hybrid consensus combining multiple


# ===== Agent States =====

class SwarmAgentState(Enum):
    """Agent states in swarm"""
    IDLE = "idle"
    ACTIVE = "active"
    BUSY = "busy"
    OFFLINE = "offline"
    RECOVERING = "recovering"
    TERMINATED = "terminated"


# ===== Message Types =====

class MessageType(Enum):
    """Types of swarm messages"""
    TASK_ASSIGNMENT = "task:assignment"
    TASK_RESULT = "task:result"
    TASK_FAILED = "task:failed"
    HEARTBEAT = "heartbeat"
    CONSENSUS_PROPOSE = "consensus:propose"
    CONSENSUS_VOTE = "consensus:vote"
    CONSENSUS_COMMIT = "consensus:commit"
    STATE_SYNC = "state:sync"
    AGENT_JOIN = "agent:join"
    AGENT_LEAVE = "agent:leave"
    ERROR = "error"


# ===== Data Classes =====

@dataclass
class SwarmAgent:
    """Agent in the swarm"""
    id: str
    agent_type: str
    state: SwarmAgentState = SwarmAgentState.IDLE
    capabilities: List[str] = field(default_factory=list)
    load: float = 0.0  # 0.0 - 1.0
    last_heartbeat: float = field(default_factory=lambda: datetime.now().timestamp())
    joined_at: float = field(default_factory=lambda: datetime.now().timestamp())
    metadata: Dict[str, Any] = field(default_factory=dict)
    parent_id: Optional[str] = None  # For hierarchical topology
    children_ids: List[str] = field(default_factory=list)
    neighbors: List[str] = field(default_factory=list)  # For mesh topology


@dataclass
class SwarmMessage:
    """Message in swarm communication"""
    id: str
    type: MessageType
    sender_id: str
    recipient_id: Optional[str]  # None for broadcast
    payload: Dict[str, Any]
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    ttl: int = 10  # Time to live (hops)


@dataclass
class ConsensusProposal:
    """Consensus proposal"""
    id: str
    algorithm: ConsensusAlgorithm
    proposed_by: str
    value: Any
    timestamp: float
    votes: Dict[str, bool] = field(default_factory=dict)
    status: str = "pending"  # pending, accepted, rejected


@dataclass
class TaskAllocation:
    """Task allocation in swarm"""
    task_id: str
    goal: str
    assigned_to: Optional[str] = None
    assigned_by: Optional[str] = None
    priority: str = "normal"  # low, normal, high, critical
    status: str = "pending"  # pending, assigned, in_progress, completed, failed
    created_at: float = field(default_factory=lambda: datetime.now().timestamp())
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[Any] = None
    error: Optional[str] = None


@dataclass
class SwarmConfig:
    """Configuration for swarm"""
    topology: SwarmTopology = SwarmTopology.HIERARCHICAL
    consensus_algorithm: ConsensusAlgorithm = ConsensusAlgorithm.RAFT
    max_agents: int = 100
    heartbeat_interval: float = 30.0
    consensus_timeout: float = 60.0
    task_timeout: float = 300.0
    auto_scale: bool = True
    fault_tolerance: bool = True
    enable_consensus: bool = True


@dataclass
class SwarmStats:
    """Swarm statistics"""
    total_agents: int = 0
    active_agents: int = 0
    idle_agents: int = 0
    busy_agents: int = 0
    offline_agents: int = 0
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    pending_tasks: int = 0
    consensus_rounds: int = 0
    messages_sent: int = 0
    messages_received: int = 0


@dataclass
class TopologyInfo:
    """Information about swarm topology"""
    type: SwarmTopology
    depth: int = 0  # For hierarchical
    diameter: int = 0  # For mesh
    central_nodes: List[str] = field(default_factory=list)
    edge_nodes: List[str] = field(default_factory=list)


@dataclass
class ConsensusResult:
    """Result of consensus round"""
    success: bool
    algorithm: ConsensusAlgorithm
    proposal_id: str
    value: Any
    votes_for: int = 0
    votes_against: int = 0
    duration_ms: float = 0.0
    error: Optional[str] = None


@dataclass
class HiveMindDecision:
    """Decision made by hive mind"""
    id: str
    decision: str
    confidence: float  # 0.0 - 1.0
    participating_agents: List[str]
    consensus_reached: bool
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    metadata: Dict[str, Any] = field(default_factory=dict)


# ===== Topology Functions =====

def get_topology_description(topology: SwarmTopology) -> str:
    """Get description for topology"""
    descriptions = {
        SwarmTopology.HIERARCHICAL: "Tree-like structure with Queen at root",
        SwarmTopology.MESH: "Fully connected mesh network",
        SwarmTopology.CENTRALIZED: "Star topology with central coordinator",
        SwarmTopology.DECENTRALIZED: "Peer-to-peer without central authority",
        SwarmTopology.HYBRID: "Combination of multiple topologies",
        SwarmTopology.ADAPTIVE: "Dynamically adjusts based on workload",
    }
    return descriptions.get(topology, "Unknown topology")


def get_consensus_description(algorithm: ConsensusAlgorithm) -> str:
    """Get description for consensus algorithm"""
    descriptions = {
        ConsensusAlgorithm.RAFT: "Raft consensus for leader election and log replication",
        ConsensusAlgorithm.BYZANTINE: "Byzantine fault tolerance for malicious agents",
        ConsensusAlgorithm.GOSSIP: "Gossip protocol for eventual consistency",
        ConsensusAlgorithm.PAXOS: "Paxos consensus for distributed agreement",
        ConsensusAlgorithm.HYBRID_CONSENSUS: "Hybrid combining multiple algorithms",
    }
    return descriptions.get(algorithm, "Unknown algorithm")


def is_valid_topology(topology: str) -> bool:
    """Check if topology is valid"""
    try:
        SwarmTopology(topology)
        return True
    except ValueError:
        return False


def is_valid_consensus(algorithm: str) -> bool:
    """Check if consensus algorithm is valid"""
    try:
        ConsensusAlgorithm(algorithm)
        return True
    except ValueError:
        return False


def get_all_topologies() -> List[SwarmTopology]:
    """Get all available topologies"""
    return list(SwarmTopology)


def get_all_consensus_algorithms() -> List[ConsensusAlgorithm]:
    """Get all available consensus algorithms"""
    return list(ConsensusAlgorithm)
