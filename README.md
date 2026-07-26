# tokens

本地 CLI 工具：统计 **Claude Code / Gemini / Codex** 的 token 用量，按 **日 / 周 / 月** 聚合，拆分到模型，输出终端表格、静态 HTML 报告、交互式 dashboard。

纯 Python stdlib，**零依赖**，下载即用。

> 默认只统计 Claude（经 [claude-code-router](https://github.com/musistudio/claude-code-router) 走 GLM-5.2 / DeepSeek 等真实后端）。Gemini / Codex 日志也支持，用 `--source` 开。

<!-- ![dashboard](docs/dashboard.png) --> _(截图占位)_

## 安装

**方式一：直接跑（零安装）**

```bash
git clone <this-repo> && cd tokens
python3 cli.py month          # 或 ./run month
```

**方式二：pipx / pip 安装为全局命令**

```bash
pipx install .                # 装后得到全局命令 `tokens`
tokens month
```

需 Python ≥ 3.9。

## 用法

```bash
# 终端报告
python3 cli.py                # 今天（默认）
python3 cli.py week           # 本周 + 最近 8 周
python3 cli.py month          # 本月 + 最近 6 个月
python3 cli.py all            # 全部历史，按日

# 交互式 dashboard（推荐）：内含日/周/月切换 + 模型筛选 + 图表
python3 cli.py dashboard --open

# 静态 HTML 报告（单期）
python3 cli.py month --html --open

# 过滤
python3 cli.py --since 2026-07-01 --until 2026-07-25
python3 cli.py week --source gemini --source codex     # 换/加来源
python3 cli.py day --no-cache                          # 强制重读日志
```

参数：

| 参数 | 说明 |
|---|---|
| `--days N` | day 模式回看天数（默认 14） |
| `--weeks N` | week 模式回看周数（默认 8） |
| `--months N` | month 模式回看月数（默认 6） |
| `--html` | 生成单期静态 HTML 报告 |
| `--dashboard` | 生成交互式 dashboard（离线可用） |
| `--open` | 生成后自动打开 |
| `--no-cache` | 忽略缓存，强制重读日志 |
| `--source` | 限定来源，可多次：`claude` / `gemini` / `codex` |

## Dashboard

`python3 cli.py dashboard --open` 生成单个自包含 HTML（`out/dashboard.html`），**双击即开、可邮件分发、离线可用**：

- 日 / 周 / 月 一键切换
- 模型 checkbox 筛选，柱状图 / 环形图 / 明细表联动
- KPI：总 token、调用次数、命中模型数、主力模型
- 堆叠柱状图（悬停看每段模型明细）+ 模型占比环形图
- 数据全部内嵌，无 CDN、无网络请求

## 数据来源

| CLI | 本地日志路径 |
|---|---|
| Claude Code | `~/.claude/projects/**/*.jsonl` |
| Gemini CLI | `~/.gemini/tmp/<hash>/chats/session-*.json` |
| Codex | `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` |

只读本地文件，不上传任何数据。按文件 `mtime+size` 缓存（`out/cache.json`），未变秒出。

## 文件

| 文件 | 作用 |
|---|---|
| `config.py` | 路径、时区、默认来源、模型别名 |
| `readers.py` | 读三源日志 → 统一 record；文件级缓存 |
| `aggregate.py` | 日/周/月聚合 + 按模型/来源拆分 |
| `report_term.py` | 终端 ANSI 表格 |
| `report_html.py` | 单期静态 HTML 报告（SVG 图） |
| `report_dashboard.py` | 交互式自包含 dashboard |
| `cli.py` | 入口 |

## Roadmap

- [ ] `$` 成本估算（按模型单价表）
- [ ] `tokens serve` 本地 live dashboard（自动刷新）
- [ ] 包结构重构：flat → `tokens/` 包，统一 `python -m tokens`
- [ ] 按 cwd / 项目维度拆分用量
- [ ] Windows 兼容（`open` → `os.startfile`）
- [ ] 测试用例

## License

MIT
