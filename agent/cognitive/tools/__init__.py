"""
Cognitive Core Integration MCP Tools

提供12个MCP工具，让AI Agent可以直接调用Cognitive Core的4大系统能力：

记忆系统工具:
- cognitive_memory_search: 混合记忆搜索（FTS5 + HNSW）
- cognitive_memory_store: 存储记忆

专家系统工具:
- Cognitive Core_delegate: 智能任务委托
- Cognitive Core_spawn_expert: 创建专家代理

蜂群系统工具:
- Cognitive Core_swarm_allocate: 蜂群任务分配
- Cognitive Core_hive_mind_decide: 集体决策

学习系统工具:
- Cognitive Core_learn_from_trajectory: 从轨迹学习
- Cognitive Core_create_skill: 创建技能
- Cognitive Core_learning_stats: 学习统计

系统工具:
- Cognitive Core_system_status: 系统状态
"""

# 工具在cognitive_tools.py中定义并自动注册
# 导入此模块即可注册所有工具

try:
    from . import cognitive_tools
except ImportError:
    pass

__all__ = []
