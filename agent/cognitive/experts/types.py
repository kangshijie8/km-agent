"""
Cognitive Core Expert Agent Types - Python Implementation

Type definitions for the expert agent system with 55+ specialized agent types.
Provides factory pattern for agent creation and lifecycle management.

Based on: @claude-flow/swarm and mcp/tools/agent-tools.ts
"""

from typing import Dict, List, Optional, Any, Callable, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto


# ===== Agent Type Classification =====

class AgentCategory(Enum):
    """Categories of expert agents"""
    CORE_DEVELOPMENT = "core_development"
    SWARM_COORDINATION = "swarm_coordination"
    CONSENSUS_DISTRIBUTED = "consensus_distributed"
    PERFORMANCE_OPTIMIZATION = "performance_optimization"
    SPARC_METHODOLOGY = "sparc_methodology"
    SPECIALIZED_DEVELOPMENT = "specialized_development"
    V3_SPECIALIZED = "v3_specialized"


# ===== 55 Expert Agent Types =====

# Core Development Agents
CODER = "coder"
REVIEWER = "reviewer"
TESTER = "tester"
PLANNER = "planner"
RESEARCHER = "researcher"

# Swarm Coordination Agents
HIERARCHICAL_COORDINATOR = "hierarchical-coordinator"
MESH_COORDINATOR = "mesh-coordinator"
ADAPTIVE_COORDINATOR = "adaptive-coordinator"
COLLECTIVE_INTELLIGENCE_COORDINATOR = "collective-intelligence-coordinator"
SWARM_MEMORY_MANAGER = "swarm-memory-manager"

# Consensus & Distributed Agents
BYZANTINE_COORDINATOR = "byzantine-coordinator"
RAFT_MANAGER = "raft-manager"
GOSSIP_COORDINATOR = "gossip-coordinator"
CONSENSUS_BUILDER = "consensus-builder"
CRDT_SYNCHRONIZER = "crdt-synchronizer"
QUORUM_MANAGER = "quorum-manager"
SECURITY_MANAGER = "security-manager"

# Performance & Optimization Agents
PERF_ANALYZER = "perf-analyzer"
PERFORMANCE_BENCHMARKER = "performance-benchmarker"
TASK_ORCHESTRATOR = "task-orchestrator"
MEMORY_COORDINATOR = "memory-coordinator"
SMART_AGENT = "smart-agent"

# SPARC Methodology Agents
SPARC_COORD = "sparc-coord"
SPARC_CODER = "sparc-coder"
SPECIFICATION = "specification"
PSEUDOCODE = "pseudocode"
ARCHITECTURE = "architecture"
REFINEMENT = "refinement"

# Specialized Development Agents
BACKEND_DEV = "backend-dev"
FRONTEND_DEV = "frontend-dev"
MOBILE_DEV = "mobile-dev"
ML_DEVELOPER = "ml-developer"
CICD_ENGINEER = "cicd-engineer"
API_DOCS = "api-docs"
SYSTEM_ARCHITECT = "system-architect"
CODE_ANALYZER = "code-analyzer"

# V3 Specialized Agents
QUEEN_COORDINATOR = "queen-coordinator"
SECURITY_ARCHITECT = "security-architect"
SECURITY_AUDITOR = "security-auditor"
MEMORY_SPECIALIST = "memory-specialist"
SWARM_SPECIALIST = "swarm-specialist"
INTEGRATION_ARCHITECT = "integration-architect"
PERFORMANCE_ENGINEER = "performance-engineer"
CORE_ARCHITECT = "core-architect"
TEST_ARCHITECT = "test-architect"
PROJECT_COORDINATOR = "project-coordinator"


# All 55 agent types
ALL_AGENT_TYPES = [
    # Core Development (5)
    CODER, REVIEWER, TESTER, PLANNER, RESEARCHER,
    
    # Swarm Coordination (5)
    HIERARCHICAL_COORDINATOR, MESH_COORDINATOR, ADAPTIVE_COORDINATOR,
    COLLECTIVE_INTELLIGENCE_COORDINATOR, SWARM_MEMORY_MANAGER,
    
    # Consensus & Distributed (7)
    BYZANTINE_COORDINATOR, RAFT_MANAGER, GOSSIP_COORDINATOR,
    CONSENSUS_BUILDER, CRDT_SYNCHRONIZER, QUORUM_MANAGER, SECURITY_MANAGER,
    
    # Performance & Optimization (5)
    PERF_ANALYZER, PERFORMANCE_BENCHMARKER, TASK_ORCHESTRATOR,
    MEMORY_COORDINATOR, SMART_AGENT,
    
    # SPARC Methodology (6)
    SPARC_COORD, SPARC_CODER, SPECIFICATION, PSEUDOCODE, ARCHITECTURE, REFINEMENT,
    
    # Specialized Development (8)
    BACKEND_DEV, FRONTEND_DEV, MOBILE_DEV, ML_DEVELOPER, CICD_ENGINEER,
    API_DOCS, SYSTEM_ARCHITECT, CODE_ANALYZER,
    
    # V3 Specialized (10)
    QUEEN_COORDINATOR, SECURITY_ARCHITECT, SECURITY_AUDITOR, MEMORY_SPECIALIST,
    SWARM_SPECIALIST, INTEGRATION_ARCHITECT, PERFORMANCE_ENGINEER, CORE_ARCHITECT,
    TEST_ARCHITECT, PROJECT_COORDINATOR,
]


# Agent type to category mapping
AGENT_CATEGORIES: Dict[str, AgentCategory] = {
    # Core Development
    CODER: AgentCategory.CORE_DEVELOPMENT,
    REVIEWER: AgentCategory.CORE_DEVELOPMENT,
    TESTER: AgentCategory.CORE_DEVELOPMENT,
    PLANNER: AgentCategory.CORE_DEVELOPMENT,
    RESEARCHER: AgentCategory.CORE_DEVELOPMENT,
    
    # Swarm Coordination
    HIERARCHICAL_COORDINATOR: AgentCategory.SWARM_COORDINATION,
    MESH_COORDINATOR: AgentCategory.SWARM_COORDINATION,
    ADAPTIVE_COORDINATOR: AgentCategory.SWARM_COORDINATION,
    COLLECTIVE_INTELLIGENCE_COORDINATOR: AgentCategory.SWARM_COORDINATION,
    SWARM_MEMORY_MANAGER: AgentCategory.SWARM_COORDINATION,
    
    # Consensus & Distributed
    BYZANTINE_COORDINATOR: AgentCategory.CONSENSUS_DISTRIBUTED,
    RAFT_MANAGER: AgentCategory.CONSENSUS_DISTRIBUTED,
    GOSSIP_COORDINATOR: AgentCategory.CONSENSUS_DISTRIBUTED,
    CONSENSUS_BUILDER: AgentCategory.CONSENSUS_DISTRIBUTED,
    CRDT_SYNCHRONIZER: AgentCategory.CONSENSUS_DISTRIBUTED,
    QUORUM_MANAGER: AgentCategory.CONSENSUS_DISTRIBUTED,
    SECURITY_MANAGER: AgentCategory.CONSENSUS_DISTRIBUTED,
    
    # Performance & Optimization
    PERF_ANALYZER: AgentCategory.PERFORMANCE_OPTIMIZATION,
    PERFORMANCE_BENCHMARKER: AgentCategory.PERFORMANCE_OPTIMIZATION,
    TASK_ORCHESTRATOR: AgentCategory.PERFORMANCE_OPTIMIZATION,
    MEMORY_COORDINATOR: AgentCategory.PERFORMANCE_OPTIMIZATION,
    SMART_AGENT: AgentCategory.PERFORMANCE_OPTIMIZATION,
    
    # SPARC Methodology
    SPARC_COORD: AgentCategory.SPARC_METHODOLOGY,
    SPARC_CODER: AgentCategory.SPARC_METHODOLOGY,
    SPECIFICATION: AgentCategory.SPARC_METHODOLOGY,
    PSEUDOCODE: AgentCategory.SPARC_METHODOLOGY,
    ARCHITECTURE: AgentCategory.SPARC_METHODOLOGY,
    REFINEMENT: AgentCategory.SPARC_METHODOLOGY,
    
    # Specialized Development
    BACKEND_DEV: AgentCategory.SPECIALIZED_DEVELOPMENT,
    FRONTEND_DEV: AgentCategory.SPECIALIZED_DEVELOPMENT,
    MOBILE_DEV: AgentCategory.SPECIALIZED_DEVELOPMENT,
    ML_DEVELOPER: AgentCategory.SPECIALIZED_DEVELOPMENT,
    CICD_ENGINEER: AgentCategory.SPECIALIZED_DEVELOPMENT,
    API_DOCS: AgentCategory.SPECIALIZED_DEVELOPMENT,
    SYSTEM_ARCHITECT: AgentCategory.SPECIALIZED_DEVELOPMENT,
    CODE_ANALYZER: AgentCategory.SPECIALIZED_DEVELOPMENT,
    
    # V3 Specialized
    QUEEN_COORDINATOR: AgentCategory.V3_SPECIALIZED,
    SECURITY_ARCHITECT: AgentCategory.V3_SPECIALIZED,
    SECURITY_AUDITOR: AgentCategory.V3_SPECIALIZED,
    MEMORY_SPECIALIST: AgentCategory.V3_SPECIALIZED,
    SWARM_SPECIALIST: AgentCategory.V3_SPECIALIZED,
    INTEGRATION_ARCHITECT: AgentCategory.V3_SPECIALIZED,
    PERFORMANCE_ENGINEER: AgentCategory.V3_SPECIALIZED,
    CORE_ARCHITECT: AgentCategory.V3_SPECIALIZED,
    TEST_ARCHITECT: AgentCategory.V3_SPECIALIZED,
    PROJECT_COORDINATOR: AgentCategory.V3_SPECIALIZED,
}


# ===== Agent Capabilities =====

class AgentCapability(Enum):
    """Capabilities that agents can have"""
    CODE_GENERATION = "code_generation"
    CODE_REVIEW = "code_review"
    TESTING = "testing"
    PLANNING = "planning"
    RESEARCH = "research"
    COORDINATION = "coordination"
    CONSENSUS = "consensus"
    MEMORY_MANAGEMENT = "memory_management"
    SECURITY = "security"
    PERFORMANCE = "performance"
    DOCUMENTATION = "documentation"
    ARCHITECTURE = "architecture"


# Capability mapping for each agent type
AGENT_CAPABILITIES: Dict[str, List[AgentCapability]] = {
    CODER: [AgentCapability.CODE_GENERATION, AgentCapability.ARCHITECTURE],
    REVIEWER: [AgentCapability.CODE_REVIEW, AgentCapability.SECURITY],
    TESTER: [AgentCapability.TESTING, AgentCapability.CODE_REVIEW],
    PLANNER: [AgentCapability.PLANNING, AgentCapability.ARCHITECTURE],
    RESEARCHER: [AgentCapability.RESEARCH, AgentCapability.DOCUMENTATION],
    
    HIERARCHICAL_COORDINATOR: [AgentCapability.COORDINATION, AgentCapability.PLANNING],
    MESH_COORDINATOR: [AgentCapability.COORDINATION, AgentCapability.CONSENSUS],
    ADAPTIVE_COORDINATOR: [AgentCapability.COORDINATION, AgentCapability.PERFORMANCE],
    COLLECTIVE_INTELLIGENCE_COORDINATOR: [AgentCapability.COORDINATION, AgentCapability.CONSENSUS],
    SWARM_MEMORY_MANAGER: [AgentCapability.MEMORY_MANAGEMENT, AgentCapability.COORDINATION],
    
    BYZANTINE_COORDINATOR: [AgentCapability.CONSENSUS, AgentCapability.SECURITY],
    RAFT_MANAGER: [AgentCapability.CONSENSUS, AgentCapability.COORDINATION],
    GOSSIP_COORDINATOR: [AgentCapability.CONSENSUS, AgentCapability.MEMORY_MANAGEMENT],
    CONSENSUS_BUILDER: [AgentCapability.CONSENSUS, AgentCapability.COORDINATION],
    CRDT_SYNCHRONIZER: [AgentCapability.CONSENSUS, AgentCapability.MEMORY_MANAGEMENT],
    QUORUM_MANAGER: [AgentCapability.CONSENSUS, AgentCapability.SECURITY],
    SECURITY_MANAGER: [AgentCapability.SECURITY, AgentCapability.COORDINATION],
    
    PERF_ANALYZER: [AgentCapability.PERFORMANCE, AgentCapability.CODE_REVIEW],
    PERFORMANCE_BENCHMARKER: [AgentCapability.PERFORMANCE, AgentCapability.TESTING],
    TASK_ORCHESTRATOR: [AgentCapability.COORDINATION, AgentCapability.PLANNING],
    MEMORY_COORDINATOR: [AgentCapability.MEMORY_MANAGEMENT, AgentCapability.COORDINATION],
    SMART_AGENT: [AgentCapability.CODE_GENERATION, AgentCapability.PERFORMANCE],
    
    QUEEN_COORDINATOR: [AgentCapability.COORDINATION, AgentCapability.CONSENSUS, AgentCapability.PLANNING],
    SECURITY_ARCHITECT: [AgentCapability.SECURITY, AgentCapability.ARCHITECTURE],
    SECURITY_AUDITOR: [AgentCapability.SECURITY, AgentCapability.CODE_REVIEW],
    MEMORY_SPECIALIST: [AgentCapability.MEMORY_MANAGEMENT, AgentCapability.ARCHITECTURE],
    SWARM_SPECIALIST: [AgentCapability.COORDINATION, AgentCapability.CONSENSUS],
}


# ===== Data Classes =====

@dataclass
class AgentConfig:
    """Configuration for creating an agent"""
    agent_type: str
    id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    priority: str = "normal"  # low, normal, high, critical
    max_iterations: int = 50
    enabled_toolsets: Optional[List[str]] = None
    disabled_toolsets: Optional[List[str]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    parent_agent_id: Optional[str] = None


@dataclass
class AgentInfo:
    """Information about an agent"""
    id: str
    agent_type: str
    name: str
    status: str  # active, idle, terminated
    created_at: float
    last_activity_at: Optional[float] = None
    config: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    capabilities: List[str] = field(default_factory=list)
    category: Optional[str] = None


@dataclass
class AgentStatus(AgentInfo):
    """Detailed agent status with metrics"""
    metrics: Dict[str, Any] = field(default_factory=dict)
    history: List[Dict[str, Any]] = field(default_factory=list)
    current_task: Optional[str] = None
    assigned_tasks: List[str] = field(default_factory=list)
    completed_tasks: List[str] = field(default_factory=list)


@dataclass
class AgentMetrics:
    """Performance metrics for an agent"""
    tasks_completed: int = 0
    tasks_in_progress: int = 0
    tasks_failed: int = 0
    average_execution_time: float = 0.0
    total_execution_time: float = 0.0
    uptime: float = 0.0
    tokens_used: int = 0
    api_calls: int = 0
    errors_encountered: int = 0


@dataclass
class TaskAssignment:
    """Task assigned to an agent"""
    task_id: str
    agent_id: str
    goal: str
    context: Optional[str] = None
    priority: str = "normal"
    deadline: Optional[float] = None
    dependencies: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=lambda: datetime.now().timestamp())


@dataclass
class AgentSpawnResult:
    """Result of spawning an agent"""
    agent_id: str
    agent_type: str
    status: str
    created_at: str
    message: Optional[str] = None


@dataclass
class AgentListResult:
    """Result of listing agents"""
    agents: List[AgentInfo]
    total: int
    limit: Optional[int] = None
    offset: Optional[int] = None


@dataclass
class AgentTerminateResult:
    """Result of terminating an agent"""
    agent_id: str
    terminated: bool
    terminated_at: str
    reason: Optional[str] = None


# ===== Agent Type Descriptions =====

AGENT_DESCRIPTIONS: Dict[str, str] = {
    CODER: "Generates high-quality code following best practices",
    REVIEWER: "Reviews code for quality, security, and performance issues",
    TESTER: "Creates and runs tests to ensure code correctness",
    PLANNER: "Creates detailed plans and architectures for complex tasks",
    RESEARCHER: "Researches technologies, patterns, and solutions",
    
    HIERARCHICAL_COORDINATOR: "Coordinates agents in a hierarchical topology",
    MESH_COORDINATOR: "Coordinates agents in a mesh network topology",
    ADAPTIVE_COORDINATOR: "Dynamically adapts coordination strategy based on workload",
    COLLECTIVE_INTELLIGENCE_COORDINATOR: "Orchestrates collective intelligence workflows",
    SWARM_MEMORY_MANAGER: "Manages shared memory across swarm agents",
    
    BYZANTINE_COORDINATOR: "Handles Byzantine fault tolerance in distributed systems",
    RAFT_MANAGER: "Manages Raft consensus protocol for distributed state",
    GOSSIP_COORDINATOR: "Coordinates gossip protocol for information dissemination",
    CONSENSUS_BUILDER: "Builds consensus among distributed agents",
    CRDT_SYNCHRONIZER: "Synchronizes CRDTs across distributed nodes",
    QUORUM_MANAGER: "Manages quorum-based decision making",
    SECURITY_MANAGER: "Manages security policies and threat detection",
    
    PERF_ANALYZER: "Analyzes performance bottlenecks and optimization opportunities",
    PERFORMANCE_BENCHMARKER: "Runs benchmarks and performance tests",
    TASK_ORCHESTRATOR: "Orchestrates complex multi-step tasks",
    MEMORY_COORDINATOR: "Coordinates memory usage across agents",
    SMART_AGENT: "Self-optimizing agent that learns from experience",
    
    QUEEN_COORDINATOR: "Central orchestrator for hive-mind coordination",
    SECURITY_ARCHITECT: "Designs secure system architectures",
    SECURITY_AUDITOR: "Audits systems for security vulnerabilities",
    MEMORY_SPECIALIST: "Specializes in memory system optimization",
    SWARM_SPECIALIST: "Expert in swarm coordination patterns",
    INTEGRATION_ARCHITECT: "Designs system integration patterns",
    PERFORMANCE_ENGINEER: "Engineers high-performance systems",
    CORE_ARCHITECT: "Designs core system architecture",
    TEST_ARCHITECT: "Designs comprehensive testing strategies",
    PROJECT_COORDINATOR: "Coordinates multi-agent project execution",
}


def get_agent_description(agent_type: str) -> str:
    """Get description for an agent type"""
    return AGENT_DESCRIPTIONS.get(agent_type, f"Specialized {agent_type} agent")


def get_agent_category(agent_type: str) -> AgentCategory:
    """Get category for an agent type"""
    return AGENT_CATEGORIES.get(agent_type, AgentCategory.CORE_DEVELOPMENT)


def get_agent_capabilities(agent_type: str) -> List[AgentCapability]:
    """Get capabilities for an agent type"""
    return AGENT_CAPABILITIES.get(agent_type, [AgentCapability.CODE_GENERATION])


def is_valid_agent_type(agent_type: str) -> bool:
    """Check if agent type is valid"""
    return agent_type in ALL_AGENT_TYPES


def get_agents_by_category(category: AgentCategory) -> List[str]:
    """Get all agent types in a category"""
    return [agent_type for agent_type, cat in AGENT_CATEGORIES.items() if cat == category]


def get_agents_by_capability(capability: AgentCapability) -> List[str]:
    """Get all agent types with a specific capability"""
    return [
        agent_type
        for agent_type, caps in AGENT_CAPABILITIES.items()
        if capability in caps
    ]
