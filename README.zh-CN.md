<div align="center">
  <img src="https://raw.githubusercontent.com/LingXi-fur/tokens/main/docs/favicon.svg" width="76" height="76" alt="tokens logo">

# tokens

**看清 AI 编程 Token 流向，同时不把本地日志上传到任何地方。**

把本机 Claude Code、Gemini CLI 与 Codex 记录变成终端摘要、仅限回环地址的实时 Dashboard，或一个自包含离线 HTML 文件。

[![在线 Demo](https://img.shields.io/badge/demo-在线体验-2f6fd6)](https://lingxi-fur.github.io/tokens/demo/)
[![CI](https://github.com/LingXi-fur/tokens/actions/workflows/ci.yml/badge.svg)](https://github.com/LingXi-fur/tokens/actions/workflows/ci.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-5b8def)](https://github.com/LingXi-fur/tokens/blob/main/pyproject.toml)
[![License](https://img.shields.io/badge/license-MIT-f59e0b)](https://github.com/LingXi-fur/tokens/blob/main/LICENSE)
[![Privacy](https://img.shields.io/badge/privacy-local--first-a78bfa)](#隐私边界)

[体验交互 Demo](https://lingxi-fur.github.io/tokens/demo/) · [克隆并运行](#克隆并运行) · [在线文档](https://lingxi-fur.github.io/tokens/zh/) · [Dashboard 指南](https://lingxi-fur.github.io/tokens/zh/dashboard.html) · [English](https://github.com/LingXi-fur/tokens/blob/main/README.md)

**用自己的数据前先看看：**在浏览器打开[合成 Dashboard](https://lingxi-fur.github.io/tokens/demo/)，无需安装、账户或本地日志。在线页面可交互，但不会实时读取你的电脑；克隆后可用 `./run demo --open` 在本机体验。

</div>

[![tokens Dashboard 合成数据预览](https://raw.githubusercontent.com/LingXi-fur/tokens/main/docs/assets/readme-preview.png)](https://lingxi-fur.github.io/tokens/demo/)

> 预览由真实 Dashboard 使用虚构记录生成，不含真实本地日志、私有路径、会话标识或路由配置。

## 不用自己的日志也能体验

打开[交互式合成 Demo](https://lingxi-fur.github.io/tokens/demo/)，用虚构记录体验 Dashboard。在线 Demo 不会读取本机数据，也不实时刷新本机日志；克隆后运行 `./run demo --open` 可生成同类本地示例报告。

## 为什么值得用？

AI 编程工具在本机留下用量记录，但格式和 Token 口径不同。`tokens` 提供可检查的本地视图：

- **在同一份报告中查看 Claude Code、Gemini CLI 与 Codex**，同时保留各来源的计数语义。
- **找到值得继续查看的变化：**日 / 周 / 月趋势、两个时段的对比与用量峰值。
- **追溯已有记录：**在来源字段允许时，查看模型、来源、项目和会话的用量构成。
- **掌握输出：**精确表格、CSV / Markdown、本机实时刷新和自包含的离线 HTML 快照。

本地 CLI 与 Dashboard 无需账户、遥测端点、托管后端或外部运行资源；AI 编程工具和本站有各自的网络政策。核心解析、聚合、报告和回环服务使用 Python 标准库。Windows 另需纯数据包 `tzdata` 才能稳定使用 IANA 时区。

## 克隆并运行

要求：macOS、Linux 或 Windows 上的 Python 3.9+。分析自己的用量还需要受支持 AI 编程 CLI 已生成的本地日志；合成 Demo 不需要日志。

```bash
git clone https://github.com/LingXi-fur/tokens.git
cd tokens
./run doctor
./run serve --open
```

默认只扫描 Claude。如果你使用 Gemini CLI 或 Codex，请给 `serve` 加上 `--source gemini` 或 `--source codex`；重复 `--source` 可以组合来源，否则这些日志不会出现在报告中。

`./run doctor` 检查路径、候选文件数、时区、输出和缓存权限，不解析消息正文，也不打印项目或会话标识。

实时 Dashboard 只绑定 `127.0.0.1`。默认每 5 分钟检查本地日志变化；页面可改为 1、5、15、30 分钟或暂停。文件未变化时不会重新解析或传输。

还没有本地日志？可先打开由同一报告管线生成的完整合成 Dashboard：

```bash
./run demo --open
```

Demo 只使用生成的示例数据写入 `out/dashboard-demo.html`，不会读取 Claude Code、Gemini CLI 或 Codex 日志。

需要离线归档时：

```bash
./run dashboard --open
```

### Windows 源码检出

先在本地虚拟环境中安装源码检出；这也会安装必需的 `tzdata`：

```powershell
git clone https://github.com/LingXi-fur/tokens.git
cd tokens
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
tokens doctor
tokens serve --open
```

如果使用 Gemini CLI 或 Codex，请给 `tokens serve --open` 加上 `--source gemini` 或 `--source codex`。

### 可选：安装本地命令

在已克隆的源码目录中创建虚拟环境，并以 editable 方式安装：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
tokens doctor
tokens serve --open
```

Windows PowerShell 激活命令为 `.venv\Scripts\Activate.ps1`。

这会从本地源码检出安装，不依赖任何已发布的软件包注册表版本。

## 选择输出方式

| 目标 | 源码检出命令 | 行为 |
|---|---|---|
| 快速看终端摘要 | `./run day` | 最近 14 天终端报告 |
| 安装前在线体验 | [打开在线合成 Demo](https://lingxi-fur.github.io/tokens/demo/) | 无需 clone、账号、本地日志或上传 |
| 本机无日志体验 | `./run demo --open` | 只用合成数据，写入 `dashboard-demo.html` |
| 长期开着 Dashboard | `./run serve --open` | 仅限回环地址的服务，页面内更新 |
| 保存离线归档 | `./run dashboard --open` | 自包含的生成时快照 |
| 准备更安全的分享副本 | `./run dashboard --anonymize --open` | 对选定标识做假名化 |

报告默认写入 `./out`；可用 `--output DIR` 更改位置。

## 能看出什么？

找出用量最高的日子，对比两个等长时段，并查看哪些**已有记录**中的模型、项目或会话构成了差异。在来源确实提供相应字段时，你可以：

- **发现变化：**查看日 / 周 / 月趋势、峰值时段与 Token 构成。
- **追溯记录：**按来源和模型筛选，查看项目与会话聚合；非脱敏 Dashboard 还可查看归入 Other 的原始模型名。
- **核对数字：**从图表切换到精确表格，导出 CSV / Markdown，或保存自包含离线 HTML 快照。

交互方法、双时段透镜、峰值剖面、成就中心等见[中文 Dashboard 指南](https://lingxi-fur.github.io/tokens/zh/dashboard.html)。A/B 只比较记录中的 Token 构成，不能证明用量变化的原因；基线为零时只报告绝对 Token 变化。项目和会话是平行聚合，不会自动配对。选定的 A/B 周期及打开的峰值剖面可能从 URL 恢复；项目 / 会话 ID 与精确 Token 明细不会写入 URL。

Token 增减只描述用量变化，不代表生产力或代码质量。Cache Read 是缓存 Token 读取量，不是已确认的货币节省。


## 支持的数据源

| 来源 | 默认本地路径 | 项目数据 | 会话数据 | 计数说明 |
|---|---|---:|---:|---|
| Claude Code | `~/.claude/projects/**/*.jsonl` | 有 | 有 | 总量为 input + output + cache read + cache write。 |
| Gemini CLI | `~/.gemini/tmp/*/chats/session-*.json` | 通常无 | 有 | 有来源 `tokens.total` 时优先使用。 |
| Codex | `~/.codex/sessions/**/rollout-*.jsonl` | 通常无 | 通常无 | cached input 已包含在 input 中，不重复相加。 |

默认只扫描 Claude。重复指定 `--source` 可组合来源：

```bash
./run serve \
  --source claude \
  --source gemini \
  --source codex \
  --open
```

各工具公开的 Token 语义并不完全相同。`tokens` 保留各来源报告的总量，不伪装成绝对同口径。

## CLI 要点

```text
./run [day|week|month|all|dashboard|demo|serve|doctor] [options]
tokens [day|week|month|all|dashboard|demo|serve|doctor] [options]  # 本地安装后
```

| 参数 | 用途 |
|---|---|
| `--source claude\|gemini\|codex` | 选择来源，可重复。 |
| `--since YYYY-MM-DD` / `--until YYYY-MM-DD` | 限制闭区间日期范围。 |
| `--timezone AREA/CITY` | 覆盖检测到的系统时区。 |
| `--lang en\|zh` | 终端及静态 HTML 语言；默认跟随系统 locale（可由 `TOKENS_LANG` 覆盖）。 |
| `--output DIR` | 指定报告目录，默认 `./out`。 |
| `--html` | 为终端模式额外生成静态 HTML。 |
| `--anonymize` | 在 Dashboard 或实时模式中假名化标识。 |
| `--interval SECONDS` | 设置实时检查初始间隔；最小 1，默认 300。 |
| `--port PORT` | 设置回环端口；默认 8765，0 表示自动选择。 |
| `--open` | 用默认浏览器打开生成文件或本机 URL。 |
| `--no-cache` | 重新读取所有选中的日志文件。 |

完整说明见[中文 CLI 文档](https://lingxi-fur.github.io/tokens/zh/cli.html)。

## 隐私边界

`tokens` 在本机读取和分析文件。离线快照不发起网络请求；实时模式只与同源的 `127.0.0.1` 服务通信，并且没有局域网绑定选项。可选的 `~/.claude-code-router/custom-router.js` 仅在本机按文本读取，不执行、不上传；Router 规则只用于解释普通 Claude 请求别名，不会改写 Gemini 或 Codex 模型名。

普通 Dashboard 仍可能包含：

- 项目路径和工作目录
- 会话标识与本地派生标题
- 精确日期、模型、Token 数值和逐轮 Token 序列
- 可能识别个人或组织的行为模式

`--anonymize` 会将项目路径、会话标识与自然语言标题替换为报告内别名，但仍保留精确日期、保留独立身份的模型名、Token、关系和逐轮回放。非脱敏 Dashboard 还会显示归入图表 Other 色槽的原始模型名和精确用量；脱敏导出不包含这些被折叠的原名。经 Router 解析出的 backend 名也可能透露本地路由配置。因此它是**假名化，不是保证匿名**。

分享报告前：

1. 使用 `./run dashboard --anonymize`，确认分享的是 `dashboard-anonymized.html`，不是旧的普通 `dashboard.html`
2. 限制日期范围
3. 检查生成文件及其内嵌数据，也检查将要分享的截图、导出内容和视图 URL
4. 搜索用户名、客户名、仓库名和自定义模型标签
5. 不要向公开 Issue 附加原始日志

详见[数据与隐私文档](https://lingxi-fur.github.io/tokens/zh/data-and-privacy.html)。

## 当前边界

- 当前公共安装入口是源码检出；在确认存在可用发布版本前，不宣传软件包注册表安装命令。
- Claude 是唯一默认来源；Gemini 与 Codex 必须显式选择。
- 来源格式提供的字段不同，部分项目、会话或 Context 视图可能不可用。
- 终端和静态报告支持 `--lang en|zh`，默认跟随系统 locale；交互式 Dashboard 可在页面内切换语言。
- 离线 Dashboard 是生成时快照。需要持续更新时使用 `./run serve --open`。

## 故障排查

**没有找到日志？** 运行 `./run doctor`。如果未使用 Claude，尝试 `./run day --source gemini` 或 `./run day --source codex`。完全没有本地日志时可运行 `./run demo --open`；已安装本地命令则使用 `tokens demo --open`。

**Dashboard 数字不更新？** `./run dashboard` 生成离线快照；实时更新请使用 `./run serve --open`。

**浏览器没有自动打开？** 命令仍会打印生成路径或本机 URL，可手动打开。

更多答案见[中文 FAQ](https://lingxi-fur.github.io/tokens/zh/faq.html)。

## 开发

Node.js 22+ 仅用于开发检查；运行 CLI 或 Dashboard 不需要 Node.js。

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
python -m compileall -q src tests
node --check src/tokens_cli/dashboard_assets/dashboard.js
node --check docs/assets/site.js
```

测试覆盖读取器、缓存失效、打包、CLI 校验、假名化、Dashboard 合同、文档链接、无障碍、隐私断言和回环实时更新。

## 贡献与安全

欢迎真实的 bug 报告和聚焦的 Pull Request。请先阅读 [CONTRIBUTING.md](https://github.com/LingXi-fur/tokens/blob/main/CONTRIBUTING.md)，复现时只使用合成数据。

安全或隐私问题请按 [SECURITY.md](https://github.com/LingXi-fur/tokens/blob/main/SECURITY.md) 私下报告，不要创建包含真实日志或未经检查 Dashboard 的公开 Issue。

如果 `tokens` 对你有帮助，可以点一颗 star，让更多需要本地优先 Token 分析的人发现它；真实的平台反馈和 bug 报告更有价值。

## License

[MIT](https://github.com/LingXi-fur/tokens/blob/main/LICENSE)
