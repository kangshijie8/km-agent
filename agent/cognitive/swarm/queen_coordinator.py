"""
Cognitive Core Queen Coordinator - Python Implementation

Central orchestrator for hive-mind coordination. The Queen manages:
- Agent lifecycle and topology
- Task allocation and routing
- Consensus coordination
- Collective intelligence workflows

Based on: @claude-flow/swarm/src/index.ts
"""

import uuid
import asyncio
import time
from typing import Dict, List, Optional, Any, Callable, Set
from dataclasses import dataclass, field
from datetime import datetime

from .types import (
    SwarmAgent, SwarmMessage, TaskAllocation, ConsensusProposal,
    SwarmConfig, SwarmStats, TopologyInfo, ConsensusResult, HiveMindDecision,
    SwarmTopology, ConsensusAlgorithm, SwarmAgentState, MessageType,
    get_topology_description, get_consensus_description
)


@dataclass
class QueenCoordinatorConfig:
    """Configuration for QueenCoordinator"""
    swarm_config: SwarmConfig = field(default_factory=SwarmConfig)
    enable_hive_mind: bool = True
    enable_collective_intelligence: bool = True
    auto_rebalance: bool = True
    rebalance_interval: float = 60.0
    max_agents_per_worker: int = 10
    decision_threshold: float = 0.7  # Minimum confidence for hive mind decisions


class QueenCoordinator:
    """
    Queen Coordinator - Central orchestrator for swarm coordination.
    
    The Queen provides:
    - Agent lifecycle management (register, heartbeat, unregister)
    - Topology management (hierarchical, mesh, centralized, etc.)
    - Task allocation and routing
    - Consensus coordination (Raft, Byzantine, Gossip, Paxos)
    - Collective intelligence workflows
    - Hive mind decision making
    
    Integration with Kunming:
        The Queen integrates with Kunming's delegate_tool to distribute
        tasks across multiple expert agents. It enhances Kunming with
        true multi-agent coordination capabilities.
    
    Example:
        ```python
        # Initialize Queen
        queen = QueenCoordinator(QueenCoordinatorConfig())
        await queen.initialize()
        
        # Register agents
        await queen.register_agent(agent_id="agent-1", agent_type="coder")
        await queen.register_agent(agent_id="agent-2", agent_type="tester")
        
        # Allocate task
        task = await queen.allocate_task("Implement authentication")
        
        # Make hive mind decision
        decision = await queen.hive_mind_decide(
            question="Which architecture pattern should we use?",
            options=["MVC", "MVVM", "Clean Architecture"]
        )
        ```
    """
    
    def __init__(self, config: Optional[QueenCoordinatorConfig] = None):
        """
        Initialize the Queen Coordinator.
        
        Args:
            config: Queen configuration
        """
        self.config = config or QueenCoordinatorConfig()
        self._initialized = False
        
        # Core state
        self._agents: Dict[str, SwarmAgent] = {}
        self._tasks: Dict[str, TaskAllocation] = {}
        self._proposals: Dict[str, ConsensusProposal] = {}
        self._decisions: Dict[str, HiveMindDecision] = {}
        
        # Topology state
        self._root_agents: List[str] = []  # For hierarchical
        self._central_coordinator: Optional[str] = None  # For centralized
        
        # Message bus
        self._message_handlers: List[Callable[[SwarmMessage], None]] = []
        self._message_history: List[SwarmMessage] = []
        
        # Background tasks
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._rebalance_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None

        # Statistics
        self._stats = SwarmStats()

        # Lock for state updates
        self._state_lock = asyncio.Lock()
        
        # Configuration
        self._proposal_ttl = 3600  # 提案过期时间（秒）
        self._cleanup_interval = 300  # 清理间隔（秒）
    
    async def initialize(self) -> None:
        """Initialize the Queen Coordinator"""
        if self._initialized:
            return
        
        # Start background tasks
        self._heartbeat_task = asyncio.create_task(self._heartbeat_monitor())
        if self.config.auto_rebalance:
            self._rebalance_task = asyncio.create_task(self._rebalance_monitor())
        self._cleanup_task = asyncio.create_task(self._cleanup_monitor())
        
        self._initialized = True
    
    async def shutdown(self) -> None:
        """Shutdown the Queen Coordinator"""
        # Cancel background tasks
        for task in [self._heartbeat_task, self._rebalance_task, self._cleanup_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Unregister all agents
        async with self._state_lock:
            agent_ids = list(self._agents.keys())
        
        for agent_id in agent_ids:
            try:
                await self.unregister_agent(agent_id)
            except Exception as e:
                logger.warning(f"Failed to unregister agent {agent_id}: {e}")
        
        self._initialized = False
    
    # ===== Agent Lifecycle =====
    
    async def register_agent(
        self,
        agent_id: str,
        agent_type: str,
        capabilities: Optional[List[str]] = None,
        parent_id: Optional[str] = None
    ) -> SwarmAgent:
        """
        Register a new agent in the swarm.
        
        Args:
            agent_id: Unique agent ID
            agent_type: Type of agent (e.g., "coder", "tester")
            capabilities: List of agent capabilities
            parent_id: Parent agent ID (for hierarchical topology)
            
        Returns:
            Registered agent
        """
        if agent_id in self._agents:
            return self._agents[agent_id]

        agent = SwarmAgent(
            id=agent_id,
            agent_type=agent_type,
            capabilities=capabilities or [],
            parent_id=parent_id
        )

        self._agents[agent_id] = agent

        # Update topology
        if self.config.swarm_config.topology == SwarmTopology.HIERARCHICAL:
            if parent_id and parent_id in self._agents:
                self._agents[parent_id].children_ids.append(agent_id)
            else:
                self._root_agents.append(agent_id)

        elif self.config.swarm_config.topology == SwarmTopology.CENTRALIZED:
            if not self._central_coordinator:
                self._central_coordinator = agent_id

        elif self.config.swarm_config.topology == SwarmTopology.MESH:
            # Connect to all existing agents
            for existing_id in self._agents:
                if existing_id != agent_id:
                    agent.neighbors.append(existing_id)
                    self._agents[existing_id].neighbors.append(agent_id)

        self._stats.total_agents += 1
        self._stats.active_agents += 1
        
        # Broadcast agent join
        await self._broadcast_message(
            MessageType.AGENT_JOIN,
            {"agent_id": agent_id, "agent_type": agent_type}
        )
        
        return agent
    
    async def unregister_agent(self, agent_id: str) -> bool:
        """
        Unregister an agent from the swarm.
        
        Args:
            agent_id: Agent ID to unregister
            
        Returns:
            True if unregistered, False if not found
        """
        agent = self._agents.get(agent_id)
        if not agent:
            return False
        
        # Update topology
        if agent.parent_id and agent.parent_id in self._agents:
            parent = self._agents[agent.parent_id]
            parent.children_ids = [c for c in parent.children_ids if c != agent_id]
        
        if agent_id in self._root_agents:
            self._root_agents.remove(agent_id)
        
        if agent_id == self._central_coordinator:
            self._central_coordinator = None
        
        # Remove from neighbors
        for neighbor_id in agent.neighbors:
            if neighbor_id in self._agents:
                neighbor = self._agents[neighbor_id]
                neighbor.neighbors = [n for n in neighbor.neighbors if n != agent_id]
        
        # Reassign children
        for child_id in agent.children_ids:
            if child_id in self._agents:
                child = self._agents[child_id]
                child.parent_id = agent.parent_id
                if agent.parent_id in self._agents:
                    self._agents[agent.parent_id].children_ids.append(child_id)
                else:
                    self._root_agents.append(child_id)
        
        # Update stats
        if agent.state == SwarmAgentState.BUSY:
            self._stats.busy_agents -= 1
        elif agent.state == SwarmAgentState.IDLE:
            self._stats.idle_agents -= 1
        elif agent.state == SwarmAgentState.OFFLINE:
            self._stats.offline_agents -= 1

        self._stats.total_agents -= 1
        self._stats.active_agents -= 1
        
        # Remove agent
        del self._agents[agent_id]
        
        # Broadcast agent leave
        await self._broadcast_message(
            MessageType.AGENT_LEAVE,
            {"agent_id": agent_id}
        )
        
        return True
    
    async def heartbeat(self, agent_id: str) -> bool:
        """
        Process agent heartbeat.
        
        Args:
            agent_id: Agent ID
            
        Returns:
            True if agent is registered
        """
        try:
            async with self._state_lock:
                agent = self._agents.get(agent_id)
                if not agent:
                    logger.warning(f"Heartbeat from unregistered agent: {agent_id}")
                    return False
                
                agent.last_heartbeat = datetime.now().timestamp()
                
                if agent.state == SwarmAgentState.OFFLINE:
                    agent.state = SwarmAgentState.IDLE
                    self._stats.idle_agents += 1
                    self._stats.offline_agents -= 1
                    logger.info(f"Agent {agent_id} back online")
                
                return True
                
        except Exception as e:
            logger.error(f"Error processing heartbeat for {agent_id}: {e}", exc_info=True)
            return False
    
    async def update_agent_state(
        self,
        agent_id: str,
        state: SwarmAgentState,
        load: Optional[float] = None
    ) -> bool:
        """
        Update agent state.

        Args:
            agent_id: Agent ID
            state: New state
            load: Optional load value (0.0 - 1.0)

        Returns:
            True if updated, False if not found
        """
        async with self._state_lock:
            agent = self._agents.get(agent_id)
            if not agent:
                return False

            old_state = agent.state
            agent.state = state

            if load is not None:
                agent.load = load

            # Update stats
            if old_state == SwarmAgentState.BUSY:
                self._stats.busy_agents -= 1
            elif old_state == SwarmAgentState.IDLE:
                self._stats.idle_agents -= 1

            if state == SwarmAgentState.BUSY:
                self._stats.busy_agents += 1
            elif state == SwarmAgentState.IDLE:
                self._stats.idle_agents += 1

            return True
    
    # ===== Task Allocation =====
    
    async def allocate_task(
        self,
        goal: str,
        priority: str = "normal",
        required_capabilities: Optional[List[str]] = None,
        preferred_agent_type: Optional[str] = None
    ) -> TaskAllocation:
        """
        Allocate a task to the best available agent.
        
        Args:
            goal: Task goal/description
            priority: Task priority (low, normal, high, critical)
            required_capabilities: Required agent capabilities
            preferred_agent_type: Preferred agent type
            
        Returns:
            Task allocation
        """
        task_id = f"task-{uuid.uuid4().hex[:8]}"
        
        task = TaskAllocation(
            task_id=task_id,
            goal=goal,
            priority=priority
        )
        
        # Find best agent
        best_agent = self._find_best_agent(
            required_capabilities,
            preferred_agent_type
        )
        
        if best_agent:
            task.assigned_to = best_agent.id
            task.assigned_by = "queen"
            task.status = "assigned"
            task.started_at = datetime.now().timestamp()
            
            # Update agent state
            await self.update_agent_state(best_agent.id, SwarmAgentState.BUSY)
            
            # Send task assignment message
            await self._send_message(
                MessageType.TASK_ASSIGNMENT,
                {
                    "task_id": task_id,
                    "goal": goal,
                    "priority": priority
                },
                best_agent.id
            )
        else:
            task.status = "pending"
        
        self._tasks[task_id] = task
        self._stats.total_tasks += 1
        
        return task
    
    async def complete_task(
        self,
        task_id: str,
        result: Any,
        success: bool = True
    ) -> bool:
        """
        Mark a task as completed.
        
        Args:
            task_id: Task ID
            result: Task result
            success: Whether task succeeded
            
        Returns:
            True if completed, False if not found
        """
        task = self._tasks.get(task_id)
        if not task:
            return False
        
        task.completed_at = datetime.now().timestamp()
        task.result = result
        
        if success:
            task.status = "completed"
            self._stats.completed_tasks += 1
            
            # Send task result message
            await self._send_message(
                MessageType.TASK_RESULT,
                {"task_id": task_id, "result": result},
                task.assigned_to
            )
        else:
            task.status = "failed"
            task.error = str(result)
            self._stats.failed_tasks += 1
            
            await self._send_message(
                MessageType.TASK_FAILED,
                {"task_id": task_id, "error": str(result)},
                task.assigned_to
            )
        
        # Free agent
        if task.assigned_to and task.assigned_to in self._agents:
            await self.update_agent_state(task.assigned_to, SwarmAgentState.IDLE)
        
        return True
    
    def _find_best_agent(
        self,
        required_capabilities: Optional[List[str]] = None,
        preferred_agent_type: Optional[str] = None
    ) -> Optional[SwarmAgent]:
        """Find the best available agent for a task"""
        candidates = []
        
        for agent in self._agents.values():
            if agent.state != SwarmAgentState.IDLE:
                continue
            
            # Check capabilities
            if required_capabilities:
                if not all(cap in agent.capabilities for cap in required_capabilities):
                    continue
            
            # Score agent
            score = 1.0 - agent.load  # Prefer less loaded agents
            
            if preferred_agent_type and agent.agent_type == preferred_agent_type:
                score += 1.0
            
            candidates.append((agent, score))
        
        if not candidates:
            return None
        
        # Sort by score (descending)
        candidates.sort(key=lambda x: x[1], reverse=True)
        
        return candidates[0][0]
    
    # ===== Consensus Coordination =====
    
    async def propose_consensus(
        self,
        value: Any,
        algorithm: Optional[ConsensusAlgorithm] = None
    ) -> ConsensusProposal:
        """
        Propose a value for consensus.
        
        Args:
            value: Value to propose
            algorithm: Consensus algorithm to use
            
        Returns:
            Consensus proposal
        """
        proposal_id = f"proposal-{uuid.uuid4().hex[:8]}"
        
        proposal = ConsensusProposal(
            id=proposal_id,
            algorithm=algorithm or self.config.swarm_config.consensus_algorithm,
            proposed_by="queen",
            value=value,
            timestamp=datetime.now().timestamp()
        )
        
        self._proposals[proposal_id] = proposal
        
        # Broadcast proposal
        await self._broadcast_message(
            MessageType.CONSENSUS_PROPOSE,
            {
                "proposal_id": proposal_id,
                "algorithm": proposal.algorithm.value,
                "value": value
            }
        )
        
        return proposal
    
    async def vote_consensus(
        self,
        proposal_id: str,
        agent_id: str,
        vote: bool
    ) -> bool:
        """
        Cast a vote on a consensus proposal.
        
        Args:
            proposal_id: Proposal ID
            agent_id: Agent ID voting
            vote: True for accept, False for reject
            
        Returns:
            True if vote recorded, False if proposal not found
        """
        try:
            async with self._state_lock:
                proposal = self._proposals.get(proposal_id)
                if not proposal:
                    logger.warning(f"Vote for unknown proposal: {proposal_id}")
                    return False
                
                # Check if proposal is still pending
                if proposal.status != "pending":
                    logger.debug(f"Proposal {proposal_id} already decided: {proposal.status}")
                    return False
                
                # Check if agent already voted
                if agent_id in proposal.votes:
                    logger.debug(f"Agent {agent_id} already voted on {proposal_id}")
                    return False
                
                proposal.votes[agent_id] = vote
                logger.debug(f"Agent {agent_id} voted {vote} on proposal {proposal_id}")
            
            # Check if consensus reached (outside lock to avoid deadlock)
            await self._check_consensus(proposal_id)
            
            return True
            
        except Exception as e:
            logger.error(f"Error recording vote for {proposal_id}: {e}", exc_info=True)
            return False
    
    async def _check_consensus(self, proposal_id: str) -> Optional[ConsensusResult]:
        """Check if consensus has been reached"""
        proposal = self._proposals.get(proposal_id)
        if not proposal:
            return None

        if proposal.status != "pending":
            return None

        total_agents = len(self._agents)
        if total_agents == 0:
            return None

        votes_for = sum(1 for v in proposal.votes.values() if v)
        votes_against = sum(1 for v in proposal.votes.values() if not v)

        # Different consensus rules based on algorithm
        if proposal.algorithm == ConsensusAlgorithm.RAFT:
            # Simple majority
            threshold = total_agents // 2 + 1
            if votes_for >= threshold:
                proposal.status = "accepted"
            elif votes_against >= threshold:
                proposal.status = "rejected"

        elif proposal.algorithm == ConsensusAlgorithm.BYZANTINE:
            # 2/3 majority for Byzantine fault tolerance
            threshold = (2 * total_agents) // 3
            if votes_for >= threshold:
                proposal.status = "accepted"
            elif votes_against >= threshold:
                proposal.status = "rejected"

        elif proposal.algorithm == ConsensusAlgorithm.PAXOS:
            # Paxos requires majority of acceptors
            threshold = total_agents // 2 + 1
            if votes_for >= threshold:
                proposal.status = "accepted"
            elif votes_against >= threshold:
                proposal.status = "rejected"
        
        elif proposal.algorithm == ConsensusAlgorithm.GOSSIP:
            # Gossip protocol: accept if majority heard
            heard_from = len(proposal.votes)
            threshold = total_agents // 2 + 1
            if heard_from >= threshold and votes_for > votes_against:
                proposal.status = "accepted"
            elif heard_from >= threshold and votes_against >= votes_for:
                proposal.status = "rejected"
        
        else:
            # Default: simple majority for other algorithms (including HYBRID)
            threshold = total_agents // 2 + 1
            if votes_for >= threshold:
                proposal.status = "accepted"
            elif votes_against >= threshold:
                proposal.status = "rejected"
        
        if proposal.status in ("accepted", "rejected"):
            self._stats.consensus_rounds += 1
            
            # Broadcast result
            await self._broadcast_message(
                MessageType.CONSENSUS_COMMIT,
                {
                    "proposal_id": proposal_id,
                    "status": proposal.status,
                    "votes_for": votes_for,
                    "votes_against": votes_against
                }
            )
            
            return ConsensusResult(
                success=proposal.status == "accepted",
                algorithm=proposal.algorithm,
                proposal_id=proposal_id,
                value=proposal.value,
                votes_for=votes_for,
                votes_against=votes_against
            )
        
        return None
    
    # ===== Hive Mind Decision Making =====
    
    @staticmethod
    def _cast_vote(agent_type: str, options: List[str]) -> str:
        """Cast a vote based on agent type/expertise matching against options.
        
        Agents vote for options that semantically match their role.
        If no match is found, a random choice is made (not round-robin).
        """
        import random
        
        role_lower = (agent_type or "").lower()
        role_keywords = set(role_lower.replace("-", " ").replace("_", " ").split())
        
        for option in options:
            option_lower = option.lower()
            if any(kw in option_lower for kw in role_keywords):
                return option
        
        return random.choice(options)
    
    async def hive_mind_decide(
        self,
        question: str,
        options: List[str],
        min_participation: Optional[int] = None
    ) -> HiveMindDecision:
        """
        Make a decision using collective intelligence.
        
        Args:
            question: Decision question
            options: Available options
            min_participation: Minimum number of agents to participate
            
        Returns:
            Hive mind decision
        """
        decision_id = f"decision-{uuid.uuid4().hex[:8]}"
        
        # Get participating agents
        if min_participation:
            participating = list(self._agents.keys())[:min_participation]
        else:
            participating = list(self._agents.keys())
        
        # Collect votes from agents
        votes: Dict[str, str] = {}
        
        for agent_id in participating:
            agent = self._agents.get(agent_id)
            if agent:
                vote = self._cast_vote(agent.agent_type, options)
                votes[agent_id] = vote
        
        # Count votes
        vote_counts: Dict[str, int] = {}
        for vote in votes.values():
            vote_counts[vote] = vote_counts.get(vote, 0) + 1
        
        # Find winner
        if vote_counts:
            winner = max(vote_counts, key=vote_counts.get)
            confidence = vote_counts[winner] / len(votes)
            consensus_reached = confidence >= self.config.decision_threshold
        else:
            winner = options[0]
            confidence = 0.0
            consensus_reached = False
        
        decision = HiveMindDecision(
            id=decision_id,
            decision=winner,
            confidence=confidence,
            participating_agents=participating,
            consensus_reached=consensus_reached,
            metadata={
                "question": question,
                "options": options,
                "vote_counts": vote_counts
            }
        )
        
        self._decisions[decision_id] = decision
        
        return decision
    
    # ===== Message Bus =====
    
    async def _broadcast_message(
        self,
        msg_type: MessageType,
        payload: Dict[str, Any]
    ) -> None:
        """Broadcast a message to all agents"""
        message = SwarmMessage(
            id=f"msg-{uuid.uuid4().hex[:8]}",
            type=msg_type,
            sender_id="queen",
            recipient_id=None,
            payload=payload
        )
        
        self._message_history.append(message)
        self._stats.messages_sent += 1
        
        # Notify handlers
        for handler in self._message_handlers:
            try:
                handler(message)
            except Exception:
                pass
    
    async def _send_message(
        self,
        msg_type: MessageType,
        payload: Dict[str, Any],
        recipient_id: str
    ) -> None:
        """Send a message to a specific agent"""
        message = SwarmMessage(
            id=f"msg-{uuid.uuid4().hex[:8]}",
            type=msg_type,
            sender_id="queen",
            recipient_id=recipient_id,
            payload=payload
        )
        
        self._message_history.append(message)
        self._stats.messages_sent += 1
    
    def add_message_handler(self, handler: Callable[[SwarmMessage], None]) -> None:
        """Add a message handler"""
        self._message_handlers.append(handler)
    
    # ===== Background Tasks =====
    
    async def _heartbeat_monitor(self) -> None:
        """Monitor agent heartbeats"""
        while True:
            try:
                await asyncio.sleep(self.config.swarm_config.heartbeat_interval)
                
                now = datetime.now().timestamp()
                timeout = self.config.swarm_config.heartbeat_interval * 3
                
                # Create a snapshot to avoid modification during iteration
                agents_snapshot = list(self._agents.values())
                for agent in agents_snapshot:
                    try:
                        if now - agent.last_heartbeat > timeout:
                            if agent.state != SwarmAgentState.OFFLINE:
                                old_state = agent.state
                                agent.state = SwarmAgentState.OFFLINE
                                
                                if old_state == SwarmAgentState.BUSY:
                                    self._stats.busy_agents -= 1
                                elif old_state == SwarmAgentState.IDLE:
                                    self._stats.idle_agents -= 1
                                
                                self._stats.offline_agents += 1
                    except Exception as e:
                        # Log but don't crash on individual agent errors
                        logger.debug(f"Error checking heartbeat for agent: {e}")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                # Log unexpected errors but keep monitoring
                logger.warning(f"Heartbeat monitor error: {e}")
                await asyncio.sleep(1)
    
    async def _rebalance_monitor(self) -> None:
        """Monitor and rebalance workload"""
        while True:
            try:
                await asyncio.sleep(self.config.rebalance_interval)
                await self._rebalance_workload()
            except asyncio.CancelledError:
                break
            except Exception as e:
                # Log unexpected errors but keep monitoring
                logger.warning(f"Rebalance monitor error: {e}")
                await asyncio.sleep(1)
    
    async def _rebalance_workload(self) -> None:
        """Rebalance workload across agents"""
        # Find overloaded and underloaded agents
        overloaded = []
        underloaded = []
        
        for agent in self._agents.values():
            if agent.state == SwarmAgentState.OFFLINE:
                continue
            
            if agent.load > 0.8:
                overloaded.append(agent)
            elif agent.load < 0.2 and agent.state == SwarmAgentState.IDLE:
                underloaded.append(agent)
        
        # Rebalance logic would go here
        # For now, just log the state
        if overloaded or underloaded:
            pass  # Could trigger scaling or task redistribution
    
    # ===== Statistics =====
    
    async def get_stats(self) -> SwarmStats:
        """Get swarm statistics"""
        return self._stats
    
    async def get_topology_info(self) -> TopologyInfo:
        """Get topology information"""
        return TopologyInfo(
            type=self.config.swarm_config.topology,
            depth=self._calculate_topology_depth(),
            central_nodes=[self._central_coordinator] if self._central_coordinator else [],
            edge_nodes=self._root_agents.copy()
        )
    
    def _calculate_topology_depth(self) -> int:
        """Calculate depth of hierarchical topology"""
        if self.config.swarm_config.topology != SwarmTopology.HIERARCHICAL:
            return 0
        
        def get_depth(agent_id: str, visited: Set[str]) -> int:
            if agent_id in visited:
                return 0
            visited.add(agent_id)
            
            agent = self._agents.get(agent_id)
            if not agent or not agent.children_ids:
                return 1
            
            child_depths = [
                get_depth(child_id, visited)
                for child_id in agent.children_ids
            ]
            
            return 1 + max(child_depths, default=0)
        
        max_depth = 0
        for root_id in self._root_agents:
            depth = get_depth(root_id, set())
            max_depth = max(max_depth, depth)
        
        return max_depth
    
    # ===== Utility Methods =====
    
    def get_agents(self) -> List[SwarmAgent]:
        """Get all agents"""
        return list(self._agents.values())
    
    def get_agent(self, agent_id: str) -> Optional[SwarmAgent]:
        """Get agent by ID"""
        return self._agents.get(agent_id)
    
    def get_tasks(self) -> List[TaskAllocation]:
        """Get all tasks"""
        return list(self._tasks.values())
    
    def get_pending_tasks(self) -> List[TaskAllocation]:
        """Get pending tasks"""
        return [t for t in self._tasks.values() if t.status == "pending"]

    async def _cleanup_monitor(self) -> None:
        """Background task to clean up expired proposals and tasks"""
        import logging
        logger = logging.getLogger(__name__)
        
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                
                if not self._initialized:
                    break
                
                await self._cleanup_expired_proposals()
                await self._cleanup_expired_tasks()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup monitor: {e}", exc_info=True)
    
    async def _cleanup_expired_proposals(self) -> None:
        """Clean up expired consensus proposals"""
        import logging
        logger = logging.getLogger(__name__)
        
        current_time = datetime.now().timestamp()
        expired_proposals = []
        
        async with self._state_lock:
            for proposal_id, proposal in list(self._proposals.items()):
                # Check if proposal is older than TTL
                proposal_age = current_time - proposal.created_at
                
                # Clean up decided proposals after 5 minutes
                if proposal.status in ("accepted", "rejected") and proposal_age > 300:
                    expired_proposals.append(proposal_id)
                # Clean up pending proposals after TTL
                elif proposal.status == "pending" and proposal_age > self._proposal_ttl:
                    expired_proposals.append(proposal_id)
                    logger.warning(f"Proposal {proposal_id} expired without consensus")
        
        # Remove expired proposals outside lock
        for proposal_id in expired_proposals:
            try:
                async with self._state_lock:
                    if proposal_id in self._proposals:
                        del self._proposals[proposal_id]
                logger.debug(f"Cleaned up expired proposal: {proposal_id}")
            except Exception as e:
                logger.error(f"Failed to cleanup proposal {proposal_id}: {e}")
    
    async def _cleanup_expired_tasks(self) -> None:
        """Clean up completed or expired tasks"""
        import logging
        logger = logging.getLogger(__name__)
        
        current_time = datetime.now().timestamp()
        task_ttl = 86400  # 24 hours
        expired_tasks = []
        
        async with self._state_lock:
            for task_id, task in list(self._tasks.items()):
                task_age = current_time - task.created_at
                
                # Clean up completed/failed tasks after TTL
                if task.status in ("completed", "failed", "cancelled") and task_age > task_ttl:
                    expired_tasks.append(task_id)
        
        # Remove expired tasks outside lock
        for task_id in expired_tasks:
            try:
                async with self._state_lock:
                    if task_id in self._tasks:
                        del self._tasks[task_id]
                logger.debug(f"Cleaned up expired task: {task_id}")
            except Exception as e:
                logger.error(f"Failed to cleanup task {task_id}: {e}")

