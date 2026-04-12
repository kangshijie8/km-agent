"""
Learning Adapter - 将Cognitive Core的SONA学习系统与Kunming现有的skill_manage整合
消除重复：Kunming有技能创建，Cognitive Core有SONA+9种RL算法，合并为智能学习
"""

import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from kunming_constants import get_kunming_home


@dataclass
class LearningConfig:
    """学习配置"""
    enable_trajectory_learning: bool = True
    enable_skill_optimization: bool = True
    enable_pattern_prediction: bool = True
    rl_algorithm: str = "ppo"  # ppo, dqn, a2c, etc.
    learning_rate: float = 0.001
    batch_size: int = 32


class UnifiedLearningSystem:
    """
    统一学习系统 - 结合Kunming的skill_manage和Cognitive Core的SONA
    
    消除重复实现：
    - Kunming原有：skill_manage工具（创建技能）、trajectory_compressor（轨迹压缩）
    - Cognitive Core新增：SONA管理器、ReasoningBank、9种RL算法
    - 合并后：智能学习循环，自动优化技能和策略
    """
    
    def __init__(self, config: Optional[LearningConfig] = None):
        self.config = config or LearningConfig()
        self._reasoning_bank = None
        self._sona_manager = None
        self._initialized = False
        
        # Kunming原有技能目录
        self._skills_dir = get_kunming_home() / "skills"
        self._skills_dir.mkdir(parents=True, exist_ok=True)
    
    async def initialize(self) -> None:
        """初始化统一学习系统"""
        if self._initialized:
            return
        
        # 初始化Cognitive Core的ReasoningBank
        from ..neural.reasoning_bank import ReasoningBank
        self._reasoning_bank = ReasoningBank()
        await self._reasoning_bank.initialize()
        
        self._initialized = True
    
    async def learn_from_trajectory(
        self,
        trajectory: Dict[str, Any],
        task_type: str = "general"
    ) -> Dict[str, Any]:
        """
        从轨迹学习 - 整合Kunming的轨迹压缩和Cognitive Core的SONA
        
        Args:
            trajectory: 执行轨迹
            task_type: 任务类型
        
        Returns:
            学习结果
        """
        results = {
            "stored_in_reasoning_bank": False,
            "patterns_extracted": 0,
            "skill_suggested": None,
            "optimizations": []
        }
        
        # 1. 存入ReasoningBank（Cognitive Core）
        if self._reasoning_bank and self.config.enable_trajectory_learning:
            from ..neural.types import ReasoningTrajectory
            
            rt = ReasoningTrajectory(
                id=f"traj_{datetime.now().timestamp()}",
                prompt=trajectory.get("prompt", ""),
                steps=trajectory.get("steps", []),
                outcome=trajectory.get("outcome", {}),
                metadata={
                    "task_type": task_type,
                    "timestamp": datetime.now().isoformat()
                }
            )
            
            await self._reasoning_bank.store(rt)
            results["stored_in_reasoning_bank"] = True
        
        # 2. 提取模式并建议技能（Kunming原有逻辑增强）
        if self.config.enable_skill_optimization:
            skill_suggestion = await self._suggest_skill(trajectory, task_type)
            if skill_suggestion:
                results["skill_suggested"] = skill_suggestion
        
        # 3. 使用RL优化策略（Cognitive Core新增）
        if self.config.enable_pattern_prediction:
            optimizations = await self._optimize_strategy(trajectory)
            results["optimizations"] = optimizations
        
        return results
    
    async def _suggest_skill(
        self,
        trajectory: Dict[str, Any],
        task_type: str
    ) -> Optional[Dict[str, Any]]:
        """
        基于轨迹建议新技能
        
        这是Kunming原有skill_manage的增强版
        """
        steps = trajectory.get("steps", [])
        
        # 简单启发式：如果步骤数>3且成功，建议创建技能
        if len(steps) >= 3 and trajectory.get("outcome", {}).get("success", False):
            # 提取通用模式
            pattern = self._extract_pattern(steps)
            
            if pattern:
                skill_name = f"auto_skill_{task_type}_{datetime.now().strftime('%Y%m%d')}"
                
                return {
                    "name": skill_name,
                    "description": f"Auto-generated skill for {task_type}",
                    "pattern": pattern,
                    "confidence": min(len(steps) * 0.2, 0.9),
                    "save_path": str(self._skills_dir / f"{skill_name}.json")
                }
        
        return None
    
    def _extract_pattern(self, steps: List[Dict[str, Any]]) -> Optional[str]:
        """从步骤中提取可复用模式"""
        if not steps:
            return None
        
        # 提取工具调用序列
        tool_sequence = []
        for step in steps:
            if "tool" in step:
                tool_sequence.append(step["tool"])
        
        if len(tool_sequence) >= 2:
            return " -> ".join(tool_sequence)
        
        return None
    
    async def _optimize_strategy(
        self,
        trajectory: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        使用RL优化策略（Cognitive Core新增）
        
        基于历史轨迹学习最优策略
        """
        optimizations = []
        
        # 搜索相似轨迹
        if self._reasoning_bank:
            # 使用轨迹提示作为查询
            query = trajectory.get("prompt", "")
            
            # 生成简单embedding（实际应使用真实embedding模型）
            query_embedding = self._simple_embed(query)
            
            similar = await self._reasoning_bank.search_similar(
                query_embedding=query_embedding,
                k=5
            )
            
            # 分析相似轨迹，找出更优路径
            for traj_result in similar:
                traj = traj_result.trajectory
                
                # 比较步骤数
                current_steps = len(trajectory.get("steps", []))
                similar_steps = len(traj.steps)
                
                if similar_steps < current_steps and traj.outcome.get("success"):
                    optimizations.append({
                        "type": "shorter_path",
                        "description": f"Found shorter path ({similar_steps} vs {current_steps} steps)",
                        "reference_trajectory": traj.id,
                        "confidence": traj_result.similarity_score
                    })
        
        return optimizations
    
    def _simple_embed(self, text: str) -> Any:
        """简单文本嵌入（生产环境应使用真实模型）"""
        import numpy as np
        
        # 使用字符频率作为简单特征
        features = np.zeros(128, dtype=np.float32)
        for char in text.lower():
            idx = ord(char) % 128
            features[idx] += 1
        
        # 归一化
        norm = np.linalg.norm(features)
        if norm > 0:
            features = features / norm
        
        return features
    
    async def create_skill(
        self,
        name: str,
        description: str,
        content: str,
        auto_improve: bool = True
    ) -> Dict[str, Any]:
        """
        创建技能 - 整合Kunming的skill格式和Cognitive Core的学习优化
        
        Args:
            name: 技能名称
            description: 技能描述
            content: 技能内容
            auto_improve: 是否启用自动改进
        
        Returns:
            创建结果
        """
        skill_data = {
            "name": name,
            "description": description,
            "content": content,
            "created_at": datetime.now().isoformat(),
            "version": "1.0.0",
            "auto_improve": auto_improve,
            "usage_count": 0,
            "success_rate": 1.0
        }
        
        # 保存技能文件
        skill_path = self._skills_dir / f"{name}.json"
        
        with open(skill_path, 'w', encoding='utf-8') as f:
            json.dump(skill_data, f, indent=2, ensure_ascii=False)
        
        result = {
            "success": True,
            "skill_path": str(skill_path),
            "skill_name": name
        }
        
        # 如果启用自动改进，存入ReasoningBank
        if auto_improve and self._reasoning_bank:
            from ..neural.types import ReasoningTrajectory
            
            rt = ReasoningTrajectory(
                id=f"skill_{name}",
                prompt=f"Create skill: {description}",
                steps=[{"action": "skill_creation", "content": content}],
                outcome={"success": True, "skill_name": name},
                metadata={"type": "skill", "auto_improve": True}
            )
            
            await self._reasoning_bank.store(rt)
            result["tracked_for_improvement"] = True
        
        return result
    
    async def get_learning_stats(self) -> Dict[str, Any]:
        """获取学习统计"""
        stats = {
            "skills_created": 0,
            "trajectories_learned": 0,
            "patterns_extracted": 0,
            "rl_algorithm": self.config.rl_algorithm
        }
        
        # 统计技能数量
        if self._skills_dir.exists():
            stats["skills_created"] = len(list(self._skills_dir.glob("*.json")))
        
        # 统计轨迹数量
        if self._reasoning_bank:
            # 这里应该查询ReasoningBank的统计
            stats["trajectories_learned"] = "available"
        
        return stats


# 全局单例
_unified_learning: Optional[UnifiedLearningSystem] = None


def get_unified_learning(config: Optional[LearningConfig] = None) -> UnifiedLearningSystem:
    """获取统一学习系统单例"""
    global _unified_learning
    if _unified_learning is None:
        _unified_learning = UnifiedLearningSystem(config)
    return _unified_learning
