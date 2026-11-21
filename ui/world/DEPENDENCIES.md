# 构建依赖审查

核验日期：2026-10-13。仅独立合成样机；不改变生产依赖、全局环境或其他供应商配置。

| 包 | 精确版本 | 许可 | 用途 | 安装脚本 |
| --- | --- | --- | --- | --- |
| `three` | `0.186.1` | MIT | 唯一运行时渲染依赖；内联到 HTML | 无 |
| `esbuild` | `0.28.2` | MIT | 开发期打包 | 有 `postinstall: node install.js`，安装时禁用 |
| `@esbuild/darwin-arm64` | `0.28.2` | metadata 声明 MIT | 当前 Mac 构建二进制，可选平台依赖 | 无 |

来源：`registry.npmjs.org` 对应固定版本 metadata 与 tarball。下载校验 metadata 的 SHA-512 integrity；以下 SHA-256 记录下载包身份，不代替锁文件 integrity：

- `three`: `8cd068708ea44f2c73c944b1cead2ba2f0d5c15c8fc194e5700f4e4f4a033fe7`
- `esbuild`: `e045f94c235c7adc50e77ba2a579c7bec41b496b6b47c3a7845f7c1e19959a88`
- `@esbuild/darwin-arm64`: `1980cde09749094452b20d36ff267585ccb3f72749c7bc97291cd9996ccf5a2a`

实际读取 `three/LICENSE` 和 `esbuild/LICENSE.md`；全文保存在本目录 `THIRD_PARTY_LICENSES.txt`。平台二进制包无独立 LICENSE 文件；不能声称核过该包的独立许可实文。其 metadata 许可与父 esbuild 许可分别记录。

`package-lock.json` 为 v3，包含平台可选依赖；不是 29 个运行时库。首次安装使用 `--ignore-scripts --no-audit --no-fund`。复现用 `npm ci`，不能用无锁 `npm install` 或浮动 latest 更新代替。跨平台二进制尚未实际构建验收，不保证所有平台安装通过。

运行产物为 Three.js、原创样机代码与内联的 Poly Haven 离线资产（见下节）；esbuild 不进入浏览器。Three.js 完整许可由 `build.mjs` 添加至 bundle banner，保留内联 legal comments，无 source map。无 React/GSAP/物理引擎/外部模型或字体文件。公开仓库仅参考交互思想，没有复制示例资产。

## 离线美术资产

除原创纹理外，样机内联两组 Poly Haven 资产（CC0 1.0 通用，无署名义务），预先下载后由 `assets/textures.js` 提供给 `materials.js`，运行时无任何网络请求。资产来源、作者、通道、尺寸与校验记录见 `assets/README.md` 和 `assets/manifest.json`；仅使用漫反射与 OpenGL 法线，粗糙度仍由程序生成，不是完整扫描 PBR 材质。两组原图合计 3,831,966 字节，不超过 4 MiB；最终生成 HTML 大小预算不超过 8 MiB。这些资产不进 npm 依赖、不写锁文件；npm 包版本、完整性、许可与安装脚本均无变更。

## 当前限制

曾因执行权限规则拒绝而停止重构建/复测，没有绕过或调用代理代执行。2026-10-13 用户随后手动完成低模版重构建（bundle 579,145 字节），其后合成/Chromium 13/13、WebKit 7/7 复测通过，作为历史记录保留。后续自然写实迭代在当前获准调用下完成重构建（bundle 583,142 字节），合成/地形/Chromium 21/21、WebKit 10/10 与 JavaScript 语法检查通过，覆盖实体遮挡、真实触摸及满村容量。写实迭代未升级/新增依赖、未重新安装包、未修改锁或许可。上述结果不等于视觉确认、真机帧率或跨平台构建验收。不把旧生成物作为当前源码证据。

许可核验不等于漏洞扫描或供应链安全保证。依赖变更必须重新核来源、完整性、许可与 scripts；不能仅更新版本表。
