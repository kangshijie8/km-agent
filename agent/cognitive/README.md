# Cognitive Core System for Kunming Agent

> ⚠️ **实验性功能** — 本模块处于早期开发阶段，部分功能尚未完全实现。
> 蜂群系统、RL学习、专家系统等高级功能目前为架构框架，核心逻辑仍在迭代中。
> 欢迎贡献代码，但不建议在生产环境中依赖这些功能。

企业级AI代理编排系统集成，将Kunming从AI陪伴助手转变为强大的AI合伙人。

## 核心能力

### 1. 记忆系统 (Memory System)
- **HNSW向量索引**: 150x-12,500x更快的语义搜索
- **混合搜索**: 结合FTS5文本搜索和HNSW向量搜索
- **统一存储**: 支持episodic/semantic/procedural/working记忆类型

### 2. 专家系统 (Expert System)
- **55+代理类型**: coder, reviewer, tester, planner, researcher, architect等
- **工厂模式**: 动态创建和管理专家代理
- **智能路由**: 根据任务复杂度自动选择执行策略

### 3. 蜂群系统 (Swarm System)
- **6种拓扑**: hierarchical, mesh, centralized, decentralized, hybrid, adaptive
- **5种共识**: Raft, Byzantine, Gossip, Paxos, Hybrid
- **女王协调器**: 中央协调多代理协作
- **集体决策**: 蜂巢意识达成共识

### 4. 学习系统 (Learning System)
- **SONA架构**: 自优化神经架构
- **9种RL算法**: PPO, DQN, A2C, Decision Transformer, Q-Learning, SARSA, SAC, TD3, Rainbow
- **ReasoningBank**: 轨迹存储和语义检索
- **自动技能创建**: 从执行轨迹学习并创建技能

## 快速开始

```python
from agent.cognitive import CognitiveCore, create_cognitive

# 创建集成实例
Cognitive Core = create_cognitive(
    memory=True,
    experts=True,
    swarm=True,
    learning=True
)

# 初始化
await Cognitive Core.initialize()

# 使用记忆系统
results = await Cognitive Core.hybrid_memory.search("API patterns", k=5)

# 使用专家系统
result = await Cognitive Core.smart_delegator.delegate("Implement authentication")

# 使用蜂群系统
decision = await Cognitive Core.swarm.hive_mind_decide(
    "Which architecture should we use?",
    ["microservices", "monolith", "serverless"]
)

# 使用学习系统
await Cognitive Core.unified_learning.learn_from_trajectory(trajectory)
```

## MCP工具

集成提供12个MCP工具，AI Agent可直接调用：

### 记忆工具
- `cognitive_memory_search`: 混合记忆搜索
- `cognitive_memory_store`: 存储记忆

### 专家工具
- `Cognitive Core_delegate`: 智能任务委托
- `Cognitive Core_spawn_expert`: 创建专家代理

### 蜂群工具
- `Cognitive Core_swarm_allocate`: 蜂群任务分配
- `Cognitive Core_hive_mind_decide`: 集体决策

### 学习工具
- `Cognitive Core_learn_from_trajectory`: 从轨迹学习
- `Cognitive Core_create_skill`: 创建技能
- `Cognitive Core_learning_stats`: 学习统计

### 系统工具
- `Cognitive Core_system_status`: 系统状态

## 项目结构

```
agent/cognitive/
├── __init__.py                 # 主集成模块
├── README.md                   # 本文档
├── memory/                     # 记忆系统
│   ├── types.py               # 类型定义
│   ├── hnsw_lite.py           # HNSW向量索引
│   └── unified_memory_service.py  # 统一记忆服务
├── experts/                    # 专家系统
│   ├── types.py               # 55种代理类型
│   └── agent_factory.py       # 代理工厂
├── swarm/                      # 蜂群系统
│   ├── types.py               # 拓扑和共识类型
│   └── queen_coordinator.py   # 女王协调器
├── neural/                     # 学习系统
│   ├── types.py               # RL算法类型
│   └── reasoning_bank.py      # 推理银行
├── adapters/                   # 优化适配器
│   ├── memory_adapter.py      # 混合记忆适配器
│   ├── delegate_adapter.py    # 智能委托适配器
│   └── learning_adapter.py    # 统一学习适配器
└── tools/                      # MCP工具
    └── cognitive_tools.py         # 12个MCP工具
```

## 优化适配器

### HybridMemoryProvider
结合Kunming的FTS5和Cognitive Core的HNSW，提供混合搜索：
- FTS5: 关键词匹配
- HNSW: 语义相似度
- 混合评分: 0.3 * FTS + 0.7 * Vector

### SmartDelegator
根据任务复杂度智能选择执行策略：
- 简单任务: 单代理执行
- 中等任务: 并行多专家
- 复杂任务: 协调器管理
- 研究任务: 蜂群系统

### UnifiedLearningSystem
整合Kunming的skill_manage和Cognitive Core的SONA：
- 轨迹存储到ReasoningBank
- 自动技能建议
- RL策略优化

## 初始化

运行初始化脚本：

```bash
python init_cognitive.py
```

## 版本

- Cognitive Core Integration: 3.5.0-kunming
- Based on: @claude-flow V3.5

## 许可证

与Kunming Agent相同
