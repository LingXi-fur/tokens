# 0.3.0 本机候选发布核对清单（Release Candidate Checklist）

本清单是**待执行**的核对项，不记录任何已完成状态。在每一项被实际执行并留下证据之前，不得勾选，也不得声称「已构建」「已测试」「已发布」。0.3.0 目前是**未公开发布**的本机候选：没有公开发布日期，不声称 PyPI 或任何软件包注册表已有 0.3.0。对外发布（GitHub tag、PyPI、Pages 更新）属于第三阶段，需**独立授权与敏感审查**，本清单不构成授权。

命名说明：`docs/` 站点是 HTML，本文件与 `monthly-budget-design.md` 是仓库级 Markdown 文档，命名沿用本仓库小写连字符习惯；它们不进入 GitHub Pages 站点构建，除非后续明确加入。

## 阶段一：准备（Preparation）

版本与元数据：

- [ ] `pyproject.toml` 的 `version = "0.3.0"` 与 `src/tokens_cli/__init__.py` 的 `__version__` 一致（均为 0.3.0）。
- [ ] 核验 `tests/test_release_contracts.py` 覆盖版本一致、四个内联资产包含与 CLI 入口；运行契约测试并在独立验收记录中记录结果与证据。本清单不预填任何「已通过」状态。
- [ ] CHANGELOG `[Unreleased]` 标注为 0.3.0 本机候选、未正式发布；无任何伪造的公开发布日期或「已发布」记录。
- [ ] 中英 README 候选段落与实际功能一致；无「PyPI 已有 0.3.0」表述、无未经验证的版本徽章。

源码白名单暂存区（clean staging）：

- [ ] 建立全新临时构建目录，**只**按明确文件白名单拷贝：`pyproject.toml`、`README.md`、`README.zh-CN.md`、`CHANGELOG.md`、`LICENSE`、`src/tokens_cli/` 下 16 个已列明 Python 模块，以及 `dashboard_assets/` 下四个资产 `template.html`、`dashboard.css`、`cost_core.js`、`dashboard.js`（共享费用核心必须先于 Dashboard 脚本内联）。禁止整目录复制；本轮 `run`、`tests/`、`docs/` 不进入暂存区或 sdist，不承诺 source dist 可复现测试与文档。
- [ ] 使用冻结后的精确路径→SHA256 manifest 核对源文件；原保护基线另行核验，不以计划内改动覆盖旧证据。拒绝源符号链接、仓库外解析路径或任何哈希漂移。
- [ ] 不使用 `git archive`（会丢失必要未跟踪改动）；不拷贝旧 `build/`、`*.egg-info`、`out/`、`__pycache__`、缓存、失败日志、冻结报告或任何私人产物。
- [ ] 白名单之外发现「必须打包」的新文件时，先停下更新白名单并说明，不得整目录拷贝。

工具与依赖（离线纪律）：

- [ ] 预先核验本机 `setuptools>=77`、`wheel`、`build`、`twine` 已存在。任一缺失即为**阻塞**：报阻塞说明缺口，不联网下载，不用其他工具替代后声称等效。
- [ ] 全程不联网：构建、安装、冒烟均不得访问网络。

## 阶段二：本机构建与纯净核验（Local Build and Clean Verification）

构建：

- [ ] 在白名单暂存区执行 `python3 -m build --no-isolation`（离线），产出 sdist + wheel。
- [ ] 产物写入**新的候选目录**，不覆盖旧产物。
- [ ] `twine check` 通过；保留成员审查摘要与校验文件（如 `*.sha256`）。

产物内容审查：

- [ ] 核对元数据：版本 0.3.0、名称 `ai-cli-tokens`、CLI 入口 `tokens`。
- [ ] wheel 成员**仅允许** `tokens_cli/` 包与 `*.dist-info/`；三类内联 dashboard 资产（JS/HTML/CSS）在包内。
- [ ] sdist 核对明确成员清单；不声称未逐项验证的 tests/docs 可复现性。
- [ ] 拒绝：绝对路径或 `..` 穿越、符号链接成员、密钥/私人日志/缓存/历史冻结证据混入。对 sdist/wheel 全成员做路径与敏感字串扫描。

纯净环境安装冒烟（隔离三要素：HOME、venv、cwd）：

- [ ] 全新临时 `HOME`、全新 venv、全新 cwd；清空 `PYTHONPATH` 与干扰环境变量，确保离线。
- [ ] `pip install --no-index --no-deps <候选wheel>` 安装。
- [ ] `python -c "import tokens_cli, sys; print(tokens_cli.__file__)"` 确认 import 来自该 venv site-packages，而非源码检出或工作目录。
- [ ] `tokens --version` 输出 `0.3.0`；`tokens doctor` 通过。
- [ ] 合成 dashboard（`tokens demo`）三类资产完整；在浏览器中交互冒烟（含费用账本：参考价显示、手填价、恢复官方参考、CSV 本地下载），只用合成数据，不使用真实用户日志。
- [ ] 候选目录中保留本次核验的记录摘要（不含私人金额、路径或会话标识）。

边界与诚实标注：

- [ ] 任一步骤失败：**不使用候选 wheel 安装或替换本机服务**、不声称候选通过；保留失败证据，报阻塞。
- [ ] 未验证的平台（如本清单执行机器之外的 OS/架构）明确标注「未验证」，不得表述为「全平台通过」。
- [ ] 使用候选 wheel 安装或替换本机服务（`local.tokens.serve` 相关），仅在以上全部通过后、按计划单独执行；失败即回退不更新。另行授权的已测试源码检出服务重启，不属于本清单的候选产物验收，不据此勾选任何核对项。

## 阶段三：外发（External Release）——需独立批准，本轮禁止

- [ ] **前置**：获得用户对公开发布的**独立明确授权**；本清单与 0.3.0 本机候选状态不构成该授权。
- [ ] 敏感审查：对将公开的全部差异做路径、密钥、私人数据、日志与配置残留复查；`.github/workflows/publish-pypi.yml` 等保护文件未在授权外被改动。
- [ ] 公开发布日期只在真正发布时产生并记录，不得预先编造。
- [ ] 发布渠道（tag、PyPI、Pages）按届时授权范围执行；发布后回填 CHANGELOG 日期与链接。

## 记录模板

每次执行本清单时，另建带时间戳的记录文件，逐项记录：通过/失败/未执行、证据文件路径、阻塞原因。未执行的项保持未勾选。
