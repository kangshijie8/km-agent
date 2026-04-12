"""
Delegate Adapter - 将Cognitive Core的55种专家代理与Kunming现有的delegate_tool整合
消除重复：Kunming有基础subagent，Cognitive Core有55种专家类型，合并为智能路由
"""

import json
import asyncio
import logging
import threading
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class TaskComplexity(Enum):
    """任务复杂度级别"""
    SIMPLE = "simple"           # 单工具调用
    MODERATE = "moderate"       # 多步骤，单领域
    COMPLEX = "complex"         # 跨领域协调
    RESEARCH = "research"       # 需要深入研究


@dataclass
class TaskAnalysis:
    """任务分析结果"""
    complexity: TaskComplexity
    required_expertise: List[str]
    estimated_steps: int
    can_parallelize: bool
    recommended_agents: List[str]


class SmartDelegator:
    """
    智能委托器 - 结合Kunming的delegate_tool和Cognitive Core的AgentFactory
    
    消除重复实现：
    - Kunming原有：基础subagent（并行执行，max 3）
    - Cognitive Core新增：55种专家类型，智能任务分配
    - 合并后：根据任务复杂度自动选择最佳策略
    """
    
    def __init__(self):
        self._agent_factory = None
        self._max_parallel = 3  # Kunming的限制
        self._initialized = False
        self._lock = threading.Lock()
    
    async def initialize(self) -> None:
        """初始化智能委托器"""
        if self._initialized:
            return
        
        try:
            from ..experts.agent_factory import AgentFactory
            
            self._agent_factory = AgentFactory()
            await self._agent_factory.initialize()
            
            self._initialized = True
        except ImportError as e:
            logger.warning(f"AgentFactory not available: {e}")
            # 初始化失败但标记为已初始化以避免重复尝试
            self._initialized = True
        except Exception as e:
            logger.error(f"Failed to initialize SmartDelegator: {e}")
            raise
    
    async def delegate(
        self,
        task: str,
        context: Optional[str] = None,
        use_swarm: bool = False
    ) -> Dict[str, Any]:
        """
        智能委托任务
        
        策略：
        1. 分析任务复杂度
        2. 选择执行策略（单代理/并行/蜂群）
        3. 执行并返回结果
        
        Args:
            task: 任务描述
            context: 上下文信息
            use_swarm: 是否使用蜂群协调
        
        Returns:
            执行结果
        """
        try:
            # 1. 分析任务
            analysis = await self._analyze_task(task, context)
            
            # 2. 根据复杂度选择策略
            if analysis.complexity == TaskComplexity.SIMPLE:
                return await self._execute_simple(task, context)
            
            elif analysis.complexity == TaskComplexity.MODERATE:
                return await self._execute_moderate(task, context, analysis)
            
            elif analysis.complexity in (TaskComplexity.COMPLEX, TaskComplexity.RESEARCH):
                if use_swarm:
                    return await self._execute_swarm(task, context, analysis)
                else:
                    return await self._execute_complex(task, context, analysis)
            
            return {"error": "Unknown task complexity"}
        except Exception as e:
            logger.error(f"Delegate failed: {e}", exc_info=True)
            return {"error": str(e)}
    
    async def _analyze_task(
        self,
        task: str,
        context: Optional[str]
    ) -> TaskAnalysis:
        """分析任务复杂度"""
        task_lower = task.lower()
        
        # 关键词匹配判断复杂度
        research_keywords = ['研究', 'research', '调查', 'investigate', '分析', 'analyze']
        complex_keywords = ['协调', 'coordinate', '架构', 'architecture', '设计', 'design']
        simple_keywords = ['查找', 'find', '搜索', 'search', '读取', 'read']
        
        # 判断复杂度
        if any(kw in task_lower for kw in research_keywords):
            complexity = TaskComplexity.RESEARCH
        elif any(kw in task_lower for kw in complex_keywords):
            complexity = TaskComplexity.COMPLEX
        elif any(kw in task_lower for kw in simple_keywords):
            complexity = TaskComplexity.SIMPLE
        else:
            complexity = TaskComplexity.MODERATE
        
        # 判断所需专长
        expertise = []
        if any(kw in task_lower for kw in ['code', '代码', 'program', '程序']):
            expertise.extend(['coder', 'reviewer'])
        if any(kw in task_lower for kw in ['test', '测试', 'bug', 'fix']):
            expertise.append('tester')
        if any(kw in task_lower for kw in ['doc', '文档', 'write', '写作']):
            expertise.append('documenter')
        if any(kw in task_lower for kw in ['plan', '计划', '设计', 'design']):
            expertise.append('architect')
        
        if not expertise:
            expertise = ['coder']  # 默认
        
        # 估计步骤数
        if complexity == TaskComplexity.SIMPLE:
            steps = 1
        elif complexity == TaskComplexity.MODERATE:
            steps = 3
        else:
            steps = 5
        
        return TaskAnalysis(
            complexity=complexity,
            required_expertise=expertise,
            estimated_steps=steps,
            can_parallelize=len(expertise) > 1,
            recommended_agents=expertise[:self._max_parallel]
        )
    
    async def _execute_simple(
        self,
        task: str,
        context: Optional[str]
    ) -> Dict[str, Any]:
        """执行简单任务 - 使用单个专家代理"""
        if not self._agent_factory:
            return {"error": "Agent factory not initialized"}
        
        try:
            # 创建单个coder代理
            from ..experts.types import AgentConfig, AgentType
            
            config = AgentConfig(
                agent_type=AgentType.CODER,
                name="simple_executor",
                capabilities=["code", "debug"]
            )
            
            result = await self._agent_factory.spawn_agent(config)
            
            if result.status == "active":
                # 分配任务
                from ..experts.types import TaskAssignment
                
                task_assign = TaskAssignment(
                    task_id=f"simple_{id(task)}",
                    agent_id=result.agent_id,
                    description=task,
                    context=context or ""
                )
                
                task_result = await self._agent_factory.assign_task(task_assign)
                
                # 清理代理
                await self._agent_factory.terminate_agent(result.agent_id)
                
                return {
                    "strategy": "single_agent",
                    "agent_type": "coder",
                    "result": task_result
                }
            
            return {"error": "Failed to spawn agent"}
        except Exception as e:
            logger.error(f"Execute simple failed: {e}")
            return {"error": f"Execute simple failed: {e}"}
    
    async def _execute_moderate(
        self,
        task: str,
        context: Optional[str],
        analysis: TaskAnalysis
    ) -> Dict[str, Any]:
        """执行中等复杂度任务 - 并行使用多个专家"""
        if not self._agent_factory:
            return {"error": "Agent factory not initialized"}
        
        try:
            from ..experts.types import AgentConfig, AgentType, TaskAssignment
            
            # 并行创建多个代理
            agents = []
            for exp in analysis.recommended_agents[:self._max_parallel]:
                try:
                    agent_type = getattr(AgentType, exp.upper(), AgentType.CODER)
                    config = AgentConfig(
                        agent_type=agent_type,
                        name=f"moderate_{exp}",
                        capabilities=[exp]
                    )
                    
                    result = await self._agent_factory.spawn_agent(config)
                    if result.status == "active":
                        agents.append((result.agent_id, exp))
                except Exception as e:
                    logger.warning(f"Failed to spawn agent {exp}: {e}")
            
            if not agents:
                return {"error": "Failed to spawn any agents"}
            
            # 并行分配任务
            async def execute_agent(agent_id: str, exp: str):
                try:
                    task_assign = TaskAssignment(
                        task_id=f"moderate_{agent_id}",
                        agent_id=agent_id,
                        description=f"[{exp}] {task}",
                        context=context or ""
                    )
                    return await self._agent_factory.assign_task(task_assign)
                except Exception as e:
                    logger.error(f"Agent {exp} execution failed: {e}")
                    return {"error": str(e)}
            
            results = await asyncio.gather(*[
                execute_agent(aid, exp) for aid, exp in agents
            ], return_exceptions=True)
            
            # 清理代理
            for agent_id, _ in agents:
                try:
                    await self._agent_factory.terminate_agent(agent_id)
                except Exception as e:
                    logger.warning(f"Failed to terminate agent {agent_id}: {e}")
            
            # 过滤掉异常结果
            valid_results = [r for r in results if not isinstance(r, Exception)]
            
            return {
                "strategy": "parallel_agents",
                "agent_count": len(agents),
                "agent_types": [exp for _, exp in agents],
                "results": valid_results
            }
        except Exception as e:
            logger.error(f"Execute moderate failed: {e}")
            return {"error": f"Execute moderate failed: {e}"}
    
    async def _execute_complex(
        self,
        task: str,
        context: Optional[str],
        analysis: TaskAnalysis
    ) -> Dict[str, Any]:
        """执行复杂任务 - 使用协调器代理管理"""
        try:
            # 使用Cognitive Core的协调器代理
            from ..experts.types import AgentConfig, AgentType, TaskAssignment
            
            config = AgentConfig(
                agent_type=AgentType.HIERARCHICAL_COORDINATOR,
                name="complex_coordinator",
                capabilities=["coordination", "planning"]
            )
            
            result = await self._agent_factory.spawn_agent(config)
            
            if result.status == "active":
                # 协调器会自己创建子代理
                task_assign = TaskAssignment(
                    task_id=f"complex_{id(task)}",
                    agent_id=result.agent_id,
                    description=task,
                    context=context or "",
                    subtasks=[
                        {"description": f"分析: {task}", "assigned_type": "analyst"},
                        {"description": f"实现: {task}", "assigned_type": "coder"},
                        {"description": f"验证: {task}", "assigned_type": "tester"}
                    ]
                )
                
                task_result = await self._agent_factory.assign_task(task_assign)
                
                await self._agent_factory.terminate_agent(result.agent_id)
                
                return {
                    "strategy": "coordinated",
                    "coordinator": "hierarchical",
                    "result": task_result
                }
            
            return {"error": "Failed to spawn coordinator"}
        except Exception as e:
            logger.error(f"Execute complex failed: {e}")
            return {"error": f"Execute complex failed: {e}"}
    
    async def _execute_swarm(
        self,
        task: str,
        context: Optional[str],
        analysis: TaskAnalysis
    ) -> Dict[str, Any]:
        """使用蜂群系统执行任务"""
        try:
            from ..swarm.queen_coordinator import QueenCoordinator
            
            queen = QueenCoordinator()
            await queen.initialize()
            
            # 注册蜂群代理
            from ..experts.types import AgentType
            
            for exp in analysis.recommended_agents:
                try:
                    agent_type = getattr(AgentType, exp.upper(), AgentType.CODER)
                    await queen.register_agent(
                        agent_id=f"swarm_{exp}_{id(task)}",
                        agent_type=agent_type.value
                    )
                except Exception as e:
                    logger.warning(f"Failed to register agent {exp}: {e}")
            
            # 分配任务
            allocation = await queen.allocate_task(task)
            
            return {
                "strategy": "swarm",
                "topology": allocation.topology.value,
                "assigned_agents": allocation.agent_ids,
                "estimated_duration": allocation.estimated_duration
            }
        except Exception as e:
            logger.error(f"Execute swarm failed: {e}")
            return {"error": f"Execute swarm failed: {e}"}


# 全局单例
_smart_delegator: Optional[SmartDelegator] = None
_lock = threading.Lock()


def get_smart_delegator() -> SmartDelegator:
    """获取智能委托器单例（线程安全）"""
    global _smart_delegator
    if _smart_delegator is None:
        with _lock:
            if _smart_delegator is None:
                _smart_delegator = SmartDelegator()
    return _smart_delegator
