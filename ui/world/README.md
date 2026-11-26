# Token 山境：独立交互样机

状态：独立合成样机（自然写实方向），尚未获用户视觉确认，不作为发布候选。生产 Dashboard、服务、采集不变；费用显示在样机内只读接入共享费用核心 `src/tokens_cli/dashboard_assets/cost_core.js`（classic script 暴露 `globalThis.CostCore`），价格数学与官方参考价未做任何变更。渲染资源泄漏与阴影绘制超预算已修复，合同验收结果见测试报告；初始化长任务仍未消除，不宣称视觉认可或整体性能通过。历史构建与测试数字保留在对应历史报告，不在本文复述。

## 使用与构建

在仓库根目录运行（Node 只用于开发构建；生成 HTML 运行时无需 Node）：

```sh
npm --prefix ui/world ci --ignore-scripts --no-audit --no-fund
npm --prefix ui/world run build
python3 scripts/build_world_prototype.py
```

生成器默认在新的系统临时目录输出 `index.html` 并打印路径、大小与 SHA-256。直接本机浏览器打开，所有代码/样式/合成数据内联，无 CDN、字体/模型下载和供应商请求。指定 `--output /path/to/new/index.html` 时目标必须不存在；不覆盖旧报告。

- 沿页面自然滚动：峰顶 → 草坡 → 村庄。顶部导航可直接跳章节。
- 山顶热点/路标/房屋：悬停或键盘聚焦看预览，点击看详情。触屏场景物体第一次轻点预览，再点查看；可见 HTML 标签直接打开详情。
- 模型筛选影响日期与项目聚合；项目检查不改变全局筛选。
- “数据视图”、项目列表/搜索和日期表提供完整精确入口。
- 系统减少动画或手动开关关闭视差/连续飞行；WebGL/forced-colors/context loss 使用数据视图。
- 主题和语言只在样机当前页面内切换，不读写任何 `tk-*` 存储。
- 信息层：常驻显示全部模型当天（报告日 2026-10-13 UTC）的 Token 与调用次数，以及 2026-10-01—2026-10-13 载入区间累计费用；主数字不随场景筛选变化。明细提供全部模型／当前筛选，范围、口径未知、待定价、免费与页面内临时价格均显式标注。

## 目录职责

| 文件 | 职责 |
| --- | --- |
| `terrain.js` | 固定种子山脊、三角网高度/法线/遮挡、避道路的村落槽位 |
| `paths.js` | 将路面裁切到实际地形三角面；短入口步道 |
| `materials.js` | 本地颜色/法线/粗糙度纹理与资源所有权（含内联的 Poly Haven CC0 离线资产，见 DEPENDENCIES.md） |
| `scene.js` | 连续山谷、实例化植被、木石房屋、有限阴影、镜头/拾取/释放 |
| `scene-data.js` | 纯函数投影既有聚合；稳定房屋位置，不推算项目费用 |
| `app.js` | HTML 交互、标注、筛选、明细、降级 |
| `prototype.html` / `prototype.css` | 章节与可访问数据层 |
| `build.mjs` | 锁定依赖打包为单 IIFE，保留 Three.js 许可，禁止源映射/不安全内联 |
| `package-lock.json` | 精确依赖与 npm 完整性锁 |
| `DEPENDENCIES.md` / `THIRD_PARTY_LICENSES.txt` | 依赖审查记录与许可 |
| `generated/` | 被忽略的可重建 bundle，不发布 |
| `node_modules/` | 被忽略的本地构建依赖，不发布 |

## 数据边界

生成器只调用 `demo.build_demo`，固定 UTC 与日期 2026-10-13，观察 2026-10-01 至 2026-10-13。显式传合成 `session_titles`，并阻断真实会话摘要/索引读取。没有真实日志输入参数。

海拔只是导航；花草、小屋大小不编码用量；模型配色只用 payload 固定色。有限房屋与完整的载入聚合项目列表分离，不声称原始采集完整。当天用量锚定报告日期，不回落到最近一天；费用接入共享费用核心，累计仅覆盖 2026-10-01—2026-10-13 载入区间。覆盖不完整时显示已定价小计，而非总体实付。合法范围外账本行跳过；`uncertain === true` 整行记口径未知、不计价；缺价待定价、显式零价免费。价格编辑仅存当前页面内存，不读写 `tk-*` 存储、不修改参考价，禁止按 Token 比例制造项目费用。少数模型仅在复制的合成 fixture 中重标注为参考价已覆盖的精确 ID，不代表真实模型调用；公共 demo 与真实 readers 不变。匿名适配只消费已有别名，Other 不展开原名。

## 测试

```sh
python3 -m unittest discover -s tests -p 'test_world*.py' -v
TOKENS_WORLD_BROWSER=webkit python3 -m unittest discover -s tests -p 'test_world_runtime.py' -v
```

WebGL 测试必须真正初始化一个 renderer；降级不能代替 3D 验收。Chromium 使用新的独立临时 persistent profile，basic store/mock-keychain、禁同步/扩展。不复用个人资料；发生钥匙串提示必须停。

测试只证明合同/布局/交互，不证明视觉惊艳，也不证明移动真机帧率。用户实际本机体验确认前，不集成生产。

2026-10-13 本机 headless Chromium 11 段采样（包括桌面阴影绘制）：最多 32 draw calls、86,364 triangles，低于 150 / 120,000 合同。当天数字首次可读约 110 ms，首次内容绘制约 52 ms；最长任务仍达 707 ms，最大 CPU 帧提交约 5.4 ms、标签投影约 0.4 ms。几何重建资源增长与阴影超预算已修复，但初始化／渲染停顿尚未消除。这些是单次本机测量，不是 GPU 完成时间、真实 FPS 或移动真机性能保证。

## 维护与清理

源码与锁/许可必须一起保留。构建输出只进 `generated/`，报告只进单独临时目录，不能拷进 Python 包或 `docs/demo`。本轮未删除旧文件。失败日志与旧冻结产物保留；不得 `git clean`、`reset --hard`、批量删临时目录/未提交文件。开发依赖仅在确认后不再构建且核用途后清理；不能删锁文件代替维护。
