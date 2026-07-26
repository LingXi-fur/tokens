# tokens

本地 CLI 工具：统计 **Claude Code / Gemini / Codex** 的 token 用量，按 **日 / 周 / 月** 聚合，拆分到模型，输出终端表格、静态 HTML 报告、交互式 dashboard。

纯 Python stdlib，**零运行依赖**，下载即用。

> 默认只统计 Claude（经 [claude-code-router](https://github.com/musistudio/claude-code-router) 走 GLM-5.2 / DeepSeek 等真实后端）。Gemini / Codex 日志也支持，用 `--source` 开启。

## 文档

完整中文文档位于 [`docs/`](docs/index.html)，包含快速开始、CLI 参考、Dashboard、数据与隐私、架构和 FAQ。

- GitHub Pages：在仓库 Pages 启用 **GitHub Actions** 后，由 [`.github/workflows/pages.yml`](.github/workflows/pages.yml) 自动发布 `docs/`。
- 直接预览：双击 `docs/index.html`。
- 本地 HTTP 预览：

```bash
python3 -m http.server 8000 --directory docs
# 打开 http://localhost:8000/
```

文档站零构建、无 CDN、无第三方运行时依赖；支持响应式布局、自动/亮色/暗色主题、`Cmd/Ctrl+K` 全站搜索、移动导航、代码复制和阅读进度。首页与 Dashboard 文档中的演示均为合成数据。

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

# 交互式 dashboard（推荐）
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
| `--since YYYY-MM-DD` | 起始日期，覆盖模式默认起点 |
| `--until YYYY-MM-DD` | 结束日期，默认今天 |
| `--html` | 生成单期静态 HTML 报告 |
| `--dashboard` | 生成交互式 dashboard（等价于 `dashboard` 位置模式） |
| `--open` | 生成后自动打开；当前使用 macOS `open` |
| `--no-cache` | 忽略缓存，强制重读日志 |
| `--source` | 限定来源，可多次：`claude` / `gemini` / `codex` |

## Dashboard

`python3 cli.py dashboard --open` 生成单个自包含 HTML（`out/dashboard.html`），双击即开、离线可用：

### 核心统计

- 日 / 周 / 月一键切换，柱状图、KPI、环形图、明细和扩展模块联动
- 模型筛选：点击开关、双击单看、Alt 点击全选/清空、右键反选
- KPI：总 token、缓存命中与省量、调用次数、命中模型数、主力模型、环比、月末预测
- 按模型堆叠柱状图、均值线、峰值标识、上一期“幻影”轮廓与变化百分比
- 点击柱子进入“时光探针”，按单日/单周/单月重算局部视图
- 模型占比、每模型迷你趋势、明细表、Top 项目 / 会话联动

### 时间与行为视图

- 数据气候、数据侦探、近 5 小时计费窗口、近 14 天迷你趋势
- 24 小时作息时钟、14 天 × 24 小时作息织锦与小时 tooltip
- 会话逐轮 token 回放、柱图竞赛、趣味换算与今日运势

### 数据宇宙模块

- Token 流光图：按真实聚合展示项目 → 模型 → 会话的 Token 流向，可锁定链路并回放会话
- Token 生物：由总量、模型、项目、缓存与作息塑形，可导出 SVG
- Token 星云：按小时 / 模型 / 缓存生成数据深空，可导出 SVG
- 大型成就图鉴：分级、隐藏、搜索、筛选、分类折叠
- 模块开关并通过 localStorage 记忆显示偏好

### 操作与导出

- 自动 / 亮色 / 暗色三态主题
- `Cmd/Ctrl+K` 命令面板；`1/2/3` 切粒度，`T` 切主题，`E` 导出 CSV
- 导出当前筛选的 CSV 或 Markdown
- 生成 Token 护照、Token 收据分享卡
- 数据、CSS 与 JavaScript 全部内嵌，无 CDN、无网络请求

## 隐私与安全

工具只读本地文件，**不会上传任何数据**。日志按文件 `mtime + size` 缓存到 `out/cache.json`，未变化时可快速复用。

但“本地生成 / 离线可用”不等于“已经匿名”：

- `out/dashboard.html` 可能包含完整项目工作目录（cwd）、会话标识、逐轮 token 序列。
- Top 会话标题可能来自 `out/session_summaries.json`，或从会话首条内容提取，因此可能出现自然语言摘要。
- 生成文件一旦复制、上传或发送，其中的内嵌数据也会一起离开本机。

**不要未经检查公开分享真实 Dashboard。** 分享前请搜索并移除用户名、主目录、项目/客户/仓库名、会话标识和摘要文本；更安全的做法是分享终端汇总截图、脱敏截图或合成数据演示。详见 [`docs/data-and-privacy.html`](docs/data-and-privacy.html)。

## 数据来源

| CLI | 本地日志路径 |
|---|---|
| Claude Code | `~/.claude/projects/**/*.jsonl` |
| Gemini CLI | `~/.gemini/tmp/<hash>/chats/session-*.json` |
| Codex | `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` |

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
| `docs/` | 零构建中文静态文档站 |
| `tests/test_docs.py` | 文档完整性、链接与隐私泄漏检查 |

## Roadmap

- [ ] `$` 成本估算（按模型单价表）
- [ ] `tokens serve` 本地 live dashboard（自动刷新）
- [ ] 包结构重构：flat → `tokens/` 包，统一 `python -m tokens`
- [ ] 按 cwd / 项目维度拆分用量
- [ ] Windows 兼容（`open` → `os.startfile`）

## License

MIT
