中国人自己的agent，一个越用越灵活的agent！

## 为什么选择 km agent?

| 特性       | km agent       | 其他 Agent |
| -------- | -------------- | -------- |
| **长期记忆** | 拥有长期记忆         | 短，中期记忆   |
| **异步架构** | 原生 asyncio，真异步 | 线程池包装同步  |
| **学习系统** | RL 训练 + 策略优化   | 基础轨迹存储   |
| **中文支持** | 完整中文化界面        | 英文为主     |
| **多平台**  | CLI + 6 种消息平台  | 通常仅 CLI  |
| **终端后端** | 6 种（含无服务器）     | 通常仅本地    |

***

## 核心能力

| 特性         | 说明                                                        |
| ---------- | --------------------------------------------------------- |
| **真·异步架构** | 从底层重新设计的原生 asyncio，不是线程池包装同步那种假异步                         |
| **内置学习循环** | 自动捕获执行轨迹 → 压缩 → 存入 ReasoningBank → RL 训练自我改进              |
| **多平台对话**  | CLI / Telegram / Discord / Slack / WhatsApp / Signal 统一入口 |
| **智能体工厂**  | 动态生成专家子代理，并行处理复杂任务                                        |
| **蜂群系统**   | 多代理协作（去中心化设计，代理间互不干扰，稳定性优先）                               |
| **MCP 生态** | 支持 Model Context Protocol，可接入任意 MCP 服务器                   |
| **定时自动化**  | 内置 Cron 调度器，自然语言配置定时任务                                    |
| **多终端后端**  | 本地 / Docker / SSH / Daytona / Modal / Singularity 无缝切换    |

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

## 模型支持

支持 200+ 模型，零代码切换：

- Kimi K2.5 / Moonshot
- GLM-4 / z.ai
- OpenRouter (200+ 模型)
- OpenAI / Anthropic
- 本地模型 (Ollama 等)

***

## 学习系统架构

```
用户对话 → AIAgent → 捕获轨迹 → ReasoningBank
                              ↓
                    轨迹压缩 + 向量化存储
                              ↓
                    RLTrainer (Q-Learning) → 策略优化
                              ↓
                    生成技能 → 自我改进
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
    ║  ╔═══╗ ╔╗       ╔═══╗╔═══╗╔═══╗╔╗╔╗╔═══╗╔═══╗          ║
    ║  ║╔═╗║╔╝╚╗      ║╔═╗║║╔═╗║║╔═╗║║║║║║╔══╝║╔═╗║          ║
    ║  ║║ ║║╚╗╔╝      ║║ ║║║╚═╝║║║ ╚╝║║║║║╚══╗║╚═╝║          ║
    ║  ║╚═╝║ ║║       ║╚═╝║║╔╗╔╝║║ ╔╗║╚╝║║╔══╝║╔╗╔╝          ║
    ║  ║╔═╗║ ║╚╗      ║╔═╗║║║║╚╗║╚═╝║╚╗╔╝║╚══╗║║║╚╗          ║
    ║  ╚╝ ╚╝ ╚═╝      ╚╝ ╚╝╚╝╚═╝╚═══╝ ╚╝ ╚═══╝╚╝╚═╝          ║
    ╚═══════════════════════════════════════════════════════════════╝

╭────────────────── km agent v0.8.0 (2026.4.8) ───────────────────╮
│                                    可用工具                                                      │
│                        ◆          浏览器: browser_back, browser_click, ...                     │
│                     ◆ ◆ ◆         文件: patch, read_file, search_files, write_file             │
│                  ◆ ◆ ◆ ◆ ◆        技能: skill_manage, skill_view, skills_list                  │
│               ◆ ◆ ◆ ◆ ◆ ◆ ◆       终端: terminal                                               │
│                      │││          (还有 5 个工具集...)                                          │
│             ══════╧╧╧══════                                                                     │
│                                   27 个工具 | 276 个技能 | /help 查看命令                       │
╰─────────────────────────────────────────────────────────────────────────────────────────────────╯

km agent ready
❯ 你好
╭─ km ───────────────────────────────────────────╮
│ 你好！我是 km agent，有什么可以帮你的？            │
╰────────────────────────────────────────────────╯
```

***

## 技术栈

- **Python 3.11+** / asyncio
- **SQLite + FTS5** (全文搜索)
- **HNSW** (向量索引)
- **Pydantic** (类型安全)
- **Rich / prompt\_toolkit** (TUI)
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
├── agent/                    # Agent 内部实现
│   ├── cognitive/            # 认知层 (学习、蜂群、RL)
│   │   ├── neural/           # 神经网络 (ReasoningBank, RLTrainer)
│   │   ├── swarm/            # 蜂群系统
│   │   └── experts/          # 专家系统
│   ├── memory/               # 记忆管理
│   └── ...
├── tools/                    # 工具实现
│   ├── registry.py           # 工具注册中心
│   ├── file_tools.py         # 文件操作
│   ├── web_tools.py          # 网络搜索
│   └── ...
├── gateway/                  # 消息平台网关
│   └── platforms/            # Telegram/Discord/Slack 等适配器
├── kunming_cli/              # CLI 子命令实现
│   ├── banner.py             # 启动画面
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





