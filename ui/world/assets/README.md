# Local terrain textures

Downloaded 2026-10-13. Runtime uses embedded bytes only; no CDN or API calls.

| Set | Asset source | Authors | Included channels |
| --- | --- | --- | --- |
| Rock | [cliff_side](https://polyhaven.com/a/cliff_side) | James Ray Cock, Jenelle van Heerden, Dario Barresi | 1k RGB diffuse, OpenGL Y+ normal |
| Ground | [rocky_terrain](https://polyhaven.com/a/rocky_terrain) | Amal Kumar | 1k RGB diffuse, OpenGL Y+ normal |

Downloaded asset license: **CC0 1.0 Universal** under [Poly Haven's asset license](https://polyhaven.com/license). This does not cover website branding, preview renders or website copy; none are included here. [CC0 legal text](https://creativecommons.org/publicdomain/zero/1.0/legalcode).

Public API terms: <https://github.com/Poly-Haven/Public-API/blob/master/ToS.md>. Retrieval used a named `tokens-world-prototype/1.0` User-Agent, serial requests: 6 API metadata requests and 4 file downloads. Total image download: **3,831,966 bytes**, below the approved 4 MiB limit. No roughness or displacement downloads: roughness remains a procedural fallback, not a claimed scanned channel.

`manifest.json` records per-channel URLs, dimensions, exact bytes, MD5 and SHA-256. `tests/test_world_terrain.py` verifies file hashes and embedded bytes. Diffuse uses sRGB; normal maps use linear color space. Original image files remain reproducible sources.

Regenerate embedded ES module from repository root:

```sh
python3 ui/world/assets/generate.py
```

`textures.js` is a generated source asset committed alongside originals for reproducible offline bundling. It is not fetched or decoded on each model-filter change. Browser decoding is cancellable; failed upgrades keep procedural materials.
