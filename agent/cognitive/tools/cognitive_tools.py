"""
Cognitive Core Integration MCP Tools - 统一入口

提供MCP工具接口，让AI Agent可以直接调用Cognitive Core的4大系统能力
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, List
from tools.registry import registry

logger = logging.getLogger(__name__)


def _run_async(coro):
    """
    安全地运行异步协程，兼容同步和异步上下文
    
    如果当前已在事件循环中，使用当前循环；否则创建新循环
    """
    try:
        loop = asyncio.get_running_loop()
        # 已在事件循环中，使用asyncio.run_coroutine_threadsafe或确保在正确的上下文中
        if loop.is_running():
            # 在已有事件循环中，创建任务并等待
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
    except RuntimeError:
        # 没有运行的事件循环，可以安全使用asyncio.run
        pass
    
    return asyncio.run(coro)


def check_cognitive_core_requirements() -> bool:
    """检查Cognitive Core集成是否可用"""
    try:
        # 检查核心适配器模块是否可导入
        from ..adapters import get_hybrid_memory_provider
        return True
    except ImportError as e:
        logger.debug(f"Cognitive Core not available: {e}")
        return False
    except Exception as e:
        logger.warning(f"Unexpected error checking Cognitive Core: {e}")
        return False


def _validate_string_param(value: Any, param_name: str, required: bool = True, max_length: int = 10000) -> tuple[bool, str]:
    """验证字符串参数"""
    if value is None:
        if required:
            return False, f"Parameter '{param_name}' is required"
        return True, ""
    if not isinstance(value, str):
        return False, f"Parameter '{param_name}' must be a string, got {type(value).__name__}"
    if len(value) == 0 and required:
        return False, f"Parameter '{param_name}' cannot be empty"
    if len(value) > max_length:
        return False, f"Parameter '{param_name}' exceeds maximum length of {max_length}"
    return True, ""


def _validate_int_param(value: Any, param_name: str, default: int, min_val: int = 1, max_val: int = 1000) -> tuple[bool, int, str]:
    """验证整数参数"""
    if value is None:
        return True, default, ""
    try:
        int_val = int(value)
        if int_val < min_val:
            return False, default, f"Parameter '{param_name}' must be >= {min_val}"
        if int_val > max_val:
            return False, default, f"Parameter '{param_name}' must be <= {max_val}"
        return True, int_val, ""
    except (ValueError, TypeError):
        return False, default, f"Parameter '{param_name}' must be an integer"


def _validate_json_param(value: Any, param_name: str, default: Any = None) -> tuple[bool, Any, str]:
    """验证JSON字符串参数"""
    if value is None or value == "":
        return True, default or {}, ""
    if not isinstance(value, str):
        return False, default or {}, f"Parameter '{param_name}' must be a JSON string"
    try:
        parsed = json.loads(value)
        return True, parsed, ""
    except json.JSONDecodeError as e:
        return False, default or {}, f"Parameter '{param_name}' is not valid JSON: {e}"


def _validate_bool_param(value: Any, param_name: str, default: bool) -> tuple[bool, bool, str]:
    """验证布尔参数"""
    if value is None:
        return True, default, ""
    if isinstance(value, bool):
        return True, value, ""
    if isinstance(value, str):
        if value.lower() in ('true', '1', 'yes', 'on'):
            return True, True, ""
        if value.lower() in ('false', '0', 'no', 'off'):
            return True, False, ""
    return False, default, f"Parameter '{param_name}' must be a boolean"


def _safe_truncate(text: str, max_length: int = 200) -> str:
    """安全截断字符串，不破坏UTF-8多字节字符"""
    if len(text) <= max_length:
        return text
    # 在max_length处截断，确保不破坏多字节字符
    truncated = text[:max_length]
    # 如果最后一个字符是多字节字符的一部分，回退到有效边界
    while truncated and (ord(truncated[-1]) & 0xC0) == 0x80:
        truncated = truncated[:-1]
    return truncated + "..."


# ============ 记忆系统工具 ============

def cognitive_memory_search(
    query: str,
    k: int = 10,
    use_hybrid: bool = True,
    task_id: str = None
) -> str:
    """
    使用Cognitive Core增强的混合记忆搜索
    
    结合Kunming的FTS5和Cognitive Core的HNSW向量索引，提供150x-12,500x更快的语义搜索
    
    Args:
        query: 搜索查询
        k: 返回结果数量
        use_hybrid: 是否使用混合搜索（FTS5 + HNSW）
    """
    # 参数验证
    valid, error_msg = _validate_string_param(query, "query", required=True, max_length=1000)
    if not valid:
        return json.dumps({"success": False, "error": error_msg})
    
    valid, k_val, error_msg = _validate_int_param(k, "k", default=10, min_val=1, max_val=100)
    if not valid:
        return json.dumps({"success": False, "error": error_msg})
    
    valid, use_hybrid_val, error_msg = _validate_bool_param(use_hybrid, "use_hybrid", default=True)
    if not valid:
        return json.dumps({"success": False, "error": error_msg})
    
    try:
        from ..adapters import get_hybrid_memory_provider
        
        provider = get_hybrid_memory_provider()
        
        # 确保初始化
        if not provider._initialized:
            _run_async(provider.initialize())
        
        # 执行搜索
        results = _run_async(provider.search(query, k=k_val, use_hybrid=use_hybrid_val))
        
        # 格式化结果
        formatted = []
        for r in results:
            formatted.append({
                "id": r.id,
                "content": _safe_truncate(r.content, 200),
                "memory_type": r.memory_type,
                "hybrid_score": round(r.hybrid_score, 4),
                "fts_score": round(r.fts_score, 4),
                "vector_score": round(r.vector_score, 4)
            })
        
        return json.dumps({
            "success": True,
            "query": query,
            "result_count": len(formatted),
            "results": formatted
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"cognitive_memory_search failed: {e}", exc_info=True)
        return json.dumps({
            "success": False,
            "error": str(e)
        })


def cognitive_memory_store(
    content: str,
    memory_type: str = "episodic",
    metadata: str = "{}",
    task_id: str = None
) -> str:
    """
    存储记忆到Cognitive Core的统一记忆系统
    
    同时存入HNSW向量索引和持久化存储
    
    Args:
        content: 记忆内容
        memory_type: 记忆类型 (episodic/semantic/procedural/working)
        metadata: JSON格式的元数据
    """
    # 参数验证
    valid, error_msg = _validate_string_param(content, "content", required=True, max_length=100000)
    if not valid:
        return json.dumps({"success": False, "error": error_msg})
    
    valid, error_msg = _validate_string_param(memory_type, "memory_type", required=False, max_length=50)
    if not valid:
        return json.dumps({"success": False, "error": error_msg})
    
    valid, meta, error_msg = _validate_json_param(metadata, "metadata", default={})
    if not valid:
        return json.dumps({"success": False, "error": error_msg})
    
    # 验证memory_type枚举值
    valid_types = ["episodic", "semantic", "procedural", "working"]
    if memory_type not in valid_types:
        return json.dumps({
            "success": False, 
            "error": f"Invalid memory_type '{memory_type}'. Must be one of: {', '.join(valid_types)}"
        })
    
    try:
        from ..adapters import get_hybrid_memory_provider
        
        provider = get_hybrid_memory_provider()
        
        if not provider._initialized:
            _run_async(provider.initialize())
        
        memory_id = _run_async(provider.store(
            content=content,
            memory_type=memory_type,
            metadata=meta
        ))
        
        return json.dumps({
            "success": True,
            "memory_id": memory_id,
            "memory_type": memory_type
        })
        
    except Exception as e:
        logger.error(f"cognitive_memory_store failed: {e}", exc_info=True)
        return json.dumps({
            "success": False,
            "error": str(e)
        })


# ============ 专家系统工具 ============

def cognitive_core_delegate(
    task: str,
    context: str = "",
    use_swarm: bool = False,
    task_id: str = None
) -> str:
    """
    智能委托任务给Cognitive Core专家代理
    
    根据任务复杂度自动选择最佳执行策略：
    - 简单任务：单代理执行
    - 中等任务：并行多专家
    - 复杂任务：协调器管理
    - 研究任务：蜂群系统
    
    Args:
        task: 任务描述
        context: 上下文信息
        use_swarm: 是否使用蜂群协调（适合复杂研究任务）
    """
    # 参数验证
    valid, error_msg = _validate_string_param(task, "task", required=True, max_length=5000)
    if not valid:
        return json.dumps({"success": False, "error": error_msg})
    
    valid, error_msg = _validate_string_param(context, "context", required=False, max_length=10000)
    if not valid:
        return json.dumps({"success": False, "error": error_msg})
    
    valid, use_swarm_val, error_msg = _validate_bool_param(use_swarm, "use_swarm", default=False)
    if not valid:
        return json.dumps({"success": False, "error": error_msg})
    
    try:
        from ..adapters import get_smart_delegator
        
        delegator = get_smart_delegator()
        
        if not delegator._initialized:
            _run_async(delegator.initialize())
        
        result = _run_async(delegator.delegate(
            task=task,
            context=context,
            use_swarm=use_swarm_val
        ))
        
        return json.dumps({
            "success": True,
            "task": task,
            "result": result
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"cognitive_core_delegate failed: {e}", exc_info=True)
        return json.dumps({
            "success": False,
            "error": str(e)
        })


def cognitive_core_spawn_expert(
    agent_type: str,
    name: str = "",
    capabilities: str = "[]",
    task_id: str = None
) -> str:
    """
    创建Cognitive Core专家代理
    
    可用类型：coder, reviewer, tester, planner, researcher, architect,
    analyst, optimizer, documenter, monitor, security_architect 等55种
    
    Args:
        agent_type: 代理类型
        name: 代理名称（可选）
        capabilities: JSON格式的能力列表
    """
    # 参数验证
    valid, error_msg = _validate_string_param(agent_type, "agent_type", required=True, max_length=50)
    if not valid:
        return json.dumps({"success": False, "error": error_msg})
    
    valid, error_msg = _validate_string_param(name, "name", required=False, max_length=100)
    if not valid:
        return json.dumps({"success": False, "error": error_msg})
    
    valid, caps, error_msg = _validate_json_param(capabilities, "capabilities", default=[])
    if not valid:
        return json.dumps({"success": False, "error": error_msg})
    
    # 验证capabilities是列表
    if not isinstance(caps, list):
        return json.dumps({
            "success": False,
            "error": "Parameter 'capabilities' must be a JSON array"
        })
    
    try:
        from ..experts.agent_factory import AgentFactory
        from ..experts.types import AgentConfig, AgentType
        
        factory = AgentFactory()
        _run_async(factory.initialize())
        
        # 解析代理类型
        try:
            agent_type_val = agent_type.lower()
            valid_types = [CODER, REVIEWER, TESTER, PLANNER, RESEARCHER,
                          HIERARCHICAL_COORDINATOR, MESH_COORDINATOR]
            if agent_type_val not in valid_types:
                return json.dumps({
                    "success": False,
                    "error": f"Invalid agent_type '{agent_type}'. Must be one of: {', '.join(valid_types)}"
                })
        except Exception:
            return json.dumps({
                "success": False,
                "error": f"Invalid agent_type '{agent_type}'"
            })
        
        config = AgentConfig(
            agent_type=agent_type_val,
            name=name or f"{agent_type}_agent",
            capabilities=caps if caps else [agent_type]
        )
        
        result = _run_async(factory.spawn_agent(config))
        
        return json.dumps({
            "success": result.status == "active",
            "agent_id": result.agent_id,
            "agent_type": agent_type,
            "status": result.status,
            "message": result.message
        })
        
    except Exception as e:
        logger.error(f"cognitive_core_spawn_expert failed: {e}", exc_info=True)
        return json.dumps({
            "success": False,
            "error": str(e)
        })


# ============ 蜂群系统工具 ============

def cognitive_core_swarm_allocate(
    goal: str,
    topology: str = "adaptive",
    task_id: str = None
) -> str:
    """
    使用Cognitive Core蜂群系统分配任务
    
    拓扑类型：hierarchical, mesh, centralized, decentralized, hybrid, adaptive
    
    Args:
        goal: 任务目标
        topology: 蜂群拓扑结构
    """
    # 参数验证
    valid, error_msg = _validate_string_param(goal, "goal", required=True, max_length=5000)
    if not valid:
        return json.dumps({"success": False, "error": error_msg})
    
    valid, error_msg = _validate_string_param(topology, "topology", required=False, max_length=50)
    if not valid:
        return json.dumps({"success": False, "error": error_msg})
    
    try:
        from ..swarm.queen_coordinator import QueenCoordinator
        from ..swarm.types import SwarmTopology
        
        queen = QueenCoordinator()
        _run_async(queen.initialize())
        
        # 解析拓扑
        try:
            topo_enum = SwarmTopology(topology.lower())
        except ValueError:
            valid_topos = [t.value for t in SwarmTopology]
            return json.dumps({
                "success": False,
                "error": f"Invalid topology '{topology}'. Must be one of: {', '.join(valid_topos)}"
            })
        
        # 设置拓扑
        queen.config.swarm_config.topology = topo_enum
        
        allocation = _run_async(queen.allocate_task(goal))
        
        return json.dumps({
            "success": True,
            "goal": goal,
            "topology": topo_enum.value,
            "assigned_to": allocation.assigned_to,
            "priority": allocation.priority,
            "status": allocation.status
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"cognitive_core_swarm_allocate failed: {e}", exc_info=True)
        return json.dumps({
            "success": False,
            "error": str(e)
        })


def cognitive_core_hive_mind_decide(
    question: str,
    options: str = "[]",
    task_id: str = None
) -> str:
    """
    使用Cognitive Core蜂巢意识进行集体决策
    
    聚合多个专家代理的意见，达成共识决策
    
    Args:
        question: 决策问题
        options: JSON格式的选项列表
    """
    # 参数验证
    valid, error_msg = _validate_string_param(question, "question", required=True, max_length=1000)
    if not valid:
        return json.dumps({"success": False, "error": error_msg})
    
    valid, opts, error_msg = _validate_json_param(options, "options", default=[])
    if not valid:
        return json.dumps({"success": False, "error": error_msg})
    
    # 验证options是列表
    if not isinstance(opts, list):
        return json.dumps({
            "success": False,
            "error": "Parameter 'options' must be a JSON array"
        })
    
    # 默认选项
    if not opts:
        opts = ["yes", "no"]
    
    try:
        from ..swarm.queen_coordinator import QueenCoordinator
        
        queen = QueenCoordinator()
        _run_async(queen.initialize())
        
        decision = _run_async(queen.hive_mind_decide(question, opts))
        
        return json.dumps({
            "success": True,
            "question": question,
            "decision": decision.decision,
            "confidence": decision.confidence,
            "consensus_reached": decision.consensus_reached,
            "participating_agents": decision.participating_agents
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"cognitive_core_hive_mind_decide failed: {e}", exc_info=True)
        return json.dumps({
            "success": False,
            "error": str(e)
        })


# ============ 学习系统工具 ============

def cognitive_core_learn_from_trajectory(
    trajectory_json: str,
    task_type: str = "general",
    task_id: str = None
) -> str:
    """
    从执行轨迹学习
    
    整合Kunming的技能创建和Cognitive Core的SONA学习系统
    
    Args:
        trajectory_json: JSON格式的执行轨迹
        task_type: 任务类型
    """
    # 参数验证
    valid, trajectory, error_msg = _validate_json_param(trajectory_json, "trajectory_json")
    if not valid:
        return json.dumps({"success": False, "error": error_msg})
    
    valid, error_msg = _validate_string_param(task_type, "task_type", required=False, max_length=50)
    if not valid:
        return json.dumps({"success": False, "error": error_msg})
    
    try:
        from ..adapters import get_unified_learning
        
        learning = get_unified_learning()
        
        if not learning._initialized:
            _run_async(learning.initialize())
        
        result = _run_async(learning.learn_from_trajectory(
            trajectory=trajectory,
            task_type=task_type
        ))
        
        return json.dumps({
            "success": True,
            "task_type": task_type,
            "result": result
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"cognitive_core_learn_from_trajectory failed: {e}", exc_info=True)
        return json.dumps({
            "success": False,
            "error": str(e)
        })


def cognitive_core_create_skill(
    name: str,
    description: str,
    content: str,
    auto_improve: bool = True,
    task_id: str = None
) -> str:
    """
    创建可复用技能
    
    整合Kunming的技能格式和Cognitive Core的自动优化
    
    Args:
        name: 技能名称
        description: 技能描述
        content: 技能内容
        auto_improve: 是否启用自动改进
    """
    # 参数验证
    valid, error_msg = _validate_string_param(name, "name", required=True, max_length=100)
    if not valid:
        return json.dumps({"success": False, "error": error_msg})
    
    valid, error_msg = _validate_string_param(description, "description", required=True, max_length=500)
    if not valid:
        return json.dumps({"success": False, "error": error_msg})
    
    valid, error_msg = _validate_string_param(content, "content", required=True, max_length=100000)
    if not valid:
        return json.dumps({"success": False, "error": error_msg})
    
    valid, auto_improve_val, error_msg = _validate_bool_param(auto_improve, "auto_improve", default=True)
    if not valid:
        return json.dumps({"success": False, "error": error_msg})
    
    try:
        from ..adapters import get_unified_learning
        
        learning = get_unified_learning()
        
        if not learning._initialized:
            _run_async(learning.initialize())
        
        result = _run_async(learning.create_skill(
            name=name,
            description=description,
            content=content,
            auto_improve=auto_improve_val
        ))
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"cognitive_core_create_skill failed: {e}", exc_info=True)
        return json.dumps({
            "success": False,
            "error": str(e)
        })


def cognitive_core_learning_stats(task_id: str = None) -> str:
    """获取学习系统统计"""
    try:
        from ..adapters import get_unified_learning
        
        learning = get_unified_learning()
        
        if not learning._initialized:
            _run_async(learning.initialize())
        
        stats = _run_async(learning.get_learning_stats())
        
        return json.dumps({
            "success": True,
            "stats": stats
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"cognitive_core_learning_stats failed: {e}", exc_info=True)
        return json.dumps({
            "success": False,
            "error": str(e)
        })


# ============ 系统状态工具 ============

def cognitive_core_system_status(task_id: str = None) -> str:
    """获取Cognitive Core集成系统状态"""
    status = {
        "memory_system": {"available": False, "initialized": False},
        "expert_system": {"available": False, "initialized": False},
        "swarm_system": {"available": False, "initialized": False},
        "learning_system": {"available": False, "initialized": False}
    }
    
    try:
        from ..adapters import (
            get_hybrid_memory_provider,
            get_smart_delegator,
            get_unified_learning
        )
        
        # 检查记忆系统
        try:
            mem = get_hybrid_memory_provider()
            status["memory_system"] = {
                "available": True,
                "initialized": mem._initialized
            }
        except Exception as e:
            status["memory_system"]["error"] = str(e)
        
        # 检查专家系统
        try:
            delegator = get_smart_delegator()
            status["expert_system"] = {
                "available": True,
                "initialized": delegator._initialized
            }
        except Exception as e:
            status["expert_system"]["error"] = str(e)
        
        # 检查学习系统
        try:
            learning = get_unified_learning()
            status["learning_system"] = {
                "available": True,
                "initialized": learning._initialized
            }
        except Exception as e:
            status["learning_system"]["error"] = str(e)
        
        # 蜂群系统随专家系统一起
        status["swarm_system"] = status["expert_system"].copy()
        
        all_ready = all(s.get("available", False) for s in status.values())
        
        return json.dumps({
            "success": True,
            "all_systems_ready": all_ready,
            "systems": status
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"cognitive_core_system_status failed: {e}", exc_info=True)
        return json.dumps({
            "success": False,
            "error": str(e),
            "systems": status
        })


# ============ 注册所有工具 ============

def register_cognitive_tools():
    """注册所有Cognitive Core集成工具"""
    
    # 记忆系统
    registry.register(
        name="cognitive_memory_search",
        toolset="Cognitive Core",
        schema={
            "name": "cognitive_memory_search",
            "description": "使用Cognitive Core增强的混合记忆搜索（FTS5 + HNSW向量索引，150x-12,500x更快）",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索查询"},
                    "k": {"type": "integer", "description": "返回结果数量", "default": 10},
                    "use_hybrid": {"type": "boolean", "description": "是否使用混合搜索", "default": True}
                },
                "required": ["query"]
            }
        },
        handler=lambda args, **kw: cognitive_memory_search(
            query=args.get("query"),
            k=args.get("k", 10),
            use_hybrid=args.get("use_hybrid", True),
            task_id=kw.get("task_id")
        ),
        check_fn=check_cognitive_core_requirements
    )
    
    registry.register(
        name="cognitive_memory_store",
        toolset="Cognitive Core",
        schema={
            "name": "cognitive_memory_store",
            "description": "存储记忆到Cognitive Core的统一记忆系统",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "记忆内容"},
                    "memory_type": {"type": "string", "description": "记忆类型", "default": "episodic"},
                    "metadata": {"type": "string", "description": "JSON元数据", "default": "{}"}
                },
                "required": ["content"]
            }
        },
        handler=lambda args, **kw: cognitive_memory_store(
            content=args.get("content"),
            memory_type=args.get("memory_type", "episodic"),
            metadata=args.get("metadata", "{}"),
            task_id=kw.get("task_id")
        ),
        check_fn=check_cognitive_core_requirements
    )
    
    # 专家系统
    registry.register(
        name="cognitive_core_delegate",
        toolset="Cognitive Core",
        schema={
            "name": "cognitive_core_delegate",
            "description": "智能委托任务给Cognitive Core专家代理（自动选择最佳执行策略）",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "任务描述"},
                    "context": {"type": "string", "description": "上下文信息", "default": ""},
                    "use_swarm": {"type": "boolean", "description": "是否使用蜂群协调", "default": False}
                },
                "required": ["task"]
            }
        },
        handler=lambda args, **kw: cognitive_core_delegate(
            task=args.get("task"),
            context=args.get("context", ""),
            use_swarm=args.get("use_swarm", False),
            task_id=kw.get("task_id")
        ),
        check_fn=check_cognitive_core_requirements
    )
    
    registry.register(
        name="cognitive_core_spawn_expert",
        toolset="Cognitive Core",
        schema={
            "name": "cognitive_core_spawn_expert",
            "description": "创建Cognitive Core专家代理（55种类型可选）",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_type": {"type": "string", "description": "代理类型（coder/reviewer/tester等）"},
                    "name": {"type": "string", "description": "代理名称", "default": ""},
                    "capabilities": {"type": "string", "description": "能力列表JSON", "default": "[]"}
                },
                "required": ["agent_type"]
            }
        },
        handler=lambda args, **kw: cognitive_core_spawn_expert(
            agent_type=args.get("agent_type"),
            name=args.get("name", ""),
            capabilities=args.get("capabilities", "[]"),
            task_id=kw.get("task_id")
        ),
        check_fn=check_cognitive_core_requirements
    )
    
    # 蜂群系统
    registry.register(
        name="cognitive_core_swarm_allocate",
        toolset="Cognitive Core",
        schema={
            "name": "cognitive_core_swarm_allocate",
            "description": "使用Cognitive Core蜂群系统分配任务（6种拓扑）",
            "parameters": {
                "type": "object",
                "properties": {
                    "goal": {"type": "string", "description": "任务目标"},
                    "topology": {"type": "string", "description": "拓扑结构", "default": "adaptive"}
                },
                "required": ["goal"]
            }
        },
        handler=lambda args, **kw: cognitive_core_swarm_allocate(
            goal=args.get("goal"),
            topology=args.get("topology", "adaptive"),
            task_id=kw.get("task_id")
        ),
        check_fn=check_cognitive_core_requirements
    )
    
    registry.register(
        name="cognitive_core_hive_mind_decide",
        toolset="Cognitive Core",
        schema={
            "name": "cognitive_core_hive_mind_decide",
            "description": "使用Cognitive Core蜂巢意识进行集体决策",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "决策问题"},
                    "options": {"type": "string", "description": "选项列表JSON", "default": "[]"}
                },
                "required": ["question"]
            }
        },
        handler=lambda args, **kw: cognitive_core_hive_mind_decide(
            question=args.get("question"),
            options=args.get("options", "[]"),
            task_id=kw.get("task_id")
        ),
        check_fn=check_cognitive_core_requirements
    )
    
    # 学习系统
    registry.register(
        name="cognitive_core_learn_from_trajectory",
        toolset="Cognitive Core",
        schema={
            "name": "cognitive_core_learn_from_trajectory",
            "description": "从执行轨迹学习（整合SONA学习系统）",
            "parameters": {
                "type": "object",
                "properties": {
                    "trajectory_json": {"type": "string", "description": "执行轨迹JSON"},
                    "task_type": {"type": "string", "description": "任务类型", "default": "general"}
                },
                "required": ["trajectory_json"]
            }
        },
        handler=lambda args, **kw: cognitive_core_learn_from_trajectory(
            trajectory_json=args.get("trajectory_json"),
            task_type=args.get("task_type", "general"),
            task_id=kw.get("task_id")
        ),
        check_fn=check_cognitive_core_requirements
    )
    
    registry.register(
        name="cognitive_core_create_skill",
        toolset="Cognitive Core",
        schema={
            "name": "cognitive_core_create_skill",
            "description": "创建可复用技能（自动优化）",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "技能名称"},
                    "description": {"type": "string", "description": "技能描述"},
                    "content": {"type": "string", "description": "技能内容"},
                    "auto_improve": {"type": "boolean", "description": "自动改进", "default": True}
                },
                "required": ["name", "description", "content"]
            }
        },
        handler=lambda args, **kw: cognitive_core_create_skill(
            name=args.get("name"),
            description=args.get("description"),
            content=args.get("content"),
            auto_improve=args.get("auto_improve", True),
            task_id=kw.get("task_id")
        ),
        check_fn=check_cognitive_core_requirements
    )
    
    registry.register(
        name="cognitive_core_learning_stats",
        toolset="Cognitive Core",
        schema={
            "name": "cognitive_core_learning_stats",
            "description": "获取学习系统统计"
        },
        handler=lambda args, **kw: cognitive_core_learning_stats(task_id=kw.get("task_id")),
        check_fn=check_cognitive_core_requirements
    )
    
    # 系统状态
    registry.register(
        name="cognitive_core_system_status",
        toolset="Cognitive Core",
        schema={
            "name": "cognitive_core_system_status",
            "description": "获取Cognitive Core集成系统状态"
        },
        handler=lambda args, **kw: cognitive_core_system_status(task_id=kw.get("task_id")),
        check_fn=lambda: True  # 总是可用
    )


# 延迟注册 - 在模块被显式导入时注册
def ensure_registered():
    """确保工具已注册（幂等操作）"""
    try:
        # 检查是否已注册
        if "cognitive_memory_search" not in registry.list_tools():
            register_cognitive_tools()
    except Exception as e:
        logger.warning(f"Failed to register cognitive tools: {e}")
