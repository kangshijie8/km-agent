中国人自己的agent，一个越用越聪明的agent！

## 为什么选择 km agent?

| 特性 | km agent | 其他 Agent |
|------|----------|-----------|
| **三层记忆** | 事实/经验/模型三层架构 + 遗忘曲线 | 扁平记忆，无衰减 |
| **混合搜索** | 内置 FTS5 + SimHash 向量检索 | 仅关键词搜索 |
| **自学习系统** | 记忆蒸馏 + 错误学习 + LLM辅助提炼 | 基础轨迹存储 |
| **异步架构** | 原生 asyncio，真异步 | 线程池包装同步 |
| **RL 训练** | Atropos 集成，支持 GRPO/PPO | 无 |
| **中文支持** | 完整中文化界面 | 英文为主 |
| **多平台** | CLI + 6 种消息平台 | 通常仅 CLI |
| **终端后端** | 6 种（含无服务器） | 通常仅本地 |

***

## 核心能力

| 特性 | 说明 |
|------|------|
| **三层记忆架构** | 事实层(FACTS) + 经验层(EXPERIENCES) + 模型层(MODELS)，像人脑一样分层存储 |
| **混合搜索** | 内置 FTS5 关键词 + SimHash 向量相似度，零外部依赖的语义检索 |
| **Ebbinghaus 遗忘曲线** | 记忆自然衰减 + 访问刷新，不常用的记忆自动淘汰 |
| **记忆蒸馏** | 夜间自动整理：收集信号 → LLM提取模式 → 评分提升 → 衰减淘汰 |
| **错误学习** | 自动检测用户纠正，记录失败经验，重复错误升级为规则 |
| **真·异步架构** | 从底层重新设计的原生 asyncio，不是线程池包装同步那种假异步 |
| **多平台对话** | CLI / Telegram / Discord / Slack / WhatsApp / Signal / 飞书 / 钉钉 / 企业微信 |
| **智能体工厂** | 动态生成专家子代理，并行处理复杂任务 |
| **MCP 生态** | 支持 Model Context Protocol，可接入任意 MCP 服务器 |
| **定时自动化** | 内置 Cron 调度器，自然语言配置定时任务 |
| **多终端后端** | 本地 / Docker / SSH / Daytona / Modal / Singularity 无缝切换 |
| **ACP 集成** | VS Code / Zed / JetBrains 编辑器内直接使用 |

***

## 快速开始

### 安装

```bash
# 克隆仓库
git clone https://github.com/kangshijie8/KM-Agent.git
cd km-agent

# 创建虚拟环境
uv venv venv --python 3.11
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
uv pip install -e ".[all]"

# 配置 API 密钥
km setup
```

### 启动

```bash
km              # 交互式 CLI
km gateway      # 启动消息网关（支持 Telegram/Discord/Slack 等）
```

### 常用命令

```bash
/help           # 查看所有命令
/model          # 切换模型
/tools          # 查看可用工具
/skills         # 查看可用技能
/skin           # 切换界面主题
```

***

## 记忆与学习系统

### 三层记忆架构

```
FACTS.md        环境知识、工具特性、项目约定
EXPERIENCES.md  问题解决记录、操作结果、成功/失败经验
MODELS.md       提炼出的规则、模式、决策策略
USER.md         用户画像、偏好、沟通风格
```

- **自动迁移**：旧版 MEMORY.md 自动迁移为 FACTS.md
- **冻结快照**：系统提示在会话开始时冻结，保持前缀缓存稳定
- **容量限制**：每层独立字符限制，防止记忆膨胀

### 混合搜索（零外部依赖）

`recall` 动作使用内置混合评分：
- **FTS5 关键词匹配**（35% 权重）：词重叠、覆盖率、精确匹配加分
- **SimHash 向量相似度**（65% 权重）：基于 hashlib.md5 的指纹比较

```python
memory(action="recall", target="facts", query="部署环境配置")
```

### Ebbinghaus 遗忘曲线

每条记忆自动跟踪元数据（创建时间、访问次数、重要性），按指数衰减：

```
retention = exp(-0.693 × age / (half_life × access_boost × importance))
```

- 14天半衰期，访问时自动刷新
- 包含"preference/always/never/must"的记忆永不衰减
- 蒸馏时自动淘汰低保留率记忆

### 记忆蒸馏（夜间自动整理）

每天凌晨3点自动运行四阶段整理：

```
Light → REM → Deep → Decay
 收集     提取    评分    淘汰
 信号    模式    提升    过期
         ↑
    LLM辅助提取
```

### 错误学习

- 自动检测5种纠正模式（显式拒绝、重定向、引用之前、修复请求、正确做法）
- 错误日志持久化，自动去重计数
- 同一错误≥3次自动升级为 MODELS.md 规则
- 会话开始时注入相关错误经验作为警告

***

## 模型支持

支持 200+ 模型，零代码切换：

- Kimi K2.5 / Moonshot
- GLM-4 / z.ai
- OpenRouter (200+ 模型)
- OpenAI / Anthropic
- 本地模型 (Ollama 等)

***

## RL 训练环境

集成 [Atropos](https://github.com/NousResearch/atropos) RL 训练框架，支持用强化学习优化 agent 策略：

- **SWE-bench 训练**：代码任务 + 测试验证奖励
- **TerminalBench 2.0 评测**：89个终端任务基准
- **Phase 1**：OpenAI Server（评估/SFT数据生成）
- **Phase 2**：VLLM ManagedServer（完整 RL 训练，GRPO/PPO）
- **10+ 工具调用解析器**：支持 Kunming/Mistral/Llama/Qwen/DeepSeek/Kimi/GLM 格式

```bash
# 运行评测
python environments/benchmarks/terminalbench_2/terminalbench2_env.py evaluate \
    --openai.model_name anthropic/claude-opus-4.6
```

***

## CLI 界面

```
    ╔═══════════════════════════════════════════════════════════════╗
    ║              ██╗  ██╗███╗   ███╗                           ║
    ║              ██║ ██╔╝████╗ ████║                           ║
    ║              █████╔╝ ██╔████╔██║                           ║
    ║              ██╔═██╗ ██║╚██╔╝██║                           ║
    ║              ██║  ██╗██║ ╚═╝ ██║                           ║
    ║              ╚═╝  ╚═╝╚═╝     ╚═╝                           ║
    ║                                                               ║
    ╚═══════════════════════════════════════════════════════════════╝

╭────────────────── km agent ───────────────────╮
│                                    可用工具                      │
│                        ◆          浏览器: browser_back, ...     │
│                     ◆ ◆ ◆         文件: read_file, write_file  │
│                  ◆ ◆ ◆ ◆ ◆        技能: skill_manage, ...      │
│               ◆ ◆ ◆ ◆ ◆ ◆ ◆       终端: terminal              │
│                      │││          (还有 5 个工具集...)          │
│             ══════╧╧╧══════                                     │
│                                   27 个工具 | 276 个技能        │
╰──────────────────────────────────────────────────────────────────╯
```

***

## 技术栈

- **Python 3.11+** / asyncio
- **SQLite + FTS5** (全文搜索)
- **SimHash** (零依赖向量相似度)
- **Pydantic** (类型安全)
- **Rich / prompt_toolkit** (TUI)
- **pytest** (3000+ 测试)

***

## 项目结构

```
km-agent/
├── km                        # CLI 入口
├── run_agent.py              # AIAgent 核心对话循环
├── model_tools.py            # 工具编排
├── toolsets.py               # 工具集定义
├── cli.py                    # CLI 主实现
├── kunming_state.py          # SQLite + FTS5 会话存储
├── agent/                    # Agent 内部实现
│   ├── builtin_memory_provider.py  # 三层记忆 Provider
│   ├── memory_distillation.py      # 记忆蒸馏 (Light→REM→Deep→Decay)
│   ├── memory_provider.py          # 记忆 Provider 抽象基类
│   ├── memory_manager.py           # 记忆管理器
│   ├── error_learning.py           # 错误学习模块
│   ├── context_compressor.py       # 上下文压缩
│   ├── prompt_caching.py           # Anthropic 提示缓存
│   ├── auxiliary_client.py         # 辅助 LLM 客户端
│   ├── cognitive/                  # 认知层 (学习、蜂群、RL)
│   │   ├── neural/                 # 神经网络 (ReasoningBank, RLTrainer)
│   │   ├── swarm/                  # 蜂群系统
│   │   └── experts/                # 专家系统
│   └── ...
├── tools/                    # 工具实现
│   ├── registry.py           # 工具注册中心
│   ├── memory_tool.py        # 三层记忆工具 (add/replace/remove/recall)
│   ├── file_tools.py         # 文件操作
│   ├── web_tools.py          # 网络搜索
│   ├── mcp_tool.py           # MCP 客户端
│   └── ...
├── gateway/                  # 消息平台网关
│   └── platforms/            # Telegram/Discord/Slack/飞书/钉钉等适配器
├── environments/             # RL 训练环境 (Atropos)
│   ├── kunming_base_env.py   # 基础 RL 环境
│   ├── agent_loop.py         # 多轮代理引擎
│   ├── tool_context.py       # 工具上下文
│   └── benchmarks/           # 评测基准
├── kunming_cli/              # CLI 子命令实现
│   ├── skin_engine.py        # 主题引擎
│   └── ...
├── skills/                   # 技能目录
└── tests/                    # 测试套件 (~3000 测试)
```

***

## 贡献

欢迎 PR！代码要实在，注释要写清楚，测试要过关。

```bash
git clone https://github.com/kangshijie8/KM-Agent.git
cd km-agent
uv venv venv --python 3.11
source venv/bin/activate
uv pip install -e ".[all,dev]"
python -m pytest tests/ -q
```

***

## License

MIT
