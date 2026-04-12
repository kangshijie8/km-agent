"""
Cognitive Core Neural Learning System - Python Implementation

Self-optimizing neural architecture (SONA) with 9 reinforcement learning
algorithms and ReasoningBank for trajectory storage.

This module provides:
- ReasoningBank for trajectory storage and retrieval
- 9 RL algorithms (PPO, DQN, A2C, Decision Transformer, Q-Learning, SARSA, SAC, TD3, Rainbow)
- SONA (Self-Optimizing Neural Architecture)
- Pattern learning from trajectories
- Curiosity-driven exploration

Integration with Kunming:
    The learning system enhances Kunming's existing skill creation and
    trajectory compression with structured learning capabilities.
    It enables:
    - Automatic skill generation from successful trajectories
    - RL-based decision optimization
    - Pattern recognition across sessions
    - Self-improvement through experience

Example:
    ```python
    from agent.cognitive.neural import (
        ReasoningBank, ReasoningBankConfig,
        NeuralLearningConfig, RLAlgorithmType
    )
    
    # Initialize ReasoningBank
    bank = ReasoningBank(ReasoningBankConfig())
    await bank.initialize()
    
    # Store trajectory
    from agent.cognitive.neural.types import (
        ReasoningTrajectory, ReasoningStep
    )
    trajectory = ReasoningTrajectory(
        id="traj-1",
        task_id="task-1",
        agent_id="agent-1",
        steps=[...],
        final_result="Success",
        success=True,
        total_steps=5,
        total_time_ms=1000
    )
    await bank.store(trajectory)
    
    # Search similar trajectories
    results = await bank.search_similar(query_embedding, k=5)
    ```

Based on: @claude-flow/neural V3.5
"""

# ===== Types =====
from .types import (
    # RL Algorithms
    RLAlgorithmType,
    SONAArchitectureType, OptimizationTarget,
    
    # Data Classes
    ReasoningStep, ReasoningTrajectory, Pattern,
    RLState, RLAction, RLExperience, RLPolicy,
    SONAModel, OptimizationResult,
    LearningMetrics, CuriosityState,
    
    # Config
    ReasoningBankConfig, PatternLearnerConfig,
    RLConfig, SONAConfig, NeuralLearningConfig,
    
    # Utilities
    generate_trajectory_id, generate_pattern_id, generate_model_id,
    calculate_similarity, get_rl_algorithm_description,
    get_all_rl_algorithms, is_valid_rl_algorithm,
)

# ===== ReasoningBank =====
from .reasoning_bank import (
    ReasoningBank,
    TrajectorySearchResult,
    create_reasoning_bank,
    create_compressed_bank,
)

# ===== Version =====
__version__ = "3.5.0"

# ===== Exports =====
__all__ = [
    # RL Algorithms
    "RLAlgorithmType",
    "SONAArchitectureType", "OptimizationTarget",
    
    # Data Classes
    "ReasoningStep", "ReasoningTrajectory", "Pattern",
    "RLState", "RLAction", "RLExperience", "RLPolicy",
    "SONAModel", "OptimizationResult",
    "LearningMetrics", "CuriosityState",
    
    # Config
    "ReasoningBankConfig", "PatternLearnerConfig",
    "RLConfig", "SONAConfig", "NeuralLearningConfig",
    
    # ReasoningBank
    "ReasoningBank", "TrajectorySearchResult",
    "create_reasoning_bank", "create_compressed_bank",
    
    # Utilities
    "generate_trajectory_id", "generate_pattern_id", "generate_model_id",
    "calculate_similarity", "get_rl_algorithm_description",
    "get_all_rl_algorithms", "is_valid_rl_algorithm",
]
