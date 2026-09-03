<div align="center">
  <img src="https://raw.githubusercontent.com/LingXi-fur/tokens/main/docs/favicon.svg" width="76" height="76" alt="tokens logo">

# tokens

**看清 AI 编程 Token 流向，同时不把本地日志上传到任何地方。**

把 Claude Code、Gemini CLI 与 Codex 已经保存在电脑上的日志，变成终端报告、本机实时 Dashboard 或单文件离线快照。

[![PyPI](https://img.shields.io/pypi/v/ai-cli-tokens?color=5b8def)](https://pypi.org/project/ai-cli-tokens/)
[![Python](https://img.shields.io/pypi/pyversions/ai-cli-tokens)](https://pypi.org/project/ai-cli-tokens/)
[![CI](https://github.com/LingXi-fur/tokens/actions/workflows/ci.yml/badge.svg)](https://github.com/LingXi-fur/tokens/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-f59e0b)](https://github.com/LingXi-fur/tokens/blob/main/LICENSE)
[![Privacy](https://img.shields.io/badge/privacy-local--first-a78bfa)](#隐私边界)

[安装](#安装) · [30 秒开始](#30-秒开始) · [Dashboard 文档](https://lingxi-fur.github.io/tokens/zh/dashboard.html) · [English](https://github.com/LingXi-fur/tokens/blob/main/README.md)

</div>

![tokens Dashboard 合成数据预览](https://raw.githubusercontent.com/LingXi-fur/tokens/main/docs/assets/readme-preview.svg)

> 上图全部使用合成数据。`tokens` 不上传日志，但生成的报告仍可能包含敏感的本地元数据；分享前请阅读[隐私边界](#隐私边界)。

## 为什么用 tokens？

AI 编程工具已经在本机记录了有价值的使用数据，但各自的日志格式和 Token 口径不同。`tokens` 提供一个可检查、可离线使用的统一视图：

- 同时支持 **Claude Code、Gemini CLI 与 Codex**
- 按日、周、月查看模型与来源趋势
- 在来源字段允许时探索项目、会话、Context 构成和逐轮回放
- 本机实时页面热更新，不整页刷新
- 导出数据、CSS、JavaScript 全内嵌的单个 HTML 文件
- 无账户、遥测、托管后端、数据库、CDN 或日志上传

核心数据管线和本机服务使用 Python 标准库。Windows 安装会额外包含纯数据包 `tzdata`，以稳定支持 IANA 时区。

## 安装

### 推荐：pipx

```bash
pipx install ai-cli-tokens
tokens doctor
tokens serve --open
```

PyPI 包名是 `ai-cli-tokens`，安装后的命令仍然是 `tokens`。

<details>
<summary>其他安装方式</summary>

使用 pip：

```bash
python -m pip install --user ai-cli-tokens
tokens --version
```

从源码运行：

```bash
git clone https://github.com/LingXi-fur/tokens.git
cd tokens
./run doctor
./run serve --open
```

Windows 从源码运行时，可以先设置 `PYTHONPATH=src`，再执行：

```powershell
python -m tokens_cli doctor
```

</details>

要求 Python 3.9+，支持 macOS、Linux 和 Windows；电脑上至少有一种受支持 AI CLI 生成的本地日志。

## 30 秒开始

```bash
# 1. 安全检查可用日志，不读取消息正文
tokens doctor

# 2. 打开仅限本机的实时 Dashboard
tokens serve --open

# 3. 或生成可归档的离线单文件快照
tokens dashboard --open
```

`tokens doctor` 只检查日志位置、候选文件数、时区、输出和缓存权限，不解析消息内容，也不打印项目或会话标识。

实时服务只绑定 `127.0.0.1`，默认每 5 分钟检查本地日志变化。页面可选择 1、5、15、30 分钟或暂停；文件未变化时不会重复解析、聚合或传输。

## 选择适合的输出

| 目标 | 命令 | 行为 |
|---|---|---|
| 快速看终端摘要 | `tokens day` | 最近 14 天终端报告 |
| 长期开着 Dashboard | `tokens serve --open` | 本机回环服务，页面内热更新 |
| 保存离线归档 | `tokens dashboard --open` | 生成时快照，单文件离线可用 |
| 准备更安全的分享副本 | `tokens dashboard --anonymize --open` | 对选定标识做假名化 |

报告默认写入当前目录的 `./out`；可用 `--output DIR` 更改位置。

## Dashboard 能看什么？

主路径包括总 Token、趋势、模型构成、来源、项目与会话。需要深入时，还可以使用：

- **Data Trail · 数据寻迹**：从选定周期进入项目、会话或 Context 证据，不暗中修改全局筛选
- **Signal Lens · 信号透镜** 与 **Exactness Key · 精确层**
- **Context Reuse River · Context 复用之河**：Fresh Input、Output、Cache Read、Cache Write 与 Other
- 项目透镜与会话回放；每个会话最多保留最近 200 轮
- Token 年鉴、成就、作息视图和本地 Furry Token 伙伴

Data Trail 状态只存在页面内存，不写入 URL 或 `localStorage`。项目与会话保持为平行聚合，不自动配对。固定上一期对比可以写入 URL 的 `compare=1`，但项目 / 会话 ID 与精确 Token 明细不会写入 URL。

Token 增减只描述使用量变化，不代表生产力或代码质量。Cache Read 是缓存 Token 读取量，不等于已确认的货币节省。

## 支持的数据源

| 来源 | 默认本地路径 | 项目数据 | 会话数据 | Token 口径说明 |
|---|---|---:|---:|---|
| Claude Code | `~/.claude/projects/**/*.jsonl` | 有 | 有 | 总量为 input + output + cache read + cache write。 |
| Gemini CLI | `~/.gemini/tmp/*/chats/session-*.json` | 通常无 | 有 | 优先使用来源的 `tokens.total`。 |
| Codex | `~/.codex/sessions/**/rollout-*.jsonl` | 通常无 | 通常无 | cached input 已包含在 input 中，不重复相加。 |

默认只扫描 Claude。重复指定 `--source` 可以组合来源：

```bash
tokens serve \
  --source claude \
  --source gemini \
  --source codex \
  --open
```

各工具公开的 Token 语义并不完全相同，`tokens` 会保留来源报告的总量，不伪装成绝对同口径。

## 常用参数

```text
tokens [day|week|month|all|dashboard|serve|doctor] [options]
```

| 参数 | 用途 |
|---|---|
| `--source claude\|gemini\|codex` | 选择来源，可重复。 |
| `--since YYYY-MM-DD` / `--until YYYY-MM-DD` | 限制闭区间日期范围。 |
| `--timezone AREA/CITY` | 覆盖系统时区。 |
| `--output DIR` | 指定报告目录，默认 `./out`。 |
| `--html` | 为终端模式额外生成静态 HTML。 |
| `--anonymize` | 在 Dashboard 或实时模式中假名化标识。 |
| `--interval SECONDS` | 设置实时检查初始间隔；最小 1，默认 300。 |
| `--port PORT` | 本机端口，默认 8765；0 表示自动选择。 |
| `--open` | 用默认浏览器打开结果。 |
| `--no-cache` | 重新读取所选日志。 |

完整说明见[中文 CLI 文档](https://lingxi-fur.github.io/tokens/zh/cli.html)。

## 隐私边界

`tokens` 在本机读取和分析文件。离线快照不发起网络请求；实时模式只与同源的 `127.0.0.1` 服务通信，并且没有局域网绑定选项。

普通 Dashboard 仍可能包含：

- 项目路径和工作目录
- 会话标识与本地派生标题
- 精确日期、模型、Token 数值和逐轮序列
- 可能识别个人或组织的行为模式

`--anonymize` 会将项目路径、会话标识与自然语言标题替换为报告内别名，但仍保留精确日期、模型、Token、关系和逐轮回放。因此它是**假名化，不是保证匿名**。

分享报告前：

1. 优先使用 `tokens dashboard --anonymize`
2. 限制日期范围
3. 人工检查文件或截图
4. 搜索用户名、客户名、仓库名和自定义模型名
5. 不要向公开 Issue 附加原始日志

详见[数据与隐私文档](https://lingxi-fur.github.io/tokens/zh/data-and-privacy.html)。

## 常见问题

**提示没有日志？** 先运行 `tokens doctor`。如果你只使用 Gemini 或 Codex，尝试 `tokens day --source gemini` 或 `tokens day --source codex`。

**Dashboard 数字不更新？** `tokens dashboard` 是离线快照；实时更新请使用 `tokens serve --open`。

**浏览器没有自动打开？** 命令仍会打印文件路径或本机 URL，可以手动打开。

**pip 安装后找不到命令？** 推荐使用 `pipx`，或把 Python 用户脚本目录加入 `PATH`。

更多答案见[中文 FAQ](https://lingxi-fur.github.io/tokens/zh/faq.html)。

## 更新与卸载

```bash
pipx upgrade ai-cli-tokens
pipx uninstall ai-cli-tokens
```

卸载 Python 包不会自动删除当前目录下的 `./out` 报告或平台用户缓存。

## 开发与贡献

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
python -m compileall -q src tests
node --check src/tokens_cli/dashboard_assets/dashboard.js
```

欢迎真实的 bug 报告和聚焦的 Pull Request。请先阅读 [CONTRIBUTING.md](https://github.com/LingXi-fur/tokens/blob/main/CONTRIBUTING.md)，复现时只使用合成数据。

安全或隐私问题请按 [SECURITY.md](https://github.com/LingXi-fur/tokens/blob/main/SECURITY.md) 私下报告，不要创建包含真实日志的公开 Issue。

如果 `tokens` 对你有帮助，可以点一颗 star，让更多需要本地优先 Token 分析的人发现它；真实的平台反馈和 bug 报告更有价值。

## License

[MIT](https://github.com/LingXi-fur/tokens/blob/main/LICENSE)
