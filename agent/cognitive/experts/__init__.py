"""
Cognitive Core Expert Agent System - Python Implementation

Enterprise-grade expert agent system with 55+ specialized agent types,
factory pattern for agent creation, and lifecycle management.

This module provides:
- 55 expert agent types across 7 categories
- AgentFactory for creating and managing agents
- Task routing and assignment
- Lifecycle management (spawn, execute, terminate)
- Integration with Kunming AIAgent

Integration with Kunming:
    The expert system wraps Kunming's AIAgent to provide specialized
    configurations for different agent types. It enhances Kunming's
    existing delegate_tool with 55+ pre-configured expert types.

Example:
    ```python
    from agent.cognitive.experts import (
        AgentFactory, AgentConfig, create_agent_factory
    )
    
    # Create factory
    factory = await create_agent_factory()
    
    # Spawn a coder agent
    result = await factory.spawn_agent(AgentConfig(
        agent_type="coder",
        name="backend-coder"
    ))
    
    # Assign task
    from agent.cognitive.experts.types import TaskAssignment
    task_result = await factory.assign_task(TaskAssignment(
        task_id="task-1",
        agent_id=result.agent_id,
        goal="Implement user authentication"
    ))
    ```

Based on: @claude-flow/swarm and mcp/tools/agent-tools.ts V3.5
"""

# ===== Types =====
from .types import (
    # Agent Types (55 total)
    CODER, REVIEWER, TESTER, PLANNER, RESEARCHER,
    HIERARCHICAL_COORDINATOR, MESH_COORDINATOR, ADAPTIVE_COORDINATOR,
    COLLECTIVE_INTELLIGENCE_COORDINATOR, SWARM_MEMORY_MANAGER,
    BYZANTINE_COORDINATOR, RAFT_MANAGER, GOSSIP_COORDINATOR,
    CONSENSUS_BUILDER, CRDT_SYNCHRONIZER, QUORUM_MANAGER, SECURITY_MANAGER,
    PERF_ANALYZER, PERFORMANCE_BENCHMARKER, TASK_ORCHESTRATOR,
    MEMORY_COORDINATOR, SMART_AGENT,
    SPARC_COORD, SPARC_CODER, SPECIFICATION, PSEUDOCODE, ARCHITECTURE, REFINEMENT,
    BACKEND_DEV, FRONTEND_DEV, MOBILE_DEV, ML_DEVELOPER, CICD_ENGINEER,
    API_DOCS, SYSTEM_ARCHITECT, CODE_ANALYZER,
    QUEEN_COORDINATOR, SECURITY_ARCHITECT, SECURITY_AUDITOR, MEMORY_SPECIALIST,
    SWARM_SPECIALIST, INTEGRATION_ARCHITECT, PERFORMANCE_ENGINEER, CORE_ARCHITECT,
    TEST_ARCHITECT, PROJECT_COORDINATOR,
    
    # Categories and Capabilities
    AgentCategory, AgentCapability,
    ALL_AGENT_TYPES, AGENT_CATEGORIES, AGENT_CAPABILITIES,
    
    # Data Classes
    AgentConfig, AgentInfo, AgentStatus, AgentMetrics,
    AgentSpawnResult, AgentListResult, AgentTerminateResult,
    TaskAssignment,
    
    # Utilities
    get_agent_description, get_agent_category, get_agent_capabilities,
    is_valid_agent_type, get_agents_by_category, get_agents_by_capability,
)

# ===== Agent Factory =====
from .agent_factory import (
    AgentFactory,
    ExpertAgent,
    AgentState,
    create_agent_factory,
    get_agent_type_description,
    list_all_agent_types,
)

# ===== Version =====
__version__ = "3.5.0"

# ===== Exports =====
__all__ = [
    # Agent Types
    "CODER", "REVIEWER", "TESTER", "PLANNER", "RESEARCHER",
    "HIERARCHICAL_COORDINATOR", "MESH_COORDINATOR", "ADAPTIVE_COORDINATOR",
    "COLLECTIVE_INTELLIGENCE_COORDINATOR", "SWARM_MEMORY_MANAGER",
    "BYZANTINE_COORDINATOR", "RAFT_MANAGER", "GOSSIP_COORDINATOR",
    "CONSENSUS_BUILDER", "CRDT_SYNCHRONIZER", "QUORUM_MANAGER", "SECURITY_MANAGER",
    "PERF_ANALYZER", "PERFORMANCE_BENCHMARKER", "TASK_ORCHESTRATOR",
    "MEMORY_COORDINATOR", "SMART_AGENT",
    "SPARC_COORD", "SPARC_CODER", "SPECIFICATION", "PSEUDOCODE", "ARCHITECTURE", "REFINEMENT",
    "BACKEND_DEV", "FRONTEND_DEV", "MOBILE_DEV", "ML_DEVELOPER", "CICD_ENGINEER",
    "API_DOCS", "SYSTEM_ARCHITECT", "CODE_ANALYZER",
    "QUEEN_COORDINATOR", "SECURITY_ARCHITECT", "SECURITY_AUDITOR", "MEMORY_SPECIALIST",
    "SWARM_SPECIALIST", "INTEGRATION_ARCHITECT", "PERFORMANCE_ENGINEER", "CORE_ARCHITECT",
    "TEST_ARCHITECT", "PROJECT_COORDINATOR",
    
    # Enums
    "AgentCategory", "AgentCapability",
    "AgentState",
    
    # Constants
    "ALL_AGENT_TYPES", "AGENT_CATEGORIES", "AGENT_CAPABILITIES",
    
    # Data Classes
    "AgentConfig", "AgentInfo", "AgentStatus", "AgentMetrics",
    "AgentSpawnResult", "AgentListResult", "AgentTerminateResult",
    "TaskAssignment",
    
    # Factory
    "AgentFactory", "ExpertAgent",
    "create_agent_factory",
    "get_agent_type_description",
    "list_all_agent_types",
    
    # Utilities
    "get_agent_description", "get_agent_category", "get_agent_capabilities",
    "is_valid_agent_type", "get_agents_by_category", "get_agents_by_capability",
]
