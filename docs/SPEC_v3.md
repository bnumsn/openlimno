# OpenLimno SPEC — v3.0 (cut from v2.14.1)

| 字段 | 内容 |
|---|---|
| 版本 | 3.0.0 |
| 状态 | **Cut from v2.14.1**; charter-tagged "强制安全 + 完成 v3.x 已知阻塞项 (R11-4 路径沙箱、R13-4 matplotlib 线程安全)" |
| 起草日期 | 2026-05-19 |
| 前一版本 | `SPEC.md` (v0.5) + `docs/SPEC_3x_research_route.md` (route doc) — 此 SPEC 把 route doc 中真正落地到 v3.0 的项目分离出来 |
| 适用范围 | v3.0 = "v2.x 加固完成版"。**非**新功能,只是把 v2.x 累积的 v3.x deferral 项收口 |

> v3.0 与 v2.x 的关系:v3.0 **不是**重新设计,而是把 v2.x 累积的"等 v3.0 再做"的兼容性破坏项一次性集中执行,从此 v2.x 维护线终结,后续在 v3.x 上演进。
>
> 命令行 user-facing 行为不变;**真正破坏**只在两处:
> 1. `Case._resolve_safe` 默认严格(详见下文 §1)。
> 2. `Case.run(slope, manning_n)` 默认 sentinel `None`(已在 v2.14.1 中完成,v3.0 无新动作)。

---

## 1. 默认严格路径沙箱 (R11-4 收尾,v3.0 头号破坏)

### Pre-v3.0 语义
- `case.allowed_data_roots` 未设置 → permissive,任意 URI 都解析(v2.12.0 起对越界 URI 触发 `DeprecationWarning`)
- `case.allowed_data_roots: []` → strict,case 目录之内才允许
- `case.allowed_data_roots: [paths]` → 允许列出的目录 + case 目录

### v3.0 语义
- `case.allowed_data_roots` 未设置 **=== `allowed_data_roots: []`** → strict
- `case.allowed_data_roots: [paths]` → 允许列出的目录 + case 目录(不变)
- `_resolve_safe(..., allow_outside_case=True)` 仍然存在,作为引擎级 escape hatch

### 迁移路径
所有 v2.x 用户的 case.yaml 中:
- 路径全部在 case 目录之内(如 `./data/...`):**无需任何修改**。
- 路径有越出 case 目录(如 `../../shared/data.parquet`):必须在 `case.allowed_data_roots` 中显式列出可信目录。

仓库内 4 个示例 fixtures 的迁移已在 v3.0.0 ship 中完成:
- `examples/lemhi/case.yaml` → 加 `allowed_data_roots: [../../data]`
- `examples/composite_hsi/case.yaml` → 加 `allowed_data_roots: [../../data, ./data]`
- `examples/phabsim_replication/case.yaml` → 无需(全部 `./data/`)
- `tests/integration/fixtures/lemhi-tiny/case.yaml` → 无需(全部 `data/`)

### 错误信息
解析失败时 `ValueError` 信息会显式指出 "Pre-v3.0 this would have been permitted" 以及如何回到旧行为(添加 `allowed_data_roots`),所以按旧文档操作的用户能立即找到迁移路径。

---

## 2. matplotlib `pyplot` 线程安全 (R13-4)

`studio/headless.py` 的 `plot_wua_q` 在 import `matplotlib.pyplot` 之前显式 `matplotlib.use("Agg", force=False)`。

- **Why**: Studio 的 `_RunCaseWorker.run` 在 `QThread` 中调用 `run_case_with_plots(plot=True)`,该函数最终调到 `plot_wua_q` → `plt.subplots()`. `pyplot` 是全局状态机,在默认 Tk/Cocoa 后端下非主线程调用会随机崩或卡 GUI;Agg 是纯软件后端,线程安全,产生相同 PNG。
- **`force=False`**: 不覆盖用户已经选择的后端(notebook / Jupyter 场景)。
- **`if 'matplotlib.pyplot' not in sys.modules`**: 仅在首次 import 之前生效(matplotlib 的设计限制)。

---

## 3. 路径解析审计 (v3.0 Audit Pass)

把 v2.x 累积的"未经过 `_resolve_safe` 的 `_resolve` 调用点"全部 route through 沙箱。**完成度**:

| 调用点 | Ship | 状态 |
|---|---|---|
| `_resolve_mesh_uri` | v2.11.1 R12-4 | ✅ |
| `data.cross_section` | v2.12.0 | ✅ |
| `data.hsi_curve` | v2.12.0 | ✅ |
| 监管数据 `data.rating_curve` | v2.12.0 | ✅ |
| `studyplan_path` | v2.14.1 | ✅ |
| 漂流卵 `params` | v2.14.1 | ✅ |
| 漂流卵 forcing CSV | v2.14.1 | ✅ |
| CLI `case._resolve(cross_section)` | v3.0.0 | ✅ |
| CLI 通用 data path | v3.0.0 | ✅ |
| `workflows/calibrate.py` PEST++ workspace | v3.0.0 | ✅ |
| `output.dir` 写入目标 | **v3.x 后续** | ⏸ 跳过 |

**`output.dir` 故意跳过**:写入目标 vs 读取源语义不同。Studio 合法可能写到 `/tmp/scratch/`;`_resolve_safe` 的"在沙箱内才允许"对写目标不适用。v3.x 后续考虑独立的 `_resolve_write_target` 语义。

10/11 sites 沙箱化。剩余 1 项明确推 v3.x。

---

## 4. 暂不在 v3.0 范围 (从 v3.x route 推到 v3.1+)

- **`ruamel.yaml` 全面替换 `yaml.safe_load/dump`** (R13-3):case.yaml 是研究员手编,`safe_dump` 会破坏注释和键顺序。v2.14.1 仅 PEST++ 写回点 atomic,没切 ruamel。v3.1 工作:新增 `ruamel.yaml` 运行依赖,改 5+ 个 YAML 读写点。
- **边界条件横向流入 / 点源** (R11-23):需先在 builtin-1d / SCHISM 求解器一侧落地,schema 才有意义。求解器扩展未启动 → 推 v3.1。
- **R9-3 高纬度 (>±60°) 投影 CRS 缓冲**:依赖 `pyproj.Geod` 改 buffered 几何路径;无用户投诉 → 推 v3.1。
- **R11-2 solver-level boundaries-missing 警告**:依赖求解器内部添加 warnings 通道;推 v3.1。
- **R11-18 TIFF fixture 生成器**:纯防御性,不解决任何真问题;推 v3.x。
- **R13-9 / R13-11 / R13-12 / R13-14 / R13-16 / R13-17**:细枝末节 + 信任面 + 性能 — 推 v3.x audit pass。

---

## 5. v3.0 → v3.x 的 stability promise

- **v3.x 仍是 additive-only**:v3.0 是破坏性发布,但发布之后 v3.x 路径(v3.0.1, v3.1, ...)回到 v2.x 的"只加不破"惯例。
- **下一次重大破坏 = v4.0**:触发条件类似 v3.0(SPEC §3 cut criteria),目前没有任何 v4.0 触发器。

---

## 6. v3.0 验证

- `ruff check` 0 findings
- `mypy --strict` core (59) + GUI/QGIS (9) clean
- 13 轮 codex+gemini+claude review chain 累积:92 findings → 84 closed → 8 deferred(全部归 v3.1+)
- 测试套件:>85 测试在 sandbox + PEST++ + plugin-smoke + schema + composite_hsi + version-consistency 上全绿
- 示例 fixtures (4 个) 全部在 v3.0 严格沙箱下通过 `validate_case` + `Case.run` (其中需要 fixture 数据的 composite_hsi 整体端到端)
