"""
RL Trainer - Basic implementation for reinforcement learning training.

Provides:
- Experience replay buffer
- Simple Q-Learning implementation
- Policy gradient basics
- Training loop scaffolding

This is a foundational implementation that can be extended with more
sophisticated algorithms (PPO, SAC, etc.).
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from numpy.typing import NDArray

from .types import (
    RLAction,
    RLAlgorithmType,
    RLConfig,
    RLExperience,
    RLPolicy,
    RLState,
    ReasoningTrajectory,
)

logger = logging.getLogger(__name__)


@dataclass
class ExperienceBuffer:
    """
    Experience replay buffer for RL training.
    
    Stores (state, action, reward, next_state, done) tuples and
    provides sampling for batch training.
    """
    capacity: int = 10000
    buffer: deque = field(default_factory=lambda: deque(maxlen=10000))
    
    def __post_init__(self):
        # Ensure buffer respects capacity
        self.buffer = deque(maxlen=self.capacity)
    
    def add(self, experience: RLExperience) -> None:
        """Add an experience to the buffer."""
        self.buffer.append(experience)
    
    def sample(self, batch_size: int) -> List[RLExperience]:
        """Sample a batch of experiences randomly."""
        if len(self.buffer) < batch_size:
            return list(self.buffer)
        return random.sample(list(self.buffer), batch_size)
    
    def __len__(self) -> int:
        return len(self.buffer)
    
    def is_ready(self, min_size: int = 100) -> bool:
        """Check if buffer has enough samples for training."""
        return len(self.buffer) >= min_size


class QLearningAgent:
    """
    Simple Q-Learning agent for discrete action spaces.
    
    This is a foundational RL implementation that can be used as a
    baseline or extended for more complex scenarios.
    """
    
    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        config: Optional[RLConfig] = None,
    ):
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.config = config or RLConfig(algorithm=RLAlgorithmType.Q_LEARNING)
        
        # Q-table for discrete state-action space
        # In practice, this would be a neural network for continuous spaces
        self.q_table: Dict[str, NDArray] = {}
        
        # Exploration parameters
        self.epsilon = self.config.epsilon
        self.epsilon_decay = 0.995
        self.epsilon_min = 0.01
        
        # Learning parameters
        self.learning_rate = self.config.learning_rate
        self.gamma = self.config.gamma
        
        # Training stats
        self.training_steps = 0
        self.episode_rewards: List[float] = []
    
    def _state_to_key(self, state: RLState) -> str:
        """Convert state to a hashable key for Q-table."""
        # Simple discretization - in practice, use better feature extraction
        features = state.features.flatten()
        # Quantize to reduce state space
        quantized = np.round(features * 10).astype(int)
        return hash(quantized.tobytes()).hex()[:16]
    
    def get_q_values(self, state: RLState) -> NDArray:
        """Get Q-values for all actions in a state."""
        state_key = self._state_to_key(state)
        if state_key not in self.q_table:
            # Initialize with small random values
            self.q_table[state_key] = np.random.randn(self.action_dim) * 0.01
        return self.q_table[state_key]
    
    def select_action(self, state: RLState, training: bool = True) -> int:
        """
        Select action using epsilon-greedy policy.
        
        Args:
            state: Current state
            training: If True, use exploration; if False, be greedy
            
        Returns:
            Selected action index
        """
        q_values = self.get_q_values(state)
        
        if training and random.random() < self.epsilon:
            # Explore: random action
            return random.randint(0, self.action_dim - 1)
        else:
            # Exploit: best action
            return int(np.argmax(q_values))
    
    def update(self, experience: RLExperience) -> float:
        """
        Update Q-value based on a single experience.
        
        Args:
            experience: (state, action, reward, next_state, done)
            
        Returns:
            TD error (for monitoring)
        """
        state_key = self._state_to_key(experience.state)
        action = int(experience.action.action_id)  # Assume action_id is action index
        
        current_q = self.q_table[state_key][action]
        
        # Calculate target Q-value
        if experience.done:
            target_q = experience.reward
        else:
            next_q_values = self.get_q_values(experience.next_state)
            target_q = experience.reward + self.gamma * np.max(next_q_values)
        
        # Update Q-value
        td_error = target_q - current_q
        self.q_table[state_key][action] += self.learning_rate * td_error
        
        # Decay epsilon
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)
        
        self.training_steps += 1
        return abs(td_error)
    
    def train_episode(self, experiences: List[RLExperience]) -> Dict[str, float]:
        """
        Train on a full episode of experiences.
        
        Args:
            experiences: List of experiences from one episode
            
        Returns:
            Training metrics
        """
        total_td_error = 0.0
        
        for exp in experiences:
            td_error = self.update(exp)
            total_td_error += td_error
        
        episode_reward = sum(exp.reward for exp in experiences)
        self.episode_rewards.append(episode_reward)
        
        return {
            "episode_reward": episode_reward,
            "mean_td_error": total_td_error / len(experiences) if experiences else 0,
            "epsilon": self.epsilon,
            "q_table_size": len(self.q_table),
        }


class RLTrainer:
    """
    Main RL trainer that orchestrates training across different algorithms.
    
    Provides a unified interface for:
    - Collecting experiences from trajectories
    - Training policies
    - Managing replay buffers
    - Tracking metrics
    """
    
    def __init__(
        self,
        config: Optional[RLConfig] = None,
        state_dim: int = 128,
        action_dim: int = 10,
    ):
        self.config = config or RLConfig()
        self.state_dim = state_dim
        self.action_dim = action_dim
        
        # Experience replay buffer
        self.buffer = ExperienceBuffer(capacity=self.config.buffer_size)
        
        # Algorithm-specific agent
        self.agent: Optional[QLearningAgent] = None
        if self.config.algorithm == RLAlgorithmType.Q_LEARNING:
            self.agent = QLearningAgent(state_dim, action_dim, config)
        else:
            # Default to Q-Learning for now
            logger.warning(
                f"Algorithm {self.config.algorithm} not fully implemented, "
                "falling back to Q-Learning"
            )
            self.agent = QLearningAgent(state_dim, action_dim, config)
        
        # Training state
        self.total_episodes = 0
        self.total_steps = 0
        self.is_training = False
        
        # Metrics
        self.metrics_history: List[Dict[str, float]] = []
    
    def trajectory_to_experiences(
        self,
        trajectory: ReasoningTrajectory,
    ) -> List[RLExperience]:
        """
        Convert a reasoning trajectory to RL experiences.
        
        This is a simple conversion that treats each reasoning step as a state.
        In practice, you'd want more sophisticated state representation.
        
        Args:
            trajectory: A completed reasoning trajectory
            
        Returns:
            List of RL experiences
        """
        experiences = []
        steps = trajectory.steps
        
        for i in range(len(steps) - 1):
            current_step = steps[i]
            next_step = steps[i + 1]
            
            # Create state from step
            state = RLState(
                features=self._encode_step(current_step),
                context={
                    "step_number": current_step.step_number,
                    "action": current_step.action,
                },
            )
            
            # Create next state
            next_state = RLState(
                features=self._encode_step(next_step),
                context={
                    "step_number": next_step.step_number,
                    "action": next_step.action_taken,
                },
            )
            
            # Create action
            action = RLAction(
                action_id=str(hash(current_step.action) % self.action_dim),
                action_type=current_step.action,
                parameters={},
                confidence=1.0,
            )
            
            # Calculate reward
            # Simple reward: +1 for success, -1 for failure, small positive for progress
            if i == len(steps) - 2:  # Last step before final result
                reward = 1.0 if trajectory.success else -1.0
            else:
                reward = 0.1  # Small reward for making progress
            
            experience = RLExperience(
                state=state,
                action=action,
                reward=reward,
                next_state=next_state,
                done=(i == len(steps) - 2),
                trajectory_id=trajectory.id,
            )
            experiences.append(experience)
        
        return experiences
    
    def _encode_step(self, step: Any) -> NDArray:
        """
        Encode a reasoning step into a feature vector.
        
        This is a simple encoding - in practice, use proper embeddings.
        """
        # Simple feature extraction
        features = np.zeros(self.state_dim)
        
        # Encode step number (normalized)
        features[0] = step.step_number / 100.0
        
        # Encode action type (hash-based)
        action_hash = hash(step.action_taken) % 1000
        features[1] = action_hash / 1000.0
        
        # Encode thought length (normalized)
        thought_len = len(getattr(step, 'thought', ''))
        features[2] = min(thought_len / 1000.0, 1.0)
        
        # Add some randomness for diversity (remove in production)
        features[3:10] = np.random.randn(7) * 0.1
        
        return features
    
    async def add_trajectory(self, trajectory: ReasoningTrajectory) -> int:
        """
        Add a trajectory to the replay buffer.
        
        Args:
            trajectory: Completed trajectory to learn from
            
        Returns:
            Number of experiences added
        """
        experiences = self.trajectory_to_experiences(trajectory)
        
        for exp in experiences:
            self.buffer.add(exp)
        
        self.total_episodes += 1
        logger.debug(f"Added {len(experiences)} experiences from trajectory {trajectory.id}")
        
        return len(experiences)
    
    async def train_step(self, batch_size: Optional[int] = None) -> Optional[Dict[str, float]]:
        """
        Perform one training step.
        
        Args:
            batch_size: Batch size for training (uses config default if None)
            
        Returns:
            Training metrics or None if not enough samples
        """
        if self.agent is None:
            logger.warning("No agent initialized, cannot train")
            return None
        
        batch_size = batch_size or self.config.batch_size
        
        if not self.buffer.is_ready(min_size=batch_size):
            logger.debug(f"Not enough samples ({len(self.buffer)} < {batch_size})")
            return None
        
        # Sample batch
        batch = self.buffer.sample(batch_size)
        
        # Train on batch
        metrics = self.agent.train_episode(batch)
        
        self.total_steps += 1
        self.metrics_history.append(metrics)
        
        # Keep only recent metrics
        if len(self.metrics_history) > 1000:
            self.metrics_history = self.metrics_history[-1000:]
        
        return metrics
    
    async def train(
        self,
        num_steps: int = 100,
        batch_size: Optional[int] = None,
    ) -> List[Dict[str, float]]:
        """
        Train for multiple steps.
        
        Args:
            num_steps: Number of training steps
            batch_size: Batch size for each step
            
        Returns:
            List of metrics from each step
        """
        self.is_training = True
        all_metrics = []
        
        try:
            for step in range(num_steps):
                metrics = await self.train_step(batch_size)
                if metrics:
                    all_metrics.append(metrics)
                    
                    # Log progress
                    if (step + 1) % 10 == 0:
                        avg_reward = np.mean([m["episode_reward"] for m in all_metrics[-10:]])
                        logger.info(f"Training step {step + 1}/{num_steps}, avg reward: {avg_reward:.3f}")
                
                # Small delay to prevent blocking
                if step % 50 == 0:
                    await asyncio.sleep(0)
        finally:
            self.is_training = False
        
        return all_metrics
    
    def get_policy(self) -> Optional[RLPolicy]:
        """
        Get the current policy.
        
        Returns:
            RLPolicy object or None if not trained
        """
        if self.agent is None:
            return None
        
        # Create policy from agent's Q-table
        weights = {
            "q_table_size": np.array([len(self.agent.q_table)]),
            "epsilon": np.array([self.agent.epsilon]),
        }
        
        # Calculate average reward
        avg_reward = 0.0
        if self.agent.episode_rewards:
            avg_reward = np.mean(self.agent.episode_rewards[-100:])
        
        return RLPolicy(
            algorithm=self.config.algorithm,
            weights=weights,
            hyperparameters={
                "learning_rate": self.config.learning_rate,
                "gamma": self.config.gamma,
                "epsilon": self.agent.epsilon,
            },
            version=self.total_episodes,
            training_episodes=self.total_episodes,
            average_reward=avg_reward,
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get training statistics."""
        return {
            "total_episodes": self.total_episodes,
            "total_steps": self.total_steps,
            "buffer_size": len(self.buffer),
            "is_training": self.is_training,
            "algorithm": self.config.algorithm.value,
            "agent_type": type(self.agent).__name__ if self.agent else None,
            "recent_rewards": (
                self.agent.episode_rewards[-10:] if self.agent else []
            ),
            "mean_recent_reward": (
                np.mean(self.agent.episode_rewards[-100:]) if self.agent and self.agent.episode_rewards else 0.0
            ),
        }


# Simple factory function
def create_rl_trainer(
    algorithm: RLAlgorithmType = RLAlgorithmType.Q_LEARNING,
    state_dim: int = 128,
    action_dim: int = 10,
    **kwargs
) -> RLTrainer:
    """
    Create an RL trainer with the specified algorithm.
    
    Args:
        algorithm: RL algorithm to use
        state_dim: Dimension of state space
        action_dim: Dimension of action space
        **kwargs: Additional config parameters
        
    Returns:
        Configured RLTrainer instance
    """
    config = RLConfig(algorithm=algorithm, **kwargs)
    return RLTrainer(config=config, state_dim=state_dim, action_dim=action_dim)
