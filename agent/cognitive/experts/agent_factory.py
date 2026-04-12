"""
Cognitive Core Agent Factory - Python Implementation

Factory pattern for creating and managing 55+ specialized expert agents.
Provides lifecycle management, task routing, and integration with Kunming.

Based on: @claude-flow/swarm and mcp/tools/agent-tools.ts
"""

import uuid
import asyncio
import threading
from typing import Dict, List, Optional, Any, Callable, Type
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .types import (
    AgentConfig, AgentInfo, AgentStatus, AgentMetrics,
    AgentSpawnResult, AgentListResult, AgentTerminateResult,
    TaskAssignment, AgentCategory, AgentCapability,
    ALL_AGENT_TYPES, AGENT_CATEGORIES, AGENT_CAPABILITIES,
    AGENT_DESCRIPTIONS, get_agent_description, get_agent_category,
    get_agent_capabilities, is_valid_agent_type
)


class AgentState(Enum):
    """Agent lifecycle states"""
    PENDING = "pending"
    INITIALIZING = "initializing"
    ACTIVE = "active"
    IDLE = "idle"
    BUSY = "busy"
    TERMINATING = "terminating"
    TERMINATED = "terminated"
    ERROR = "error"


@dataclass
class ExpertAgent:
    """
    Expert Agent instance with full lifecycle management.
    
    This class wraps Kunming's AIAgent to provide Cognitive Core-style
    expert agent capabilities with specialized configurations.
    """
    id: str
    agent_type: str
    name: str
    config: AgentConfig
    state: AgentState = AgentState.PENDING
    created_at: float = field(default_factory=lambda: datetime.now().timestamp())
    last_activity_at: Optional[float] = None
    metrics: AgentMetrics = field(default_factory=AgentMetrics)
    current_task: Optional[str] = None
    assigned_tasks: List[str] = field(default_factory=list)
    completed_tasks: List[str] = field(default_factory=list)
    failed_tasks: List[str] = field(default_factory=list)
    history: List[Dict[str, Any]] = field(default_factory=list)
    _agent_instance: Optional[Any] = field(default=None, repr=False)
    
    def __post_init__(self):
        """Initialize agent after creation"""
        if not self.name:
            self.name = f"{self.agent_type}-{self.id[:8]}"
    
    async def initialize(self) -> bool:
        """Initialize the agent instance"""
        try:
            self.state = AgentState.INITIALIZING
            
            # Import Kunming AIAgent
            from run_agent import AIAgent
            
            # Create agent instance with specialized configuration
            self._agent_instance = AIAgent(
                model=self.config.metadata.get("model", "anthropic/claude-opus-4.6"),
                max_iterations=self.config.max_iterations,
                enabled_toolsets=self.config.enabled_toolsets,
                disabled_toolsets=self.config.disabled_toolsets,
                quiet_mode=self.config.metadata.get("quiet_mode", True),
                save_trajectories=self.config.metadata.get("save_trajectories", False),
            )
            
            self.state = AgentState.IDLE
            self.last_activity_at = datetime.now().timestamp()
            return True
            
        except Exception as e:
            self.state = AgentState.ERROR
            self.history.append({
                "timestamp": datetime.now().timestamp(),
                "event": "initialization_failed",
                "error": str(e)
            })
            return False
    
    async def execute_task(self, task: TaskAssignment) -> Dict[str, Any]:
        """
        Execute a task using this agent.
        
        Args:
            task: Task assignment
            
        Returns:
            Task execution result
        """
        if self.state in (AgentState.TERMINATING, AgentState.TERMINATED):
            return {"success": False, "error": "Agent is terminated"}
        
        if not self._agent_instance:
            success = await self.initialize()
            if not success:
                return {"success": False, "error": "Failed to initialize agent"}
        
        self.state = AgentState.BUSY
        self.current_task = task.task_id
        self.assigned_tasks.append(task.task_id)
        
        start_time = datetime.now().timestamp()
        
        try:
            # Build context with agent type specialization
            context = self._build_task_context(task)
            
            # Execute using Kunming AIAgent
            result = await self._execute_with_kunming(context)
            
            # Update metrics
            execution_time = datetime.now().timestamp() - start_time
            self.metrics.tasks_completed += 1
            self.metrics.total_execution_time += execution_time
            self.metrics.average_execution_time = (
                self.metrics.total_execution_time / self.metrics.tasks_completed
            )
            
            self.completed_tasks.append(task.task_id)
            self.current_task = None
            self.state = AgentState.IDLE
            self.last_activity_at = datetime.now().timestamp()
            
            # Record history
            self.history.append({
                "timestamp": datetime.now().timestamp(),
                "event": "task_completed",
                "task_id": task.task_id,
                "execution_time": execution_time
            })
            
            return {
                "success": True,
                "result": result,
                "execution_time": execution_time,
                "agent_id": self.id
            }
            
        except Exception as e:
            self.metrics.tasks_failed += 1
            self.failed_tasks.append(task.task_id)
            self.current_task = None
            self.state = AgentState.ERROR
            
            self.history.append({
                "timestamp": datetime.now().timestamp(),
                "event": "task_failed",
                "task_id": task.task_id,
                "error": str(e)
            })
            
            return {
                "success": False,
                "error": str(e),
                "agent_id": self.id
            }
    
    def _build_task_context(self, task: TaskAssignment) -> str:
        """Build specialized context for the agent type"""
        agent_desc = get_agent_description(self.agent_type)
        capabilities = [c.value for c in get_agent_capabilities(self.agent_type)]
        
        context = f"""You are a {self.agent_type} agent.
Description: {agent_desc}
Capabilities: {', '.join(capabilities)}

Task: {task.goal}
"""
        if task.context:
            context += f"\nContext:\n{task.context}"
        
        return context
    
    async def _execute_with_kunming(self, context: str) -> str:
        """
        Execute task using Kunming AIAgent with true async support.
        
        Uses asyncio.to_thread for non-blocking execution in a thread pool,
        allowing proper async concurrency without blocking the event loop.
        """
        # Use asyncio.to_thread for true async execution
        # This runs the synchronous chat() in a thread pool without blocking
        return await asyncio.to_thread(self._agent_instance.chat, context)
    
    async def terminate(self, reason: Optional[str] = None) -> bool:
        """Terminate the agent"""
        self.state = AgentState.TERMINATING
        
        # Clean up agent instance
        self._agent_instance = None
        
        self.state = AgentState.TERMINATED
        self.history.append({
            "timestamp": datetime.now().timestamp(),
            "event": "terminated",
            "reason": reason
        })
        
        return True
    
    def to_info(self) -> AgentInfo:
        """Convert to AgentInfo"""
        return AgentInfo(
            id=self.id,
            agent_type=self.agent_type,
            name=self.name,
            status=self.state.value,
            created_at=self.created_at,
            last_activity_at=self.last_activity_at,
            config={
                "max_iterations": self.config.max_iterations,
                "enabled_toolsets": self.config.enabled_toolsets,
                "disabled_toolsets": self.config.disabled_toolsets,
            },
            metadata=self.config.metadata,
            capabilities=[c.value for c in get_agent_capabilities(self.agent_type)],
            category=get_agent_category(self.agent_type).value
        )
    
    def to_status(self) -> AgentStatus:
        """Convert to AgentStatus"""
        info = self.to_info()
        return AgentStatus(
            **info.__dict__,
            metrics=self.metrics.__dict__,
            history=self.history[-10:],  # Last 10 events
            current_task=self.current_task,
            assigned_tasks=self.assigned_tasks,
            completed_tasks=self.completed_tasks
        )


class AgentFactory:
    """
    Factory for creating and managing expert agents.
    
    This factory provides:
    - Creation of 55+ specialized agent types
    - Lifecycle management
    - Task routing
    - Metrics collection
    - Integration with Kunming AIAgent
    
    Example:
        ```python
        factory = AgentFactory()
        
        # Spawn a coder agent
        result = await factory.spawn_agent(AgentConfig(
            agent_type="coder",
            name="backend-coder"
        ))
        
        # Assign task
        task = TaskAssignment(
            task_id="task-1",
            agent_id=result.agent_id,
            goal="Implement user authentication"
        )
        result = await factory.assign_task(task)
        ```
    """
    
    def __init__(self):
        """Initialize the agent factory"""
        self._agents: Dict[str, ExpertAgent] = {}
        self._agents_by_type: Dict[str, List[str]] = {}
        self._task_queue: List[TaskAssignment] = []
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._initialized = False
        # 并发安全锁
        self._agents_lock = asyncio.Lock()
        self._task_queue_lock = asyncio.Lock()
    
    async def initialize(self) -> None:
        """Initialize the factory"""
        self._initialized = True
    
    async def shutdown(self) -> None:
        """Shutdown all agents and cleanup"""
        async with self._agents_lock:
            # Terminate all active agents
            agent_ids = list(self._agents.keys())
        
        for agent_id in agent_ids:
            try:
                await self.terminate_agent(agent_id, reason="Factory shutdown")
            except Exception as e:
                logger.warning(f"Failed to terminate agent {agent_id}: {e}")
        
        async with self._agents_lock:
            self._agents.clear()
            self._agents_by_type.clear()
        
        self._initialized = False
    
    # ===== Agent Creation =====
    
    async def spawn_agent(self, config: AgentConfig) -> AgentSpawnResult:
        """
        Spawn a new expert agent.
        
        Args:
            config: Agent configuration
            
        Returns:
            Spawn result with agent ID
        """
        if not is_valid_agent_type(config.agent_type):
            return AgentSpawnResult(
                agent_id="",
                agent_type=config.agent_type,
                status="error",
                created_at=datetime.now().isoformat(),
                message=f"Invalid agent type: {config.agent_type}"
            )
        
        # Generate agent ID
        agent_id = config.id or f"agent-{uuid.uuid4().hex[:12]}"
        
        # Create agent name if not provided
        name = config.name or f"{config.agent_type}-{agent_id[:8]}"
        
        # Create agent instance
        agent = ExpertAgent(
            id=agent_id,
            agent_type=config.agent_type,
            name=name,
            config=config
        )
        
        # Initialize agent
        success = await agent.initialize()
        
        if not success:
            return AgentSpawnResult(
                agent_id=agent_id,
                agent_type=config.agent_type,
                status="failed",
                created_at=datetime.now().isoformat(),
                message="Failed to initialize agent"
            )
        
        # Store agent with lock for thread safety
        async with self._agents_lock:
            self._agents[agent_id] = agent
            
            # Index by type
            if config.agent_type not in self._agents_by_type:
                self._agents_by_type[config.agent_type] = []
            self._agents_by_type[config.agent_type].append(agent_id)
        
        return AgentSpawnResult(
            agent_id=agent_id,
            agent_type=config.agent_type,
            status="active",
            created_at=datetime.now().isoformat(),
            message=f"Agent {name} spawned successfully"
        )
    
    async def spawn_agents_batch(
        self,
        configs: List[AgentConfig]
    ) -> List[AgentSpawnResult]:
        """
        Spawn multiple agents in parallel.
        
        Args:
            configs: List of agent configurations
            
        Returns:
            List of spawn results
        """
        tasks = [self.spawn_agent(config) for config in configs]
        return await asyncio.gather(*tasks)
    
    # ===== Agent Management =====
    
    async def get_agent(self, agent_id: str) -> Optional[ExpertAgent]:
        """Get an agent by ID"""
        return self._agents.get(agent_id)
    
    async def get_agent_info(self, agent_id: str) -> Optional[AgentInfo]:
        """Get agent info by ID"""
        agent = self._agents.get(agent_id)
        if agent:
            return agent.to_info()
        return None
    
    async def get_agent_status(self, agent_id: str) -> Optional[AgentStatus]:
        """Get detailed agent status"""
        agent = self._agents.get(agent_id)
        if agent:
            return agent.to_status()
        return None
    
    async def list_agents(
        self,
        agent_type: Optional[str] = None,
        category: Optional[AgentCategory] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> AgentListResult:
        """
        List agents with filtering.
        
        Args:
            agent_type: Filter by agent type
            category: Filter by category
            status: Filter by status
            limit: Maximum results
            offset: Pagination offset
            
        Returns:
            List of agent info
        """
        agents = list(self._agents.values())
        
        # Apply filters
        if agent_type:
            agents = [a for a in agents if a.agent_type == agent_type]
        
        if category:
            agents = [
                a for a in agents
                if get_agent_category(a.agent_type) == category
            ]
        
        if status:
            agents = [a for a in agents if a.state.value == status]
        
        # Sort by creation time
        agents.sort(key=lambda a: a.created_at, reverse=True)
        
        # Apply pagination
        total = len(agents)
        agents = agents[offset:offset + limit]
        
        return AgentListResult(
            agents=[a.to_info() for a in agents],
            total=total,
            limit=limit,
            offset=offset
        )
    
    async def terminate_agent(
        self,
        agent_id: str,
        reason: Optional[str] = None
    ) -> AgentTerminateResult:
        """
        Terminate an agent.
        
        Args:
            agent_id: Agent ID to terminate
            reason: Optional termination reason
            
        Returns:
            Termination result
        """
        agent = self._agents.get(agent_id)
        
        if not agent:
            return AgentTerminateResult(
                agent_id=agent_id,
                terminated=False,
                terminated_at=datetime.now().isoformat(),
                reason="Agent not found"
            )
        
        # Terminate agent
        await agent.terminate(reason)
        
        # Remove from indexes
        del self._agents[agent_id]
        
        if agent.agent_type in self._agents_by_type:
            self._agents_by_type[agent.agent_type] = [
                aid for aid in self._agents_by_type[agent.agent_type]
                if aid != agent_id
            ]
        
        return AgentTerminateResult(
            agent_id=agent_id,
            terminated=True,
            terminated_at=datetime.now().isoformat(),
            reason=reason
        )
    
    async def terminate_agents_batch(
        self,
        agent_ids: List[str],
        reason: Optional[str] = None
    ) -> List[AgentTerminateResult]:
        """Terminate multiple agents"""
        tasks = [
            self.terminate_agent(agent_id, reason)
            for agent_id in agent_ids
        ]
        return await asyncio.gather(*tasks)
    
    # ===== Task Management =====
    
    async def assign_task(self, task: TaskAssignment) -> Dict[str, Any]:
        """
        Assign a task to an agent.
        
        Args:
            task: Task assignment
            
        Returns:
            Task execution result
        """
        agent = self._agents.get(task.agent_id)
        
        if not agent:
            return {
                "success": False,
                "error": f"Agent {task.agent_id} not found"
            }
        
        if agent.state in (AgentState.TERMINATING, AgentState.TERMINATED):
            return {
                "success": False,
                "error": f"Agent {task.agent_id} is terminated"
            }
        
        # Execute task
        return await agent.execute_task(task)
    
    async def assign_task_by_type(
        self,
        agent_type: str,
        goal: str,
        context: Optional[str] = None,
        priority: str = "normal"
    ) -> Dict[str, Any]:
        """
        Assign task to an available agent of specified type.
        
        Args:
            agent_type: Type of agent to use
            goal: Task goal
            context: Optional context
            priority: Task priority
            
        Returns:
            Task execution result
        """
        # Find available agent
        agent_ids = self._agents_by_type.get(agent_type, [])
        
        available_agent = None
        for agent_id in agent_ids:
            agent = self._agents.get(agent_id)
            if agent and agent.state in (AgentState.IDLE, AgentState.ACTIVE):
                available_agent = agent
                break
        
        if not available_agent:
            # Spawn new agent
            result = await self.spawn_agent(AgentConfig(agent_type=agent_type))
            if result.status != "active":
                return {
                    "success": False,
                    "error": f"Failed to spawn {agent_type} agent"
                }
            available_agent = self._agents.get(result.agent_id)
        
        # Create task
        task = TaskAssignment(
            task_id=f"task-{uuid.uuid4().hex[:8]}",
            agent_id=available_agent.id,
            goal=goal,
            context=context,
            priority=priority
        )
        
        return await self.assign_task(task)
    
    # ===== Specialized Agent Creation =====
    
    async def create_coder_agent(
        self,
        name: Optional[str] = None,
        specialization: Optional[str] = None
    ) -> AgentSpawnResult:
        """Create a specialized coder agent"""
        metadata = {"specialization": specialization} if specialization else {}
        return await self.spawn_agent(AgentConfig(
            agent_type="coder",
            name=name,
            metadata=metadata
        ))
    
    async def create_reviewer_agent(
        self,
        name: Optional[str] = None,
        focus_areas: Optional[List[str]] = None
    ) -> AgentSpawnResult:
        """Create a code reviewer agent"""
        metadata = {"focus_areas": focus_areas or ["security", "performance"]}
        return await self.spawn_agent(AgentConfig(
            agent_type="reviewer",
            name=name,
            metadata=metadata
        ))
    
    async def create_planner_agent(
        self,
        name: Optional[str] = None,
        planning_depth: str = "detailed"
    ) -> AgentSpawnResult:
        """Create a planner agent"""
        return await self.spawn_agent(AgentConfig(
            agent_type="planner",
            name=name,
            metadata={"planning_depth": planning_depth}
        ))
    
    async def create_tester_agent(
        self,
        name: Optional[str] = None,
        test_types: Optional[List[str]] = None
    ) -> AgentSpawnResult:
        """Create a tester agent"""
        metadata = {"test_types": test_types or ["unit", "integration"]}
        return await self.spawn_agent(AgentConfig(
            agent_type="tester",
            name=name,
            metadata=metadata
        ))
    
    async def create_researcher_agent(
        self,
        name: Optional[str] = None,
        research_domains: Optional[List[str]] = None
    ) -> AgentSpawnResult:
        """Create a researcher agent"""
        metadata = {"domains": research_domains or []}
        return await self.spawn_agent(AgentConfig(
            agent_type="researcher",
            name=name,
            metadata=metadata
        ))
    
    async def create_queen_coordinator(
        self,
        name: Optional[str] = None
    ) -> AgentSpawnResult:
        """Create a queen coordinator for swarm management"""
        return await self.spawn_agent(AgentConfig(
            agent_type="queen-coordinator",
            name=name or "Queen",
            priority="critical",
            max_iterations=100
        ))
    
    # ===== Statistics =====
    
    async def get_factory_stats(self) -> Dict[str, Any]:
        """Get factory statistics"""
        total_agents = len(self._agents)
        agents_by_type = {
            agent_type: len(agent_ids)
            for agent_type, agent_ids in self._agents_by_type.items()
        }
        
        state_counts = {}
        for agent in self._agents.values():
            state = agent.state.value
            state_counts[state] = state_counts.get(state, 0) + 1
        
        total_tasks_completed = sum(
            a.metrics.tasks_completed for a in self._agents.values()
        )
        total_tasks_failed = sum(
            a.metrics.tasks_failed for a in self._agents.values()
        )
        
        return {
            "total_agents": total_agents,
            "agents_by_type": agents_by_type,
            "state_counts": state_counts,
            "total_tasks_completed": total_tasks_completed,
            "total_tasks_failed": total_tasks_failed,
            "queued_tasks": len(self._task_queue),
            "running_tasks": len(self._running_tasks)
        }
    
    # ===== Utility Methods =====
    
    def get_available_agent_types(self) -> List[str]:
        """Get list of available agent types"""
        return ALL_AGENT_TYPES.copy()
    
    def get_agents_by_capability(
        self,
        capability: AgentCapability
    ) -> List[ExpertAgent]:
        """Get agents with specific capability"""
        from .types import get_agents_by_capability as get_by_cap
        
        agent_types = get_by_cap(capability)
        agents = []
        
        for agent_type in agent_types:
            for agent_id in self._agents_by_type.get(agent_type, []):
                agent = self._agents.get(agent_id)
                if agent:
                    agents.append(agent)
        
        return agents
    
    async def find_best_agent_for_task(
        self,
        goal: str,
        required_capabilities: Optional[List[AgentCapability]] = None
    ) -> Optional[ExpertAgent]:
        """
        Find the best available agent for a task.
        
        Args:
            goal: Task goal description
            required_capabilities: Required capabilities
            
        Returns:
            Best available agent or None
        """
        candidates = []
        
        for agent in self._agents.values():
            if agent.state not in (AgentState.IDLE, AgentState.ACTIVE):
                continue
            
            if required_capabilities:
                agent_caps = get_agent_capabilities(agent.agent_type)
                if not all(cap in agent_caps for cap in required_capabilities):
                    continue
            
            candidates.append(agent)
        
        if not candidates:
            return None
        
        # Sort by availability and metrics
        candidates.sort(key=lambda a: (
            0 if a.state == AgentState.IDLE else 1,
            -a.metrics.tasks_completed
        ))
        
        return candidates[0]


# ===== Factory Functions =====

async def create_agent_factory() -> AgentFactory:
    """Create and initialize an agent factory"""
    factory = AgentFactory()
    await factory.initialize()
    return factory


def get_agent_type_description(agent_type: str) -> str:
    """Get human-readable description for agent type"""
    return get_agent_description(agent_type)


def list_all_agent_types() -> List[Dict[str, str]]:
    """List all available agent types with descriptions"""
    return [
        {
            "type": agent_type,
            "description": get_agent_description(agent_type),
            "category": get_agent_category(agent_type).value
        }
        for agent_type in ALL_AGENT_TYPES
    ]
