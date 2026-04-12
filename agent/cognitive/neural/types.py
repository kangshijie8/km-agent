"""
Cognitive Core Neural Learning System Types - Python Implementation

Type definitions for self-optimizing neural architecture (SONA) with
9 reinforcement learning algorithms and ReasoningBank for trajectory storage.

Based on: @claude-flow/neural/src/index.ts
"""

from typing import Dict, List, Optional, Any, Callable, Tuple, Union, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from numpy.typing import NDArray
import numpy as np


# ===== RL Algorithm Types =====

class RLAlgorithmType(Enum):
    """Reinforcement learning algorithm types"""
    PPO = "ppo"                        # Proximal Policy Optimization
    DQN = "dqn"                        # Deep Q-Network
    A2C = "a2c"                        # Advantage Actor-Critic
    DECISION_TRANSFORMER = "decision_transformer"
    Q_LEARNING = "q_learning"          # Q-Learning
    SARSA = "sarsa"                    # State-Action-Reward-State-Action
    SAC = "sac"                        # Soft Actor-Critic
    TD3 = "td3"                        # Twin Delayed Deep Deterministic Policy Gradient
    RAINBOW = "rainbow"                # Rainbow DQN


# ===== SONA Types =====

class SONAArchitectureType(Enum):
    """SONA architecture types"""
    FEEDFORWARD = "feedforward"
    RECURRENT = "recurrent"
    TRANSFORMER = "transformer"
    ATTENTION = "attention"
    HYBRID = "hybrid"


class OptimizationTarget(Enum):
    """Optimization targets for SONA"""
    PERFORMANCE = "performance"
    ACCURACY = "accuracy"
    LATENCY = "latency"
    MEMORY = "memory"
    ENERGY = "energy"
    BALANCED = "balanced"


# ===== Data Classes =====

@dataclass
class ReasoningStep:
    """Single reasoning step in trajectory"""
    step_number: int
    input_data: str
    thought_process: str
    action_taken: str
    output_result: str
    confidence: float
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReasoningTrajectory:
    """Complete reasoning trajectory"""
    id: str
    task_id: str
    agent_id: str
    steps: List[ReasoningStep]
    final_result: str
    success: bool
    total_steps: int
    total_time_ms: float
    created_at: float = field(default_factory=lambda: datetime.now().timestamp())
    tags: List[str] = field(default_factory=list)
    embedding: Optional[NDArray] = None


@dataclass
class Pattern:
    """Learned pattern from trajectories"""
    id: str
    name: str
    description: str
    pattern_type: str
    frequency: int
    confidence: float
    examples: List[str]
    embedding: NDArray
    created_at: float = field(default_factory=lambda: datetime.now().timestamp())
    last_matched_at: Optional[float] = None
    match_count: int = 0


@dataclass
class RLState:
    """State representation for RL"""
    features: NDArray
    context: Dict[str, Any]
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())


@dataclass
class RLAction:
    """Action representation for RL"""
    action_id: str
    action_type: str
    parameters: Dict[str, Any]
    confidence: float = 1.0


@dataclass
class RLExperience:
    """Single RL experience tuple"""
    state: RLState
    action: RLAction
    reward: float
    next_state: RLState
    done: bool
    trajectory_id: Optional[str] = None


@dataclass
class RLPolicy:
    """RL policy"""
    algorithm: RLAlgorithmType
    weights: Dict[str, NDArray]
    hyperparameters: Dict[str, Any]
    version: int = 1
    created_at: float = field(default_factory=lambda: datetime.now().timestamp())
    training_episodes: int = 0
    average_reward: float = 0.0


@dataclass
class SONAModel:
    """SONA model configuration"""
    id: str
    architecture_type: SONAArchitectureType
    layers: List[Dict[str, Any]]
    parameters: Dict[str, NDArray]
    optimization_target: OptimizationTarget
    version: int = 1
    created_at: float = field(default_factory=lambda: datetime.now().timestamp())
    last_optimized_at: Optional[float] = None
    performance_score: float = 0.0


@dataclass
class OptimizationResult:
    """Result of SONA optimization"""
    success: bool
    model_id: str
    previous_score: float
    new_score: float
    improvement_percent: float
    changes_made: List[str]
    duration_ms: float
    error: Optional[str] = None


@dataclass
class LearningMetrics:
    """Metrics for learning system"""
    total_trajectories: int = 0
    total_patterns: int = 0
    total_episodes: int = 0
    average_reward: float = 0.0
    policy_updates: int = 0
    model_optimizations: int = 0
    cache_hit_rate: float = 0.0


@dataclass
class CuriosityState:
    """State for curiosity-driven exploration"""
    novelty_score: float
    exploration_bonus: float
    visited_states: Set[str]
    state_visits: Dict[str, int]


# ===== Configuration Classes =====

@dataclass
class ReasoningBankConfig:
    """Configuration for ReasoningBank"""
    max_trajectories: int = 10000
    embedding_dimensions: int = 1536
    similarity_threshold: float = 0.85
    enable_compression: bool = True
    compression_ratio: float = 0.5


@dataclass
class PatternLearnerConfig:
    """Configuration for PatternLearner"""
    min_pattern_frequency: int = 3
    min_pattern_confidence: float = 0.7
    max_patterns: int = 1000
    pattern_ttl_days: int = 30
    enable_embedding: bool = True


@dataclass
class RLConfig:
    """Configuration for RL algorithms"""
    algorithm: RLAlgorithmType = RLAlgorithmType.PPO
    learning_rate: float = 0.0003
    gamma: float = 0.99  # Discount factor
    epsilon: float = 0.1  # Exploration rate
    batch_size: int = 64
    buffer_size: int = 100000
    update_frequency: int = 100


@dataclass
class SONAConfig:
    """Configuration for SONA"""
    architecture_type: SONAArchitectureType = SONAArchitectureType.HYBRID
    optimization_target: OptimizationTarget = OptimizationTarget.BALANCED
    auto_optimize: bool = True
    optimization_interval: int = 100
    max_layers: int = 10
    min_layers: int = 2


@dataclass
class NeuralLearningConfig:
    """Configuration for NeuralLearningCore"""
    reasoning_bank: ReasoningBankConfig = field(default_factory=ReasoningBankConfig)
    pattern_learner: PatternLearnerConfig = field(default_factory=PatternLearnerConfig)
    rl: RLConfig = field(default_factory=RLConfig)
    sona: SONAConfig = field(default_factory=SONAConfig)
    enable_curiosity: bool = True
    enable_meta_learning: bool = True


# ===== Utility Functions =====

def generate_trajectory_id() -> str:
    """Generate unique trajectory ID"""
    import uuid
    return f"traj_{uuid.uuid4().hex[:16]}"


def generate_pattern_id() -> str:
    """Generate unique pattern ID"""
    import uuid
    return f"pat_{uuid.uuid4().hex[:16]}"


def generate_model_id() -> str:
    """Generate unique model ID"""
    import uuid
    return f"model_{uuid.uuid4().hex[:16]}"


def calculate_similarity(embedding1: NDArray, embedding2: NDArray) -> float:
    """Calculate cosine similarity between embeddings"""
    dot = float(np.dot(embedding1, embedding2))
    norm1 = float(np.linalg.norm(embedding1))
    norm2 = float(np.linalg.norm(embedding2))
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    return dot / (norm1 * norm2)


def get_rl_algorithm_description(algorithm: RLAlgorithmType) -> str:
    """Get description for RL algorithm"""
    descriptions = {
        RLAlgorithmType.PPO: "Proximal Policy Optimization - stable and sample efficient",
        RLAlgorithmType.DQN: "Deep Q-Network - value-based method for discrete actions",
        RLAlgorithmType.A2C: "Advantage Actor-Critic - combines value and policy gradients",
        RLAlgorithmType.DECISION_TRANSFORMER: "Decision Transformer - sequence modeling for RL",
        RLAlgorithmType.Q_LEARNING: "Q-Learning - classic temporal difference learning",
        RLAlgorithmType.SARSA: "SARSA - on-policy temporal difference learning",
        RLAlgorithmType.SAC: "Soft Actor-Critic - maximum entropy RL",
        RLAlgorithmType.TD3: "Twin Delayed DDPG - continuous action space RL",
        RLAlgorithmType.RAINBOW: "Rainbow DQN - combines 6 DQN improvements",
    }
    return descriptions.get(algorithm, "Unknown algorithm")


def get_all_rl_algorithms() -> List[RLAlgorithmType]:
    """Get all available RL algorithms"""
    return list(RLAlgorithmType)


def is_valid_rl_algorithm(algorithm: str) -> bool:
    """Check if RL algorithm is valid"""
    try:
        RLAlgorithmType(algorithm)
        return True
    except ValueError:
        return False
