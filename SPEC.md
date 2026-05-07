# OpenLimno 技术规格书 (SPEC) — v0.5

| 字段 | 内容 |
|---|---|
| 版本 | 0.5.0 (frozen) |
| 状态 | **Approved-for-M0 (无条件)** — 三轮领域验收 12/12 PASS;SPEC 进入冻结期, 后续仅接受真实流域案例驱动的字段补丁 |
| 起草日期 | 2026-05-07 |
| 前一版本 | `SPEC-v0.1-archive.md` in repository root (v0.1 → v0.2 → v0.3 → v0.4 → v0.5) |
| 适用范围 | 1.0 = PHABSIM/IFIM 现代化替代 + SCHISM 包装 2D 栖息地 + 桌面工作流 |
| 许可 | Apache-2.0 (代码) / CC-BY-4.0 (规格、数据、文档) |

> **v0.5 与 v0.4 的差异 (领域验收 13 条背书条件 + 内部一致性修复)**:
> 1. **§4.2.6** 漂流性卵评估的水温场来源声明 (1.0 由用户 CSV 提供, 不内嵌 thermal)
> 2. **§4.2.2.3 (新)** 遗留 PHABSIM/IFG 数据导入默认填值与降级策略 (避免"装上跑不起来")
> 3. **§13.7** P1 显式声明为"1.x 首批, 不抢 1.0 资源"; §0.3 + §10 + §13.7 三处口径对齐
> 4. **§3.1.3 + §4.4.1** TUF 库默认 vs case 覆盖的优先级合并规则
> 5. **§4.2.2 + §3.1.4.1** quality_grade 字段去重 (互相引用同源定义)
> 6. **§4.2.4.2** SL-712 输出补"四件套" (分月最小 + 适宜 + 多年平均% + 90% 保证率)
> 7. **§14.3 (新)** 邀请监管/FERC/WFD 专家 M2 节点对口审查
> 8. **附录 C** 补中文文献骨架 (易伯鲁 / 曹文宣 / 段中华 / SL 609 / SL/Z 712)
>
> **v0.4 已纳入的差异 (8 项领域盲点修复)** 见附录 B。

---

## 0. 引言

### 0.1 目的
定义一个**有限范围、可在 18 个月内交付、能持续维护**的开源水生态建模平台第 1 版规格。1.0 目标是替代 PHABSIM 的桌面工作流并为后续扩展奠定数据与接口基础。

### 0.2 1.0 设计目标 (优先级有序)

1. **能装上、跑通、出图** — 桌面 (Win/Mac/Linux), pixi/conda 一键装, 自带可复现示例
2. **数据可信** — 输入/输出全部开放格式, 自带数据来源与质量元数据; **物理 + 生物**双闭环
3. **结果可信** — 与 PHABSIM 标准例表级回归 ≤ 1e-3
4. **可演化** — 数据模型 + 求解器接口稳定, 后续加 2D/不确定性/GPU 等扩展不破 API
5. **能被 ≥3 人持续维护** — 治理、release、文档责任在 M0 就到位
6. **支持 IFIM 五步法**, 不只是计算第三步 (v0.4 新增) — 1.0 提供研究设计 (studyplan)、目标变量选择、栖息地时序产品 (Habitat Time Series / Duration Curve / Frequency Analysis)、监管语言导出 (SL/Z 712 / FERC / WFD)

### 0.3 1.0 非目标 (重点!)

下列能力**明确不在 1.0**, 防止范围蔓延:

- **OpenLimno 自有 2D/3D 水动力求解器** (1.0 不提供自研 2D/3D 数值方法)
  - **澄清**: 1.0 通过 SCHISM 包装可达成 2D 栖息地评估工作流, 但 2D 求解能力归属 SCHISM, 不归 OpenLimno; OpenLimno 只做前后处理与栖息地后端
- 自研 GPU 求解器
- 不确定性量化 / 集合预报 / 数据同化
- ML 代理模型 / 神经算子
- 个体行为模型 (IBM/ABM) / 种群动力学
- 水温 / 水质 / 泥沙 / 河床演变 (后期)
- Web GUI / 云原生 / 多租户 / REST 服务
- 嵌入式实时调度
- 多求解器 BMI 互换 (1.0 只深度集成 SCHISM 一个)

详见 [§13 研究路线]。

### 0.4 术语

| 缩写 | 全称 | 注 |
|---|---|---|
| WEDM | Water Ecology Data Model | 本规格定义的数据模型 |
| HSI | Habitat Suitability Index | 栖息地适宜度指数 |
| WUA | Weighted Usable Area | 加权可用面积 |
| IFIM | Instream Flow Incremental Methodology | 河道内流量增量法 |
| UGRID | Unstructured Grid Conventions | NetCDF 非结构网格约定 |
| CF | Climate and Forecast Conventions | NetCDF 元数据约定 |
| SCHISM | Semi-implicit Cross-scale Hydroscience Integrated System Model | 深度集成的开源水动力引擎 |
| HMU | Hydromorphological Mesohabitat Unit | 中尺度栖息地单元 (Parasiewicz 2001), 如 riffle/run/pool/glide/cascade/step |
| RSF | Resource Selection Function | 资源选择函数 (Manly 2002), HSI 的现代统计学替代 |
| η_A | Attraction Efficiency | 过鱼吸引效率 (鱼到达入口概率) |
| η_P | Passage Efficiency | 过鱼通过效率 (进入入口后通过概率); 整体 η = η_A × η_P |
| RST | Rotary Screw Trap | 旋转鼓式陷阱, 监测下行迁徙鱼 |
| eDNA | environmental DNA | 环境 DNA 采样 |
| TUF | Time Use Factor | 时段使用因子 (IFIM 加权), 生命阶段-时段映射 |

---

## 1. 设计原则 (修订)

### P1 范围纪律
1.0 范围一旦冻结, 任何扩展走第 13 章。新功能默认放第 13 章, 而非 1.0。

### P2 单引擎深度集成
1.0 水动力后端**只**是 SCHISM, 不做"求解器超市"。OpenLimno 提供:
- SCHISM 输入文件生成器 (从 WEDM)
- SCHISM 结果读取器 (回写 WEDM)
- 1D Saint-Venant 内置参考实现 (PHABSIM 等价)

不实现"换一个 backend 物理结果一致"这种工程上做不到的承诺。

### P3 全开放数据
持久化输出: NetCDF-4 / Zarr v3 / Parquet / GeoParquet。配置: YAML + JSON-Schema。
不引入私有二进制格式, 不引入未声明字段。

### P4 桌面优先
1.0 部署形态**只一种**: 单机桌面 (Win/Mac/Linux), pixi/conda 装。
HPC: 仅承诺"输出文件格式可在 HPC 上读"; 不提供 Slurm 模板/MPI 适配。
云、嵌入式、Web GUI、Tauri: 不进 1.0。

### P5 工程可诊断 > 论文级精度
验证套件每个 case 必须含: 输入数据许可、网格版本、边界条件清单、质量守恒指标、人工验收图。
不写"100M 元素 1 分钟"这种绝对性能目标; 写"在参考机器上的实测基准 + 复现脚本"。

### P6 治理先行
M0 必须有: ≥3 named maintainer、release 节奏、bus factor 应对、deprecation policy、文档责任人。没有这些, 不做 M1。

### P7 第一公里优先
"读 ADCP/CSV/横断面表 → 出合格网格"是 M1 必交付项, 不是附属工具。
PHABSIM 之所以普及, 一半是因为它解决了"现实测量数据怎么进系统"。1.0 必须做对这一步。

---

## 2. 系统架构 (简化)

### 2.1 一张图说清

```
┌─────────────────────────────────────────────────┐
│  CLI  │  QGIS Plugin  │  Jupyter Notebook       │  ← L4 接入
├─────────────────────────────────────────────────┤
│  workflows: calibrate, regression, scenarios     │  ← L3 编排 (Snakemake)
├─────────────────────────────────────────────────┤
│  habitat (HSI/WUA)  │  passage (1D 涵洞 v1)      │  ← L2 生态
├─────────────────────────────────────────────────┤
│  hydro-1d (内置 SaintVenant)                     │  ← L1 水动力
│  hydro-schism (生成输入 + 读结果, 不内嵌求解)      │
├─────────────────────────────────────────────────┤
│  preprocess (ADCP/横断面/LiDAR → UGRID)           │  ← L0.5 第一公里
│  wedm (数据模型 + JSON-Schema 校验 + provenance)   │  ← L0 内核
└─────────────────────────────────────────────────┘
```

### 2.2 进程模型
**单进程**, 全部 Python 调用本地库或本地 SCHISM 可执行文件。
无 gRPC、无 Arrow Flight、无 K8s、无 MPI。

### 2.3 与 SCHISM 的边界

```
[OpenLimno Python]
     │ 1. 把 WEDM mesh + 边界条件 → SCHISM 输入文件 (hgrid.gr3, vgrid.in, param.nml, ...)
     ▼
[SCHISM 可执行]   ← 用户自行编译/conda-forge 安装, 通过 subprocess 调用
     │ 2. 跑稳态/非稳态
     ▼
[SCHISM 输出 schout_*.nc]
     │ 3. 读 + 转 WEDM (UGRID + CF)
     ▼
[OpenLimno Python] → 栖息地 / 通过性 / 出图
```

**1.0 不做的**: 不嵌入 SCHISM 二进制, 不做 BMI 实时步进耦合, 不在 SCHISM 内插值。
**1.0 做的**: 前后处理 + 一个守恒插值层 (用 ESMF/SCRIP 现有库)。

---

## 3. 核心契约

### 3.1 WEDM — 水生态通用数据模型 (扩展版)

> **v0.1 → v0.2 关键变化**: 从"网格 + 物种表"扩展为完整的项目数据闭环。新增 6 张领域数据表, 这是 Codex 评审最强烈的要求。

#### 3.1.1 几何/网格层
- NetCDF-4 + UGRID-1.0
- 1D: 横断面链 + 河道线
- 2D: 三角/四边形非结构 (UGRID 标准)
- 1.0 不支持: 3D σ/z 混合层 (放 SCHISM 自己处理, 只读不存)
- **HMU 中尺度图层** (v0.4 新增): 与网格平行, 一组 polygon + 类型枚举
  - 类型: riffle / run / pool / glide / cascade / step / backwater (基于 Parasiewicz 2001 MesoHABSIM)
  - 字段: hmu_id, polygon, type, mean_depth, mean_velocity, dominant_substrate
  - 可由用户手工标定, 也可由水力结果自动分类 (§4.2.7)
- **时变网格** (v0.4 新增, 应对河床演变): mesh schema 保留 `time` 维度可选; 1.0 不实现演化, 但允许"前/后两期手工网格"参与同一 case
  - 用例: 建坝前后地形变化下的 WUA 敏感性分析
  - 不在 1.0 实现: 自动河床演变 (→ §13.7, P1, M5-M6)

#### 3.1.2 时变场层
- 本地: NetCDF-4
- 1.0 不引入 Zarr (放到第 13 章), 简化依赖
- CF 标准名 + units 强制
- 必填字段: `time`, `water_depth`, `velocity_x`, `velocity_y`

#### 3.1.3 物种与栖息地参数库 (v0.4 大幅扩展)

**核心表 (Parquet)**:

- `species` — taxon_id, 学名, 中文名, IUCN 状态, 流域分布, 是否洄游 (anadromous/catadromous/potamodromous/none), 是否产漂流性卵 (drifting_egg)
- `life_stage` — species, stage (egg/larvae/fry/juvenile/adult/spawner), time_window, **habitat_zone** (产卵场/育幼场/索饵场/越冬场/洄游通道, v0.4 新增), **TUF_default** (库默认 Time Use Factor, 见 §4.4.1.1 优先级规则)
- `swimming_performance` — species, stage, temp_C, burst/prolonged/sustained
- `hsi_curve` — species, stage, variable, x, suitability, **category** (I/II/III, Bovee 1986; I=专家意见, II=利用频率, III=偏好), **geographic_origin** (流域代码或坐标), **transferability_score** ∈ [0,1] + 文本说明, **independence_tested** (是否做过变量独立性检验, 默认 false), **citation_doi**
  - 1.0 默认表达: 分段线性
  - 加载时若 transferability_score < 0.5 且 case 流域 != geographic_origin 流域, 必须发出 WARNING
  - 配置层若使用 composite=geometric_mean 或 arithmetic_mean, 用户必须显式声明 `acknowledge_independence: true` (类似 SQL UNSAFE 操作)
- `passage_criteria` — jump_height, leap_speed, fatigue_curve_id
- **`migration_corridor`** (v0.4 新增) — species, from_stage, to_stage, distance_km, timing (date_window), cue_variable (温度/流量/光周期), barrier_geom (可选)
- **`drifting_egg_params`** (v0.4 新增) — species, drift_distance_km_min/max, hatch_temp_days_curve, mortality_velocity_threshold (用于产漂流性卵 1D 拉格朗日评估, §4.2.6)

#### 3.1.4 ⭐ 项目数据闭环表 (v0.2 引入物理表, v0.4 补全生物表)

> v0.2 解决"物理数据闭环", v0.4 解决"生物数据闭环"。两者缺一不可, 否则 §9 的校准只能闭水力的环, 不能闭"水力 → 栖息地 → 鱼类响应"全链条的环。

##### 3.1.4.1 物理观测表

| 表 | 说明 | 关键字段 |
|---|---|---|
| `survey_campaign` | 一次现场调查 | id, date, agency, equipment, weather, license, doi |
| `observations` | 单点/单线观测 | campaign_id, time, geom (Point/Line), variable, value, units, sensor, qc_flag |
| `cross_section` | 横断面测量 | campaign_id, station_m, geom (Line), points (depth, elev, sub, cov) |
| `adcp_transect` | ADCP 横线 | campaign_id, geom, ensemble[time, depth, u, v, w, backscatter] |
| `rating_curve` | 水位-流量 | gauge_id, points (h, Q, sigma_Q), valid_range, source_doi |
| `hydraulic_controls` | 控制工程 | id, type (weir/culvert/dam), geom, geometry_params, operation_rules |
| `hsi_evidence` | HSI 曲线证据来源 | curve_id, paper_doi, n_observations, geographic_region, quality_grade (A/B/C) |

##### 3.1.4.2 生物观测表 (v0.4 新增, 补领域评审盲点 4)

| 表 | 说明 | 关键字段 |
|---|---|---|
| `fish_sampling` | 鱼类捕捞 | campaign_id, geom, method (electrofishing/snorkel/seine/gill_net/fyke_net/hook_line), effort_seconds_or_meters, species, count, length_mm, weight_g, age, sex, qc_flag |
| `redd_count` | 产卵巢调查 | campaign_id, geom (Point/Polygon), species, count, redd_status (active/superimposed/buried), substrate_dominant, depth_m, velocity_ms |
| `pit_tag_event` | PIT tag 标记重捕 | tag_id, species, length_mm, event_type (release/recapture/detection), location_geom, time, antenna_id |
| `rst_count` | RST 下行迁徙计数 | campaign_id, station_geom, time_start/end, species, life_stage, count, water_temp_C, discharge_m3s |
| `edna_sample` | eDNA 采样 | campaign_id, geom, time, water_volume_L, target_species, qPCR_copies_per_L, lab_method_doi |
| `macroinvertebrate_sample` | 大型底栖无脊椎动物 | campaign_id, geom, method (Surber/kicknet/Hess), taxa, count, biomass_g, EPT_richness, BMWP_score |

##### 3.1.4.3 主外键约束

- `*.campaign_id → survey_campaign.id`
- `hsi_curve.id` ← `hsi_evidence.curve_id` (1:N)
- `pit_tag_event.tag_id` 自然主键 (重复合法, 含 release + N 次 recapture)
- 所有几何字段 EPSG 必填于列元数据
- 所有时间字段含时区

##### 3.1.4.4 原则

- 每一个数据点都能追溯到 `survey_campaign` 或 `paper_doi`, 不允许"凭空"的数据进入 WEDM
- M0 出 JSON-Schema 完整定义, 不能停在表格描述
- 1 个真实流域样例数据 (Lemhi River 优先, 因 USGS PIT/RST/HSI 数据公开) 是 M0 退出条件

#### 3.1.5 配置层 (示例, 简化)

```yaml
openlimno: 0.2
case:
  name: lemhi_phabsim_replication
  crs: EPSG:32612
mesh:
  uri: file://lemhi.ugrid.nc
hydrodynamics:
  backend: builtin-1d              # 或 schism
  builtin_1d:
    scheme: preissmann
    boundaries:
      upstream:  { type: discharge, series: file://Q_2024.csv }
      downstream:{ type: rating-curve, ref: rating_curves/rc-lemhi.parquet }
habitat:
  species: [oncorhynchus_mykiss]
  stages:  [spawning, fry]
  metric:  wua-q                   # 或 wua-time
  composite: geometric_mean
output:
  dir: ./out/lemhi_2024/
  formats: [netcdf, csv]
provenance:
  emit: true
```

**配置删减**: v0.1 的 ensemble/perturb/cmip6 等不出现在 1.0 配置 schema 里。

### 3.2 求解器接口 (简化)

#### 3.2.1 1.0 不用 BMI

理由 (Codex 评审): BMI 是为多求解器互换设计的, 但 1.0 只接 SCHISM 一个 + 内置 1D, 上 BMI 是无用复杂度。

**1.0 接口**: 两个具体的 Python 类:

```python
class HydroSolver(Protocol):
    def prepare(self, case: Case) -> Path: ...
    def run(self, work_dir: Path) -> RunResult: ...
    def read_results(self, work_dir: Path) -> WEDMDataset: ...

class Builtin1D(HydroSolver): ...      # OpenLimno 内置
class SCHISMAdapter(HydroSolver): ...  # 调外部 SCHISM 可执行
```

#### 3.2.2 BMI 留给研究路线
未来 (§13.2) 加第 3+ 个 backend 时再引入 BMI。

### 3.3 工作流

- **唯一**: Snakemake (社区接受度最高, Python 友好)
- **必备工作流** (1.0):
  - `calibrate`: PEST++ 参数校准 (基础)
  - `regression-test`: 自动跑全部基准
- **不进 1.0**: uq-mc, uq-pce, da-enkf, scenario-cmip6 (移到 §13)

---

## 4. 模块规格 (1.0 仅核心)

### 4.0 数据预处理 — `openlimno.preprocess` ⭐⭐ (新增, Gemini 评审要求)

**这是 v0.2 新加的 L0.5 层, 是 1.0 必交付而非附属。**

#### 4.0.1 输入支持

> **v0.3 修订 (Codex 二轮评审)**: M1 仅做加粗"核心三件套", 其余 (原生二进制 / HEC-RAS / River2D 迁移) 移到 M3 之后。.g0X / .cdg 是逆向解析, 永远是 best-effort, 不构成 1.0 契约。

| 数据源 | 格式 | 工具 | 阶段 |
|---|---|---|---|
| **横断面表 (M1)** | **CSV / Excel** | `read_cross_sections()` | **M1 必交付** |
| **ADCP transect (M1)** | **USGS QRev CSV** | `read_adcp()` | **M1 必交付** |
| **DEM (M1)** | **GeoTIFF** | `read_dem()` | **M1 必交付** |
| 流量站 | USGS RDB / 中国水文年鉴 CSV | `read_gauge()` | M2 |
| 底质样方 | GeoPackage / Shapefile | `read_substrate()` | M2 |
| ADCP 原生二进制 | TRDI / SonTek | `read_adcp_native()` | M3 |
| PHABSIM IFG4 | .IFG | `import_phabsim()` | M3 |
| 现有 HEC-RAS 几何 | .g0X (best-effort, 非契约) | `import_hecras_geometry()` | M4 |
| 现有 River2D | .cdg / .bed (best-effort, 非契约) | `import_river2d()` | M4 |

#### 4.0.2 处理管线
1. **标准化**: 投影/单位/缺失值
2. **质量控制**: 自动 QC flag, 用户可手动覆盖
3. **网格剖分**: 调用 GMSH / Triangle, 提供"按横断面引导"的特殊算法
4. **插值**: 线性/克里金/IDW, 都带 QC 报告

#### 4.0.3 输出
统一为 WEDM 格式 (UGRID + 项目数据闭环表)。

### 4.1 水动力 — `openlimno.hydrodynamics`

#### 4.1.1 1D 内置 (PHABSIM 等价)

控制方程:
```
∂A/∂t + ∂Q/∂x = q_lat
∂Q/∂t + ∂(Q²/A)/∂x + gA·∂h/∂x = -gA·S_f + q_lat·v_lat
```
- 离散: Preissmann 4 点隐式 (默认)
- 摩阻: Manning 逐段
- 内嵌局部模型: 涵洞 (HY-8 库)、堰、桥
- **PHABSIM 表级回归** (v0.3 修订, 不再说 "bit-level"): 与 PHABSIM 同输入下 WSP 与 WUA 表的逐行最大偏差 ≤ 1e-3 (绝对值或相对值, 取较宽); HSI 实现细节差异允许在容差内吸收

#### 4.1.2 SCHISM 包装

仅做前后处理:
- 写 SCHISM 输入文件 (hgrid.gr3, vgrid.in, param.nml, bctides.in, ...)
- 启动 SCHISM 子进程 (subprocess + log 解析)
- 读 SCHISM 输出 (schout_*.nc → WEDM)

**不在 1.0**: 编译 SCHISM、嵌入 SCHISM、改 SCHISM 数值。

#### 4.1.3 验证套件 (工程可诊断标准)

每个 benchmark 必交付:

| 项目 | 内容 |
|---|---|
| 输入数据 | 许可、来源 DOI、版本号 |
| 网格 | 版本、单元数、最差单元质量、生成方法 |
| 边界条件 | 上下游、闭口、湿干、构筑物 |
| 质量守恒 | 模拟期间总质量误差 (绝对 + 相对) |
| 水面线 | 与参考解逐站点对比图 |
| 干湿边界 | 湿干面积时序图 |
| 速度剖面 | 关键断面剖面图 |
| 失败容忍 | RMSE/IoU/相对峰值阈值 (写明依据) |
| 人工验收图 | maintainer 签字保存的 PNG |

**M1 必通过** (v0.3 修订: 国内案例不再是硬门槛):
- MMS 1D (二阶网格收敛)
- Toro 1D Riemann (L1 < 0.5%)
- PHABSIM Bovee 1997 标准例 (WUA 表级一致, ≤ 1e-3)
- **USGS Lemhi River 公开数据集** (硬门槛, 国际可复现)
- 国内真实流域 (软推荐, 视合作进度而定; M3-M5 任意时间点完成皆可)

### 4.2 栖息地评估 — `openlimno.habitat` ⭐⭐⭐

**OpenLimno 1.0 的核心差异化模块。v0.4 大幅扩展, 补领域评审盲点 1/2/3/5/7。**

#### 4.2.1 1.0 评估方法 (PHABSIM 等价 + 现代化扩展)

| 方法 | 1.0? | 说明 |
|---|---|---|
| HSI 单变量 (分段线性) | ✓ | PHABSIM 兼容 |
| HSI 复合 (geom/arith/min/weighted_geom) | ✓ | PHABSIM 兼容; 但用 geom/arith 时强制 acknowledge_independence |
| WUA-Q 曲线 | ✓ | PHABSIM 核心产品 |
| WUA-time | ✓ | 超 PHABSIM, 给时序水力数据 |
| 持续栖息地 (%time HSI > θ) | ✓ | 现代生态流量指标 |
| **Habitat Duration Curve** (HDC) | ✓ (v0.4) | Milhous 1990, IFIM 标准产品 |
| **Habitat Frequency Analysis** (HFA) | ✓ (v0.4) | 阈值穿越频次, 生态流量推荐核心 |
| **Habitat Time Series** (HTS) | ✓ (v0.4) | 与 WUA-time 一对一, 但带时段加权 (TUF) |
| **多尺度聚合** (cell / HMU / reach) | ✓ (v0.4) | Frissell 1986, Parasiewicz 2001 |
| Tennant / Texas / Wetted-perimeter | ✓ | 基线对比 |
| **产漂流性卵评估** (1D Lagrangian) | ✓ (v0.4) | 中国四大家鱼/铜鱼必备, §4.2.6 |
| Fuzzy HSI | ✗ → §13.14 | |
| Bayesian HSI | ✗ → §13.14 | |
| RSF / Occupancy (现代统计学) | ✗ → §13.17 (v0.4 新增占位) | |
| 漂移-觅食 NREI | ✗ → §13.15 | |
| 多目标 e-flow Pareto | ✗ → §13.16 | |

#### 4.2.2 HSI 曲线 (1.0, v0.4 严格化)

> **v0.4 关键变化**: 回应领域评审盲点 2 (HSI 科学性争议)。
> Mathur 1985, Williams 1996, Lancaster & Downes 2010 三十年来对 HSI 的批评要求平台**显式承担**而非隐藏。

仅"分段线性"一种内部表示, 与 PHABSIM 完全兼容。其他表达 (Spline/Fuzzy/Bayesian) 在 §13.14。

```python
@dataclass
class HSICurve:
    species: str
    life_stage: str
    variable: Literal["depth", "velocity", "substrate", "cover", "temperature"]
    points: list[tuple[float, float]]                       # (x, suitability) 分段线性
    category: Literal["I", "II", "III"]                     # ⭐ Bovee 1986 强制分级
    geographic_origin: str                                  # ⭐ 流域代码 / 国家
    transferability_score: float                            # ⭐ ∈ [0,1] + 文本说明
    independence_tested: bool = False                       # ⭐ 默认 false, 置 true 须给检验报告
    evidence: list[Doi]
    quality_grade: Literal["A", "B", "C"]                   # 见 §4.2.2.1; 与 §3.1.4.1 hsi_evidence.quality_grade 同源, 加载时用 §3.1.4.1 表的值覆盖此处, 若 hsi_evidence 无对应记录则使用此处
```

> **v0.5 字段去重声明**: HSICurve.quality_grade 与 §3.1.4.1 hsi_evidence.quality_grade 是**同一概念**。HSICurve 上的字段是冗余便利字段; hsi_evidence 表是权威来源 (含完整文献证据链)。加载时若两者冲突, 以 hsi_evidence 表为准并发 WARN。

##### 4.2.2.1 quality_grade 评级标准 (v0.4 新增)

| 等级 | 准入条件 |
|---|---|
| A | Category III 偏好观测, n ≥ 200, 同流域且 transferability ≥ 0.8, 通过独立性检验, 同行评审论文 |
| B | Category II/III, n ≥ 50, 邻近流域 transferability ≥ 0.5, 内部报告或官方手册 |
| C | Category I 专家意见 / Category II 利用频率, 缺独立性检验, 跨流域使用 |

加载时自动检查; 用 C 级 HSI 跑出的 WUA 必须在输出图上加水印 "Category I/C-grade HSI - tentative"。

##### 4.2.2.2 独立性假设的硬声明 (v0.4 新增)

```yaml
habitat:
  composite: geometric_mean        # 或 arithmetic_mean / min / weighted_geometric
  acknowledge_independence: true   # ⭐ geom/arith 时必填
  acknowledge_independence_reason: |
    HSI variables are assumed independent for this case based on Bovee 1997
    Section 5.3, with awareness of Lancaster & Downes 2010 criticism.
    Independence justified by limited spatial co-variation in target reach.
```

不带 acknowledge_independence 直接配 geom/arith → 启动失败。这是教育用户认知的硬约束。

##### 4.2.2.3 遗留数据导入默认填值与降级策略 (v0.5 新增)

> 旧 PHABSIM .IFG / RHABSIM 数据库 / USFWS HSI Blue Book 文件**不带** category / transferability_score / geographic_origin / independence_tested 这些 v0.4 新引入的字段。如果硬性要求, 所有遗留数据"装上跑不起来", 是反向阻碍迁移。

**导入时的默认填值与处理**:

| 字段 | 遗留数据缺失时的默认 | 行为 |
|---|---|---|
| `category` | `"III"` (假定原作者收的是 Category III 偏好观测,这是最常见情况) | 仅 WARN, 不阻断 |
| `geographic_origin` | `"unknown"` | 仅 WARN |
| `transferability_score` | `0.5` (中性) | 仅 WARN |
| `independence_tested` | `false` | 维持原行为, 配 geom/arith 时仍要求 acknowledge_independence |
| `quality_grade` | `"C"` (最低评级) | 跑出的 WUA 自动加水印 "C-grade HSI - tentative, missing v0.4 metadata"; 不阻断 |
| `evidence` | 文件名 / 文件路径 | 仅 WARN |

**导入命令明示降级**:
```bash
openlimno preprocess import-phabsim --in legacy.IFG --out hsi_curve.parquet --grade-default C --warn-only
# stderr 输出:
# WARN  legacy.IFG: 142 HSI curves imported with v0.4 default metadata.
# WARN  Quality auto-set to "C". Output WUA will be watermarked.
# WARN  Run 'openlimno hsi upgrade' to add metadata interactively.
```

**升级路径 (M3+)**: `openlimno hsi upgrade` 交互式向导, 给每条曲线补 category / origin / transferability, 升级到 B 级或 A 级。

**原则**: 导入永远不阻断,只发 WARN; 跑出的结果带可视水印; 升级路径低摩擦。这避免"严格化反向赶跑用户"。

#### 4.2.3 WUA 计算 (含多尺度聚合, v0.4 扩展)

##### 4.2.3.1 cell 级 (PHABSIM 等价)

```
WUA_cell = Σ_i  A_i · CSI_i
CSI_i = f(HSI_h, HSI_v, HSI_sub, HSI_cov)
   f ∈ {geometric_mean, arithmetic_mean, min, weighted_geometric}
```

##### 4.2.3.2 HMU 级 (v0.4 新增, 中尺度)

```
WUA_HMU = Σ_{cells ∈ HMU}  A_i · CSI_i
HMU 类型聚合: WUA_riffle, WUA_pool, WUA_run, WUA_glide
```

可与 MesoHABSIM 的 HMU 级 HSC (Habitat Suitability Curve) 互操作。

##### 4.2.3.3 reach 级 (v0.4 新增, 宏观)

```
WUA_reach = Σ_{HMUs ∈ reach}  WUA_HMU
```

输出 reach × 流量 × 物种 × 生命阶段 多维 NetCDF。

实现: 纯 NumPy/xarray 向量化, 无 GPU, 无并行优化。性能目标"在参考机上百万级网格 100 步内 < 30 秒"。

#### 4.2.4 生态流量产品 (1.0, v0.4 大幅扩展)

##### 4.2.4.1 核心栖息地产品

- WUA-Q 曲线 (cell/HMU/reach 三尺度)
- WUA 时间序列 (Habitat Time Series, HTS)
- 栖息地持续曲线 (Habitat Duration Curve, HDC) — Milhous 1990 标准
- 栖息地频次分析 (Habitat Frequency Analysis, HFA) — 阈值穿越频次
- 持续栖息地指标 (%time HSI > θ)
- Tennant / Texas / Wetted-perimeter (基线)

##### 4.2.4.2 监管输出三模板 (v0.4 新增, 补盲点 8)

`openlimno.habitat.regulatory_export` 子模块, 把 NetCDF/Parquet 自动渲染为监管语言:

| 模板 | 输出格式 | 内容 |
|---|---|---|
| **CN-SL712** (v0.5 补"四件套") | CSV + PDF | **(1)** 分月最小生态流量 (m³/s, 12 个月) **(2)** 分月适宜生态流量 (m³/s, 12 个月) **(3)** 多年平均流量百分比 (%, 12 个月) **(4)** 90% 保证率分月最小流量 (m³/s, 12 个月); 符合《河湖生态流量计算规范》(SL/Z 712-2014) §5.2-5.4 |
| **US-FERC-4e** | CSV + PDF | flow regime by water year type (wet/normal/dry), 符合 FERC 4(e) conditions 模板; M2 后将增加 ESA section 7 consultation biological opinion 表 |
| **EU-WFD** | CSV + PDF | ecological status class (high/good/moderate/poor/bad), 符合 Water Framework Directive Annex V; M2 后将整合 BQE (Biological Quality Elements) 五指标 |

每个模板含: 输入 case + 计算依据 + 推荐流量 + 不确定性区间 (1.0 用经验区间, §13.3 用 UQ 替代)。

**v0.5 重要声明**: 三模板 1.0 是**模板架子**, 实际能否过审需 §14.3 邀请监管专家做 M2 节点对口审查后才能正式背书。

##### 4.2.4.3 不进 1.0
- 多目标 Pareto (§13.16)
- 漂移-觅食 (§13.15)

#### 4.2.5 HMU 自动分类 (v0.4 新增)

输入: 水力结果 (h, u 时间序列) + DEM
算法: 基于 Parasiewicz 2007 阈值 + Wadeson 1994 形态分类 (Froude 数 + 相对水深)
输出: HMU polygon 集合, 与 §3.1.1 HMU 图层一致

用户可手工标定覆盖, 自动分类作为初值。

#### 4.2.6 产漂流性卵评估 (v0.4 新增, v0.5 补水温源)

> 中国四大家鱼 (青草鲢鳙) 与铜鱼属产漂流性卵, 卵需在水柱中漂流 50-100 km 孵化。"某点 HSI"无法表达这个过程。

输入:
- 1D 水力时间序列 (流速 u(x, t))
- **水温场 T(x, t) 来源 (v0.5 关键澄清)**:
  - 1.0 不内嵌水温模拟模块 (见 §4.5 thermal → §13.5)
  - 1.0 用户必须以 forcing CSV/NetCDF 形式提供 T(x, t), 文件 schema 为 WEDM 时变场 (CF 标准名 `water_temperature`)
  - 等温情景: 用户填一个常数 + 时间-温度曲线即可
  - 与 §13.5 thermal 模块未来对接: 当 thermal 1.x 上线后, T(x, t) 自动从耦合获得, 用户配置不变
- `drifting_egg_params` 表 (参见 §3.1.3)
- 产卵点位置 (从 redd_count 表派生或用户指定)

算法:
- 1D Lagrangian 漂移: dx/dt = u(x, t)
- 孵化天数积分: 对水温做 hatch_temp_days_curve 积分
- 死亡率: 流速 < mortality_velocity_threshold 的累积时长
- 输出: 卵漂流轨迹, 孵化位置分布, 孵化前死亡率

1.0 仅 1D, 不做 2D 分散。结果接入 reach 级 WUA 作为"产卵-孵化连通性"指标。

### 4.3 过鱼通过性 — `openlimno.passage` (v0.4 严格化, 拆 attraction vs passage)

> **v0.4 关键变化** (盲点 6): FishXing 最大缺陷不是"确定性",而是把 **整体过鱼效率 η = η_A × η_P** 错误地归为单一 pass/fail。OpenLimno 1.0 必须明确只算 η_P, 把 η_A 暴露给用户输入或后期扩展。

#### 4.3.1 术语 (v0.4 新增, Castro-Santos 2005 / Bunt 2012 / Silva 2018)

| 量 | 定义 | 1.0 处理 |
|---|---|---|
| **η_A** Attraction Efficiency | 鱼到达涵洞/鱼道入口的概率 | 用户输入常数 (默认 1.0, 配置中必须显式声明) |
| **η_P** Passage Efficiency / Passage Success Rate | 进入入口后通过的概率 | 1.0 唯一计算量 |
| η = η_A × η_P | 整体过鱼效率 | 1.0 不直接输出 (避免误导), 输出 η_P + 用户提供 η_A 时旁注 η |

输出术语统一用 **"passage success rate"**, 不用 "passage efficiency" (后者在领域内特指 η_P × η_A)。

#### 4.3.2 1.0 范围

- 涵洞 1D 水力 (HY-8 兼容)
- 三段式鱼类游泳 (burst/prolonged/sustained)
- 温度依赖 (多项式)
- 确定性 η_P (FishXing pass/fail 等价)
- **概率性 η_P (Monte Carlo)**: 1.0 默认开启 (而非 v0.3 的"接口保留"); 抽样维度: 鱼长度 / 起跳能 / 温度 / 入口流速; 输出 η_P 分布 (不是单点)

#### 4.3.3 配置示例

```yaml
passage:
  culvert: { ... }
  species: chinese_sturgeon
  attraction_efficiency:           # ⭐ v0.4 必填
    value: 0.6
    source: "Site survey 2023, 60% of tagged fish approached entrance"
    note: "η_A = 1.0 假设鱼有完整动机持续尝试; 经验值 0.3-0.7 更现实"
  monte_carlo:
    n: 1000
    seed: 42
```

#### 4.3.4 移到 §13

- IBM 微观鱼轨迹 (§13.9)
- 感官场 (压力梯度 + 紊流强度) (§13.9)
- 复杂鱼道 (vertical slot, weir-and-pool, Denil) (§13.18 与 attraction 同级)
- η_A 子模型 (基于下游引诱流速场 + 鱼类感官) (§13.18)

### 4.4 研究设计 — `openlimno.studyplan` ⭐ (v0.4 新增, 补盲点 1)

> 回应领域评审: PHABSIM 在 IFIM 五步法里只是第三步, OpenLimno 不能也只做第三步。1.0 必须给前两步 (Problem Identification + Study Planning) 提供脚手架。

#### 4.4.1 1.0 范围 (轻量, 文档驱动)

不实现复杂决策算法, 只提供:

1. **物种选择决策树** (YAML checklist): 流域 → 候选鱼种 → 保护优先级 → 数据可用性 → 推荐物种 + 生命阶段
2. **生命阶段-时段映射** (TUF, Time Use Factor): 按月/旬给出每个生命阶段的时段权重, 用于 Habitat Time Series 加权聚合 (优先级规则见 §4.4.1.1)
3. **目标变量选择 checklist**: WUA / WUA-time / 持续栖息地 / HDC / HFA / 产漂流性卵 哪个适用哪种问题
4. **HSI 来源决策**: 优先现地校准 → 邻近流域 → 全国数据库 → 国际数据库; 输出 transferability_score
5. **不确定性来源 checklist** (1.0 不算 UQ, 但要列): 测量误差 / HSI 不确定性 / 校准残差 / 模型结构性 / 时段假设

##### 4.4.1.1 TUF 优先级与合并规则 (v0.5 新增)

> v0.5 澄清: TUF 在 §3.1.3 `life_stage.TUF_default` 与本节 case-level studyplan 中两处出现, 必须明确优先级。

| 来源 | 字段 | 用途 | 优先级 |
|---|---|---|---|
| 物种参数库 | `life_stage.TUF_default` | 该物种在标准时段的默认权重, 跨流域 | 低 (默认值) |
| case studyplan | `studyplan.tuf_override` | 本项目特定流域、特定研究问题的 TUF | **高 (覆盖默认)** |

合并规则:
1. 加载 case 时, 先填库默认 `TUF_default`
2. 若 `studyplan.tuf_override` 给出对应 `(species, stage)` 的覆盖值, 则覆盖
3. 输出 provenance 记录每个 `(species, stage)` 的最终 TUF 来源 (库 / case / 用户交互修改)
4. 跨 case 比较时使用统一的库默认 `TUF_default`, 避免不可比性

配置示例:
```yaml
studyplan:
  tuf_override:
    - { species: oncorhynchus_mykiss, stage: spawning, monthly: [0,0,0,1,1,0.5,0,0,0,0,0,0] }
    # 缺失 (species, stage) 自动用库 TUF_default
```

输出: 一份 `studyplan.md` + 一个 `studyplan.yaml` 进配置, 可被 case 自动加载并写入 provenance。

#### 4.4.2 工作流入口

```bash
openlimno studyplan init --interactive   # 引导式
openlimno studyplan validate study.yaml
openlimno run case.yaml --studyplan study.yaml
```

#### 4.4.3 不进 1.0

- 替代方案分析 (Alternatives Analysis, IFIM 第四步) → §13.16 多目标 Pareto
- 谈判支持工具 (IFIM 第五步) → 不做, 留给项目方

### 4.5 其他模块 (全部移走)

| 原 v0.1 模块 | v0.2-v0.4 状态 |
|---|---|
| `thermal` 水温 | → §13.5 |
| `waterquality` 水质 | → §13.6 |
| `sediment` 泥沙 + 河床演变 | → §13.7 (v0.4: P3 → **P1**, M9+ → **M5-M6**) |
| `connectivity` 连通性 | → §13.8 |
| `ibm` 个体行为 | → §13.9 |
| `population` 种群 | → §13.10 |

---

## 5. 部署形态 (单一)

### 5.1 桌面 (1.0 唯一形态)
- **打包**: pixi.toml + conda-forge 包
- **平台**: Win/Mac (Intel + Apple Silicon)/Linux
- **GUI**:
  - **CLI** 是默认接口
  - **QGIS Plugin** 是给生态学家的图形入口 (优先级高于 Tauri/Web)
  - **Jupyter Notebook** 给科研/培训
- **数据**: 本地 NetCDF + Parquet + SQLite (元数据)
- **依赖**: 全部走 conda-forge, 不允许必须从源码编译

### 5.2 HPC (有限承诺)
- 仅承诺: 1.0 的 NetCDF/Parquet 输出文件能在 HPC 上读
- 不承诺: Slurm 模板、MPI 并行、跨节点扩展
- 移到 §13: HPC 部署模板

### 5.3 云 / 嵌入式 / Web
全部移到 §13。

---

## 6. 算法选型 (精简)

| 决策点 | 1.0 选择 | 1.0 不引入 |
|---|---|---|
| 水动力后端 | SCHISM (外部, **见 §6.1 LTS pin**) + 内置 1D (**M0 调研建/买**) | 自研 2D/3D, GPU |
| 网格 | GMSH (外部) + Triangle | MFEM, deal.II |
| 数据栈 | NumPy/xarray/Pandas/Parquet/NetCDF | Arrow Flight, Zarr, Dask 分布式 |
| 工作流 | Snakemake | CWL, Nextflow |
| 校准 | PEST++ | UQLab, Chaospy |
| 容器 | OCI 镜像 (M0 必出 SCHISM 容器) | Apptainer, Helm |
| GUI | QGIS Plugin + Jupyter + CLI | Tauri, React, Web GUI |

### 6.1 SCHISM 集成策略 (新增, Gemini 二轮评审要求)

> SCHISM 子进程包装的脆弱性是 v0.2 最大未识别风险。M0 必须做以下工程加固。

#### 6.1.1 版本锁定
- **OpenLimno 1.0 锁定 SCHISM v5.11.0** (ADR-0002 M0 调研后定锚, 2025-02-07 发布, 是 SCHISM 当前最新且事实 LTS)
- 升级到未来 v5.12+ 是独立 PR + 完整回归套件通过
- 不支持用户自带任意 SCHISM 编译

#### 6.1.2 运行环境标准化 (v0.5 修订: SCHISM 不在 conda-forge)
M0 调研发现 SCHISM **未打包到 conda-forge**, 用户无法 `conda install`。修订分发策略:
- **OCI 容器 (主路径)**: `ghcr.io/openlimno/schism:5.11.0`, 多架构镜像 (linux/amd64, linux/arm64), CI 从源码编译
- **源码编译指南 (备路径)**: HPC 用户用; CMake + gfortran + OpenMPI + HDF5 + NetCDF-Fortran
- ~~conda-forge 包~~: 不可用; 若 SCHISM 后续上 conda-forge, ADR-0002 将被新 ADR superseded

#### 6.1.3 输入文件生成
- 使用 SCHISM 团队维护的 [pyschism](https://github.com/schism-dev/pyschism) (如适用)
- 不自研文本写出器去解析 hgrid.gr3 / param.nml; 用 schema 驱动写出 + 与 SCHISM 官方示例对照
- 每个 SCHISM 输入字段在 WEDM 都有可追溯映射, 不允许"裸字符串"配置

#### 6.1.4 输出读取
- 直接读 SCHISM 的 schout_*.nc (本就是 NetCDF), 不解析 stdout/log
- log 仅用于失败诊断, 不作为正常路径数据源

#### 6.1.5 Subprocess 控制
- 标准化 stdin/stdout/stderr 管道
- 超时 + 信号处理 + 失败回调
- log 滚动写到 work_dir, 失败时打包给用户提交 issue

---

---

## 7. 验证套件 (工程标准)

详见 §4.1.3 验收标准模板。强制 CI 集合:

| 套件 | 频率 | 通过标准 |
|---|---|---|
| MMS 1D | 每 PR | 二阶网格收敛 |
| Toro 1D Riemann | 每 PR | L1 < 0.5% |
| PHABSIM Bovee 1997 | 每 PR | WUA 表逐行 ≤ 1e-3 偏差 |
| FishXing 涵洞 | 每周 | 临界流量 ±2% |
| 国内真实流域 (待用户提供) | 每周 | 与现场观测 RMSE 写入验收 |
| 文档构建 | 每 PR | mkdocs strict mode 0 警告 |
| 安装回归 (Win/Mac/Linux × Python 3.11/3.12) | 每周 | pixi run pytest 全绿 |

---

## 8. API 草案 (简化)

### 8.1 Python API

```python
import openlimno as ol

# 1. 准备数据 (第一公里)
campaign = ol.preprocess.import_cross_sections("xs_lemhi_2024.csv", crs="EPSG:32612")
mesh    = ol.preprocess.mesh_from_cross_sections(campaign, dx_m=2.0)

case = ol.Case(
    name="lemhi_phabsim",
    mesh=mesh,
    hydro=ol.hydro.Builtin1D(scheme="preissmann"),
    habitat=ol.habitat.WUAQ(
        species=["oncorhynchus_mykiss"],
        stages=["spawning", "fry"],
        composite="geometric_mean",
    ),
    boundaries={
        "upstream":   ol.bc.Discharge.from_csv("Q_2024.csv"),
        "downstream": ol.bc.RatingCurve.from_parquet("rc.parquet"),
    },
)

# 2. 运行
result = case.run()    # 单进程, 同步, 进度条

# 3. 分析
result.wua.plot()
result.water_depth.isel(time=-1).plot()
result.export("out/")
```

### 8.2 CLI

```bash
openlimno init my-project
openlimno validate case.yaml
openlimno preprocess xs --in xs.csv --out mesh.nc
openlimno run case.yaml
openlimno wua case.yaml --species coho --stage spawning --plot
openlimno passage --culvert culvert.yaml --species rainbow_trout
openlimno calibrate case.yaml --observed gauges.csv --algo pestpp-glm
openlimno reproduce provenance.json
```

### 8.3 QGIS Plugin (1.0 必备, 部署策略, v0.3 扩展)

> Gemini 二轮: QGIS 自带 Python 与 pixi 隔离, GDAL/DLL 冲突会让"1.0 易安装"目标破产。M0 必须先固定部署策略, 不是 M4 再补。

#### 8.3.1 功能矩阵

| 阶段 | 功能 | 进度 |
|---|---|---|
| **M2 alpha (read-only viewer)** | 导入 WEDM 网格 / 结果, 显示 WUA / HSI 变量 | M2 必交付 (v0.3 前置) |
| **M3 beta (interactive)** | 修改 HSI 曲线, 触发本地运行 | M3 |
| **M4 GA** | 出版级出图 (legend/scalebar/north arrow), 多语言 (中文/英文) | M4 |

> **v0.3 关键变化**: 最小读图能力前置到 M2 (原 v0.2 是 M4 alpha)。理由: 没有 GUI 入口, 生态学家无法在 M2 验证 PHABSIM 等价。

#### 8.3.2 隔离策略 (避免 GDAL/Python/DLL 冲突)

QGIS 的 Python 环境与系统/pixi 隔离, 直接 `pip install openlimno` 在 QGIS 里**经常失败**。OpenLimno 采用三层策略:

1. **核心数据访问层**: 不依赖 OpenLimno Python 包; 仅用 QGIS 自带的 GDAL/Qt 能力打开 NetCDF/Parquet (read-only viewer 满足)
2. **计算调用层** (M3+): QGIS plugin 通过 subprocess 调用外部 `openlimno` CLI, 而**非**在 QGIS Python 进程内 import; 避免依赖隔离地狱
3. **运算结果回传**: 通过 NetCDF/Parquet 文件落盘, QGIS 重新打开

#### 8.3.3 分发渠道

- **官方 QGIS Plugin Repository** (主): 走 QGIS 官方审核流程
- **OSGeo4W / conda-forge 旁路** (备): 给企业内网/不能联外网用户
- **不分发**: 任何依赖 git 的"开发版"安装方式

#### 8.3.4 兼容性策略

- 对 QGIS LTS 版本测试 (M0 确定最低版本; 候选 3.34 LTS / 3.40 LTS)
- 每个 OpenLimno 1.x 版本对至少 1 个 QGIS LTS 版本承诺兼容
- CI 矩阵: QGIS LTS × Win/Mac/Linux

### 8.4 移到 §13
REST API, Arrow Flight, MCP server, Web GUI。

---

## 9. 仓库结构 (单仓 + 简化)

```
openlimno/
├── SPEC.md                         # 本文件
├── SPEC-v0.1-archive.md            # 历史
├── docs/                           # MkDocs Material
├── pixi.toml                       # 跨平台环境
├── pyproject.toml                  # 单一 Python 包 (1.0 不切多 package)
├── src/openlimno/
│   ├── wedm/                       # 数据模型 + JSON-Schema
│   ├── preprocess/                 # ⭐ 第一公里
│   ├── hydro/
│   │   ├── builtin_1d.py
│   │   └── schism.py
│   ├── habitat/                    # ⭐ HSI/WUA
│   ├── passage/                    # 涵洞 + 鱼游泳
│   ├── workflows/                  # Snakemake rules
│   ├── cli.py
│   └── qgis/                       # QGIS plugin (可独立打包)
├── benchmarks/                     # §7 验证套件
├── examples/                       # 教程数据
└── tests/
```

不引入 monorepo, 不引入多 package 切分, 不引入 Bazel。

---

## 10. 路线图 (v0.3 修订)

> v0.3 关键变化: QGIS 最小读图前置到 M2; preprocess M1 砍核心三件套; M0 必出 1D 引擎建/买调研记录、SCHISM 容器、3 名 maintainer 签字、WEDM JSON-Schema + 样例数据。

### 10.1 M0 必交付清单 (Codex/Gemini 二轮共识门槛)

进入 M1 前必须完成:

1. **3 名 maintainer 真名签字承诺书** — 来自 ≥2 个机构, 公开姓名 + 邮箱, 各占 commit 权
2. **WEDM v0.1 JSON-Schema + 真实样例数据包** — 一个真实流域 (USGS Lemhi 优先), 完整 NetCDF + Parquet 样本, 不是表格描述
3. **SCHISM 集成路线决策记录** — LTS 版本号 + conda-forge 包 + OCI 容器 + 与 pyschism 的关系
4. **1D 引擎建/买调研报告** — 自建 Saint-Venant vs 封装 MASCARET vs HEC-RAS 1D 开放组件; 输出 ADR (Architecture Decision Record)
5. **1.0 能力边界冻结声明** — 与本文件 §0.3 + 附录 A 完全一致
6. **三平台 CI + MkDocs 构建通过** — Win/Mac/Linux × Python 3.11/3.12

### 10.2 里程碑

| 里程碑 | 时间 | 交付 | 验证 |
|---|---|---|---|
| **M0** 立项 | T+2 月 | 上述 §10.1 六项 + 仓库骨架 + 治理章程 | 全部六项签字归档 |
| **M1** 第一公里 | T+5 月 | `preprocess` (CSV/Excel 横断面 + USGS QRev + GeoTIFF DEM 三件套) + WEDM 项目数据闭环表落地 | 1 个真实流域完整入库 (Lemhi) |
| **M2** PHABSIM 等价 + QGIS read-only | T+10 月 | `builtin-1d` (或封装) + `habitat` (HSI/WUA) + CLI + Jupyter + **QGIS read-only viewer** | Bovee 1997 表级 ≤ 1e-3 |
| **M3** SCHISM 包装 + QGIS interactive | T+13 月 | SCHISM 输入生成 + 结果读取 + WUA on 2D + QGIS 触发本地运行 | Lemhi 2D 案例 RMSE 在容差内 |
| **M4** 过鱼 + QGIS GA | T+16 月 | 涵洞 + 鱼游泳 + Snakemake calibrate + QGIS 出版级出图 | FishXing 涵洞临界流量 ±2% |
| **M5 / 1.0** | T+18 月 | 1.0 release, 完整文档, 3 个国际 + 软推荐国内 case study | §7 验证套件全绿 |

> 目标: 1.0 是 **桌面 PHABSIM 替代品 + 第一公里数据工具 + 通过 SCHISM 拿到 2D 栖息地能力 + 基础过鱼通过性**。

---

## 11. 治理与社区 (强化)

### 11.1 M0 必到位

- **3 名 maintainer**: 至少 2 个机构, 各占 commit 权; 公开姓名
- **release manager**: 季度 release, semver, changelog 强制
- **bus factor 应对**: 每个核心模块 (wedm/preprocess/hydro/habitat) ≥ 2 reviewer
- **deprecation policy**: 任何公开 API 弃用至少跨 1 个 minor 版本
- **文档责任人**: docs/ 有 CODEOWNER, CI 强制文档构建
- **示例数据 CI**: examples/ 必须每周自动跑通
- **API semver**: `openlimno.*` 公开 API 按 semver, 内部 (`_*`) 自由
- **降级路线**: 资金不达标时, 优先保 1.0 文档站 + bug 修复, 不接新功能

### 11.2 长期机制

- **许可**: 代码 Apache-2.0, 数据/规格 CC-BY-4.0
- **托管**: GitHub (主) + Gitee 镜像
- **PSC**: 5 人, 至少含 1 名生态学家、1 名水利工程师、1 名软件工程师
- **同行评审**: 关键算法发 GMD / EMS / Ecological Modelling 期刊
- **学术互操作**: 与 SCHISM 团队 MOU
- **中文社区**: 中文文档分站, 与中科院水生所/水科院 JV 用户组
- **国内特有种参数库** (v0.4 新增, 核心交付物): 由水科院 / 中科院水生所 / 长江所 / 珠江所共建国内 50+ 关键鱼种 (中华鲟/胭脂鱼/达氏鲟/圆口铜鱼/长鳍吻鮈/四大家鱼/裂腹鱼属) 的 species/life_stage/swimming/hsi/passage/migration_corridor/drifting_egg 参数; 不属于 maintainer 私有, 而是协作建设
  - M2 完成北美 + 欧洲常见种 (虹鳟/大西洋鲑/欧洲鳇/...)
  - M5 完成首期国内 10 种
  - 1.0 后由 PSC 国内分支持续维护

---

## 12. 风险与缓解 (修订)

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| **1.0 范围再次膨胀** (Codex/Gemini 评审主因) | 高 | 高 | §0.3 列黑名单; PR 模板要求声明"是否扩了 1.0 范围" |
| SCHISM 升级破坏包装 | 中 | 中 | pin 一个 LTS 版本, 升级走独立 PR + 完整回归 |
| 国内真实流域案例难找 | 中 | 中 | 与 1-2 家科研院所合作; 备选: 公开 USGS 数据 |
| PHABSIM bit-level 回归不可能 (HSI 实现细节差) | 中 | 中 | 退到表级一致 + 容差; 在 §7 写明 |
| 生态学家不会 Python/CLI | 高 | 高 | QGIS plugin 是 1.0 必交付, 不是 nice-to-have |
| 维护人手流失 | 中 | 高 | bus factor 2 + 治理章程 + 季度 release 强制纪律 |
| 鱼类参数区域差异 | 高 | 中 | 数据库分区 + `quality` 评级 + 用户贡献流程 |
| HEC-RAS 几何导入合规风险 | 中 | 低 | 仅读不写, 不分发 HEC-RAS 二进制 |
| **HSI 方法论 obsolete 被审稿人攻击** (v0.4 新增) | 中 | 高 | §4.2.2 强制 category/transferability/independence 字段; §13.17 RSF 明确占位; 投稿用 GMD 而非 EM 期刊以淡化方法论新颖性争议 |
| **国内特有种参数库共建拖延** (v0.4 新增) | 高 | 高 | M0 与 ≥2 家国内研究所 MOU; M5 国内 10 种是软门槛, 跑不到先用占位曲线发布 |
| **regulatory_export 三模板偏离实际审批口径** (v0.4 新增) | 中 | 中 | 各模板需 1 个真实项目验证; 在 §14 邀请监管/审批专家二轮评审 |
| **河床演变 P1 升级超出 18 月窗口** (v0.4 新增) | 中 | 高 | §13.7 M5-M6 是软目标; 1.0 用 §3.1.1 时变网格 (手工换网格) 顶住, 自动演化模型可拖到 1.x |

---

## 13. 研究路线 (1.0 不做, 但保留接口空间)

> 这一章是给评审者、合作者、资助方看的"未来愿景", 也是给 maintainer 的"防 scope creep 收纳箱"。任何 §0.3 列出的能力, PR 走这里。

每个条目格式: **能力名 / 优先级 / 大致 milestone / 与 1.0 接口要求**

### 13.1 自研 GPU 2D SWE 求解器
P2, M6+。1.0 必须保证 hydro 接口可加第 3 个 backend 而不破 API。

### 13.2 BMI 多求解器
P2, 与 13.1 同步。引入 BMI 替换当前简化的 `HydroSolver` Protocol。

### 13.3 不确定性量化 (UQ)
P3, M7+。集合预报、PCE、贝叶斯反演。Codex 评审建议默认不开, 配置项扩展。

### 13.4 数据同化 (DA)
P3, M8+。EnKF 接 USGS 流量站 / 中国水文站。

### 13.5 水温
P2, M5+。1D 平流-扩散 + 表面热通量, 河岸遮蔽。

### 13.6 水质
P3, M9+。DO / N / TSS, WASP 兼容。

### 13.7 泥沙与河床演变 (v0.4 升级: P3 → P1, M9+ → M5-M6, v0.5 口径澄清)

> **v0.5 关键澄清** (领域评审验收要求): "P1, M5-M6"指的是**1.x 首批**优先级, **不**抢 1.0 资源。1.0 release (M5/T+18 月) 不含此模块。M5-M6 是 1.0 之后立即启动的次轮交付, 通常对应 1.1 release。
>
> §0.3 黑名单中"水温/水质/泥沙/河床演变 (后期)"与本节"P1 1.x 首批"一致, 不矛盾。

回应领域评审盲点 5: PHABSIM 假设栖息地几何不变是其最大缺陷, OpenLimno 复刻这个假设等于复刻最大缺陷。三峡 / 向家坝 / 雅鲁藏布江都是真实痛点。

**1.0 兜底方案** (避免完全复刻 PHABSIM 静态假设):
- §3.1.1 时变网格 schema 已支持手工换网格
- 用户可手工提供"建坝前 / 建坝后"两期 mesh, 在同一 case 里跑两次 WUA, 做敏感性分析
- 这不是"自动河床演变", 是"手工换图触发 WUA 重算"

**1.x (本节) 自动模型**:
- 推移质: Meyer-Peter-Müller, Wong-Parker
- 悬移质: van Rijn
- 床面演化: Exner + 多粒级 Hirano-Parker
- 与 §3.1.1 时变网格集成: 河床演变后自动重构 mesh, 触发 WUA 重算

**资源分配纪律**: M0-M5 期间 §13.7 不占 maintainer 主线时间, 仅由 community contributor 在分支预研。

### 13.8 连通性
P2, M6+。DCI + 拆坝多目标优化。

### 13.9 IBM
P3, M10+。引入感官场契约 (Gemini 评审建议)。

### 13.10 种群动力学
P3, M11+。

### 13.11 ML 代理模型 (FNO 等)
P2, M7+。可作为嵌入式部署的核心。

### 13.12 嵌入式实时调度
P2, M8+。**重定义为读 ML 代理 / 预计算响应面**, 不现场跑物理求解器 (Codex+Gemini 共识)。

### 13.13 Web GUI / 云原生
P3, M9+。

### 13.14 Bayesian / Fuzzy HSI
P2, M6+。

### 13.15 漂移-觅食栖息地 (NREI)
P2, M7+。

### 13.16 多目标 e-flow Pareto
P2, M7+。NSGA-II/MOEA-D, 同时优化栖息地 / 水量 / 发电 / 灌溉。对应 IFIM 第四步 Alternatives Analysis。

### 13.17 RSF / Occupancy Modeling (v0.4 新增, 补盲点 2)
P2, M6+。回应 Mathur 1985 / Lancaster & Downes 2010 / Manly 2002 / Boyce 2006 对 HSI 的批评。
- Resource Selection Function: 用 logistic regression 替代 HSI 的"经验曲线"
- Occupancy Modeling: 同时考虑探测概率 + 占据概率 (MacKenzie 2002), 处理 false-absence
- 接口: 与 `hsi_curve` 表平行, 增加 `rsf_model` 表 (类型: glm/gam/randomforest, 参数, 评估指标 AUC/TSS)
- 1.0 不实现, 但 SPEC 必须明示"我们知道这个争议",防止学术界以"reinventing 1995 wheel"拒稿

### 13.18 Attraction Efficiency 子模型 + 复杂鱼道 (v0.4 新增, 补盲点 6)
P2, M7+。Castro-Santos 2005 / Bunt 2012 / Silva 2018。
- 基于下游引诱流速场 (从 SCHISM 2D 结果派生) + 鱼类感官场 (压力梯度 + 紊流强度) + 水温
- 与 §13.9 IBM 联动: 个体鱼带能量储备, 在引诱场中 Langevin 轨迹决定是否到达入口
- 复杂鱼道: vertical slot / weir-and-pool / Denil / nature-like
- 输出 η_A 分布, 与 §4.3 的 η_P 复合得 η = η_A × η_P

---

## 14. 评审请关注 (v0.5)

提请评审者就以下问题给反馈:

### 14.1 软件工程视角 (v0.2/v0.3 沿用)

1. **§3.1.4 项目数据闭环表是否覆盖你的真实工作流?** 缺哪张表?
2. **§4.0 第一公里是否抓对了?** ADCP/横断面/LiDAR 入口是否够?
3. **§2.3 SCHISM 边界划分是否合理?** "仅前后处理 + 子进程调用"是否过于保守?
4. **§4.1.3 工程可诊断验收标准是否够?** 还需哪类检查项?
5. **§10 路线图节奏是否仍乐观?** M2 (10 月内做 PHABSIM 等价) 是否现实?
6. **§11 治理章程是否够强?** ≥3 maintainer + 季度 release + bus factor 是否到位?
7. **§13 研究路线是否对你重要?** 哪些条目应该提到 1.0?

### 14.2 生态水利领域视角 (v0.4 新增)

8. **§4.4 studyplan 是否覆盖 IFIM 五步法的研究设计环节?** 你做生态流量推荐时, 第几步最痛?
9. **§4.2.2 HSI 严格化是否过度?** quality_grade 与 acknowledge_independence 是否会让用户嫌烦?
10. **§4.2.3 多尺度聚合 (cell/HMU/reach) 是否抓对了?** 你的项目里 HMU 类型有没有 SPEC 之外的 (如 alcove, side channel)?
11. **§4.2.4 监管输出三模板 (CN-SL712 / US-FERC / EU-WFD) 是否够?** 还要哪个监管框架?
12. **§4.3 attraction vs passage 拆分是否清楚?** 你做过鱼项目里 η_A 一般怎么测?
13. **§4.2.6 产漂流性卵评估** 是否覆盖了四大家鱼工作流? 还缺什么变量?
14. **§3.1.3 物种参数库** 国内特有种数据 你能贡献几种?
15. **§13.7 河床演变升 P1** 是否激进? 1.0 时变网格手工换网格是否够顶?

### 14.3 监管/审批专家二轮评审 (v0.5 新增)

> 领域评审验收要求: 监管模板 (§4.2.4.2) 1.0 是模板架子, 能否过审需对口审查。M2 节点 (T+10 月, PHABSIM 等价里程碑) 必须邀请下列三方各 1 名专家做正式 review:

| 监管框架 | 邀请专家来源 | 审查重点 |
|---|---|---|
| **CN-SL712** | SL/Z 712-2014 编制单位 (水利部水资源管理中心 / 中国水科院) | "四件套"输出能否直接进省级生态流量论证报告; 与《水利水电建设项目水资源论证导则》对齐 |
| **US-FERC-4e** | FERC 项目承包商代表 (北美生态流量咨询公司, 如 Stillwater Sciences / R2 Resource) | 输出能否进 FERC 再发证申请书; ESA section 7 consultation biological opinion 模板 |
| **EU-WFD** | River Basin Management Plan 编制单位 (欧盟成员国流域管理局, 如英国 EA / 德国 LfU) | 与 WFD 6 年管理周期对齐; BQE 五指标整合路径 |

每位专家提供: ≤1500 字书面 review, 列举本框架下不可妥协的合规字段, 1.0 GA 前必须满足。

PSC 在 M2 评审会议正式 acknowledge 三位专家为 reviewer-of-record (与 GMD model description paper 同步)。

---

## 附录 A. 与现有软件对照 (1.0 vs 研究路线)

> v0.3 修订: 修复 §0.3 与本表 2D 标注的自相矛盾。"OpenLimno 自有"列指 OpenLimno 代码库内的实现; "工作流可达"列指通过外部依赖能跑通的功能。

| 功能 | OpenLimno 自有 (1.0) | 工作流可达 (1.0) | 研究路线 |
|---|---|---|---|
| 1D 水力 | ✓ (内置 1D 或封装, M0 决定) | ✓ | — |
| 2D 水力 | ✗ (不自有) | ✓ (通过 SCHISM 外部) | 自研 GPU (§13.1) |
| 3D 水力 | ✗ | ✓ (通过 SCHISM 外部) | (§13) |
| 涵洞水力 | ✓ | ✓ | — |
| HSI 单/复合 | ✓ (含 category/transferability/independence) | ✓ | — |
| WUA-Q (cell/HMU/reach 三尺度, v0.4) | ✓ | ✓ | — |
| WUA-time / HTS / HDC / HFA (v0.4) | ✓ | ✓ | — |
| 持续栖息地 | ✓ | ✓ | — |
| **多尺度聚合 (cell/HMU/reach)** (v0.4) | ✓ | ✓ | — |
| **产漂流性卵评估** (v0.4) | ✓ (1D Lagrangian) | ✓ | 2D 分散 (§13) |
| **监管导出 CN-SL712/US-FERC/EU-WFD** (v0.4) | ✓ | ✓ | — |
| 鱼类游泳 | ✓ | ✓ | — |
| **过鱼 η_P (passage success rate)** (v0.4) | ✓ (确定性 + Monte Carlo) | ✓ | — |
| **过鱼 η_A (attraction efficiency)** (v0.4) | ✗ (用户输入常数) | — | §13.18 |
| 复杂鱼道 (vertical slot / Denil) | — | — | §13.18 |
| **studyplan IFIM 研究设计** (v0.4) | ✓ (轻量 YAML) | ✓ | 替代方案分析 (§13.16) |
| **migration_corridor 洄游通道** (v0.4) | ✓ (数据模型) | ✓ | — |
| **HMU 自动分类** (v0.4) | ✓ | ✓ | — |
| **时变网格 (河床演变手工换图)** (v0.4) | ✓ | — | 自动河床演变 (§13.7) |
| Bayesian/Fuzzy HSI | — | — | §13.14 |
| **RSF/Occupancy** (v0.4 占位) | — | — | §13.17 |
| 漂移-觅食 NREI | — | — | §13.15 |
| 不确定性 | — | — | §13.3 |
| 数据同化 | — | — | §13.4 |
| 水温/水质 | — | — | §13.5/6 |
| **泥沙 + 河床演变** (v0.4 P1) | — | — | §13.7 (M5-M6) |
| GPU | — | — | §13.1 |
| 云原生 | — | — | §13.13 |
| 嵌入式 | — | — | §13.12 (改为读响应面) |
| Web GUI | — | — | §13.13 |
| QGIS plugin | ✓ | ✓ | — |
| CLI / Jupyter | ✓ | ✓ | — |

---

## 附录 B. 评审历史

| 日期 | 版本 | 评审者 | 关键反馈 | 处理 |
|---|---|---|---|---|
| 2026-05-07 | v0.1 | Codex 一轮 | 9 点: 范围失控/A 轨不成立/GPU 目标过硬/WEDM 缺数据闭环/零拷贝不可兑现/四形态死亡/runtime-min 矛盾/验证标准/治理缺机制 | 全部纳入 v0.2 |
| 2026-05-07 | v0.1 | Gemini 一轮 | 8 点: 四形态过载/双轨黑洞/缺第一公里/路线图幻觉/数值无敬畏/治理陷阱/UQ 过度/过鱼无感官场 | 1-7 纳入 v0.2; 第 8 点感官场移到 §13.9 |
| 2026-05-07 | v0.2 | Codex 二轮 | 准予进入 M0; 新硬伤 3 点: 2D 边界自相矛盾 / QGIS 太晚 / preprocess 太重; M0 退出条件 3 项 | 全部纳入 v0.3 |
| 2026-05-07 | v0.2 | Gemini 二轮 | 准予进入 M0; 新硬伤 4 点: SCHISM 子进程脆弱 / 1D 引擎重造轮子 / .g0X 黑盒 / QGIS 部署摩擦 | SCHISM/QGIS 部署纳入 v0.3; 1D 引擎建/买移到 M0 调研; .g0X 改 best-effort |
| 2026-05-07 | v0.3 | 生态水利领域评审 | 8 点领域盲点: IFIM 五步法只覆盖第 3 步 / HSI 科学性争议 / micro-only 缺 meso/macro / 数据闭环缺生物观测 / 河床演变假设静态 / attraction-passage 混淆 / 国内特有种装不下 / 监管输出鸿沟 | **全部纳入 v0.4** |
| 2026-05-07 | v0.4 | 生态水利领域评审验收 | **准予有条件冻结**; 6 PASS / 2 PARTIAL / 0 FAIL; 6 个内部矛盾 + 7 条 1.0 GA 背书条件 | **13 条全部纳入 v0.5** |
| 2026-05-07 | v0.5 | 生态水利领域评审三轮验收 | **无条件 approved-for-M0**; 12/12 PASS; SPEC 进入冻结期 | 不再开新一轮领域评审, 仅接受流域案例驱动的字段补丁 |

---

## 附录 C. 参考文献骨架

**水力 + IFIM 经典**
- Bovee, K.D. (1986) IFIM stream habitat analysis. USGS Biological Report 86(7)
- Bovee et al. (1998) Stream Habitat Analysis Using IFIM. USGS Biological Resources Division Information and Technology Report
- Stalnaker et al. (1995) PHABSIM Reference Manual
- Steffler & Blackburn (2002) River2D Technical Manual
- Milhous, R.T. (1990) The calculation of flushing flows for gravel and cobble bed rivers (Habitat Time Series / Duration / Frequency)
- Zhang et al. (2016) SCHISM v5.x technical reference

**HSI 科学性 (v0.4 新增)**
- Mathur et al. (1985) A critique of the IFIM. Canadian J Fisheries Aquatic Sci
- Williams (1996) Lost in space: Habitat-based assessment errors. Ecology
- Lancaster & Downes (2010) Linking the hydraulic world of individual organisms to ecological processes. River Research and Applications
- Manly et al. (2002) Resource Selection by Animals (RSF 经典)
- Boyce (2006) Scale for resource selection functions. Diversity and Distributions
- MacKenzie et al. (2002) Estimating site occupancy rates when detection probabilities are less than one. Ecology

**中尺度 / MesoHABSIM (v0.4 新增)**
- Frissell et al. (1986) A hierarchical framework for stream habitat classification. Environmental Management
- Kemp et al. (1999) Mesohabitats and the management of fluvial systems. Hydrobiologia
- Parasiewicz (2001) MesoHABSIM. Fisheries
- Parasiewicz (2007) The MesoHABSIM model revisited. River Research and Applications
- Wadeson (1994) A geomorphological approach to the identification of channel-related stream habitats

**过鱼 attraction vs passage (v0.4 新增)**
- Castro-Santos (2005) Optimal swim speeds for traversing velocity barriers
- Bunt et al. (2012) Performance of fish passage structures at upstream barriers
- Silva et al. (2018) The future of fish passage science, engineering, and practice. Fish and Fisheries

**河床演变与栖息地 (v0.4 新增, P1 升级依据)**
- Kondolf (2000) Assessing salmonid spawning gravel quality. TAFS
- Lamouroux et al. (2008) Stream gradient and salmonid habitat. River Research and Applications

**水力数值方法**
- FHWA HY-8 Culvert Hydraulic Analysis Program
- USFS FishXing Documentation
- Audusse et al. (2004) Well-balanced SWE
- Bollermann et al. (2011) Dry-bed treatment

**监管框架 (v0.4 新增)**
- 中华人民共和国《河湖生态流量计算规范》 SL/Z 712-2014
- US FERC 4(e) Conditions, 18 CFR Part 4
- EU Water Framework Directive 2000/60/EC, Annex V
- Poff et al. (2010) The ecological limits of hydrologic alteration (ELOHA): a new framework

**中文文献骨架 (v0.5 补)**
- 易伯鲁等《长江鱼类早期资源》 (1988, 经典四大家鱼漂流性卵孵化研究)
- 曹文宣《长江上游特有鱼类自然保护区的建立及其相关问题的思考》(2008)
- 曹文宣等《青鱼草鱼鲢鳙四大家鱼及生态学研究》系列
- 段中华等《长江中游四大家鱼产漂流性卵孵化的水温与流速条件》
- 段辛斌、陈大庆等《三峡库区蓄水后长江上游产漂流性卵鱼类繁殖状况》
- 中华人民共和国水利水电行业标准《水利水电工程鱼道设计导则》SL 609-2013
- 中华人民共和国《河湖生态流量计算规范》 SL/Z 712-2014
- 中华人民共和国《水利水电建设项目水资源论证导则》SL 525
- 杨宇等《基于栖息地模拟的河道内生态需水研究》
- 易雨君等《PHABSIM 在中华鲟产卵河段适宜生境评价中的应用》

---

*— v0.2 是 v0.1 的瘦身重写, 核心原则: **范围纪律 + 单引擎深度集成 + 桌面优先 + 工程可诊断 + 治理先行**。任何条款在 1.0 发布前可被推翻, 请通过 GitHub Issue 提案。*
