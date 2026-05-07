# OpenLimno 技术规格书 (SPEC)

| 字段 | 内容 |
|---|---|
| 版本 | 0.1.0-draft |
| 状态 | Request for Comments |
| 起草日期 | 2026-05-07 |
| 适用范围 | 完整对标 FishXing / PHABSIM / River2D 并扩展为现代水生态建模平台 |
| 许可 | Apache-2.0 (代码) / CC-BY-4.0 (规格、数据、文档) |

---

## 0. 引言

### 0.1 目的
定义一个开源水生态建模平台的**架构、数据模型、模块边界与接口契约**,使任何符合规格的实现都能互操作,并为首版实现提供可执行的工程依据。

### 0.2 设计目标 (优先级有序)

1. **可信** — 所有数值结果可复现,带数据/代码/容器指纹
2. **可演化** — 模块边界稳定,内部实现可换不破坏外部
3. **可移植** — 同一份模型描述跑在桌面/HPC/云/边缘四种形态
4. **可验证** — 自带与 PHABSIM/River2D/FishXing 对比的回归基准
5. **现代** — 支持 GPU、不确定性量化、ML 代理、数据同化

### 0.3 非目标 (本规格不解决)

- 通用 CFD 框架 (推荐 OpenFOAM)
- 海洋/河口锋面级三维建模 (推荐 SCHISM/Delft3D-FM, OpenLimno 通过 BMI 包装)
- 流域水文 (推荐 mHM/SWAT/HEC-HMS, 通过 BMI 接入)

### 0.4 术语

| 缩写 | 全称 | 注 |
|---|---|---|
| WEDM | Water Ecology Data Model | 本规格定义的数据模型 |
| BMI | Basic Model Interface | NOAA OWP 标准 |
| HSI | Habitat Suitability Index | 栖息地适宜度指数 |
| WUA | Weighted Usable Area | 加权可用面积 |
| IFIM | Instream Flow Incremental Methodology | 河道内流量增量法 |
| UGRID | Unstructured Grid Conventions | NetCDF 非结构网格约定 |
| CF | Climate and Forecast Conventions | NetCDF 元数据约定 |
| IBM | Individual-Based Model | 个体模型 |

---

## 1. 设计原则

### P1 契约高于实现
顶层定义五类契约: 数据、求解器、耦合、进程间通信、工作流。模块语言、依赖、硬件后端均为实现细节。

### P2 双轨求解器
每个核心物理求解器有两条路径:
- **A 轨 (默认)**: 封装现有成熟开源求解器 (SCHISM/ANUGA/HEC-RAS 等), 提供 BMI 适配层
- **B 轨 (高性能)**: 自研 GPU 原生求解器, 长期目标取代 A 轨默认

调用方通过配置 `solver.backend: schism | native | hec-ras` 切换, 数据格式与栖息地后处理完全一致。

### P3 全开放数据
不允许私有二进制格式作为持久化输出。所有持久化输出必须是 UGRID/CF-NetCDF, Zarr, Parquet, GeoParquet, COG 之一。配置一律 YAML + JSON-Schema。

### P4 瘦身可达
存在一个 **runtime-min** 子集, 不依赖 Python/MPI/GPU, 可静态链接到嵌入式设备 (ARM Linux, < 50 MB 镜像), 用于实时调度场景。

### P5 渐进精度
同一个研究区域可以从 1D 起步, 局部加密到 2D, 关键过鱼/取水口段加密到 3D, 各维度间通过 WEDM 嵌套耦合。

### P6 不确定性是一等公民
每个模拟接受概率输入 (集合/采样/PCE), 输出带置信区间。点估计是 ensemble size = 1 的特例。

### P7 可重复
每次运行产出 `provenance.json`, 含: git 提交哈希、依赖锁定、容器镜像 SHA、输入数据 SHA-256、参数指纹、运行时间、机器指纹。可一键重跑。

---

## 2. 系统架构

### 2.1 分层视图

```
┌────────────────────────────────────────────────────────┐
│ L5  接入                                                │
│  Web GUI │ QGIS Plugin │ Jupyter │ CLI │ MCP Server     │
├────────────────────────────────────────────────────────┤
│ L4  编排                                                │
│  CWL/Snakemake 工作流 │ 校准 │ UQ │ 数据同化 │ 情景      │
├────────────────────────────────────────────────────────┤
│ L3  生态                                                │
│  Habitat (HSI/WUA/时序) │ Passage │ IBM │ Population    │
│  Connectivity │ Bioenergetics                          │
├────────────────────────────────────────────────────────┤
│ L2  环境                                                │
│  Thermal │ WaterQuality │ Sediment │ Morphodynamics    │
├────────────────────────────────────────────────────────┤
│ L1  水动力 (双轨)                                        │
│  A 轨包装: SCHISM, ANUGA, HEC-RAS-2D, MIKE, Delft3D-FM   │
│  B 轨自研: 1D Saint-Venant, 2D SWE-FV-GPU, 3D-NH        │
├────────────────────────────────────────────────────────┤
│ L0  内核                                                │
│  Mesh │ IO (NetCDF/Zarr/Parquet) │ Coupler │ Provenance │
└────────────────────────────────────────────────────────┘
```

### 2.2 进程拓扑 (四种部署形态共用)

```
[Orchestrator] ──BMI/Arrow Flight──> [Solver Worker] × N
      │                                     │
      └──> [Provenance Store]                └──> [Data Store: NetCDF/Zarr]
```

形态差异:

| 形态 | Orchestrator | Worker | Data Store |
|---|---|---|---|
| 桌面 | 同进程 Python | 同进程 lib | 本地 NetCDF |
| HPC | Slurm 任务 | MPI 进程组 | 并行 HDF5 / Lustre |
| 云原生 | K8s Job | Pod (gRPC) | S3 + Zarr |
| 嵌入式 | runtime-min | 同进程 lib | 本地 SQLite + 增量 NetCDF |

---

## 3. 核心契约

### 3.1 WEDM — 水生态通用数据模型

#### 3.1.1 几何/网格层
- **基础**: NetCDF-4 + UGRID-1.0
- **维度**: 1D (横断面链), 2D (节点+面), 3D (Schism-style 垂向 σ/z 混合)
- **必备变量**:
  - `mesh2d_node_x/y` (lon/lat 或投影坐标, EPSG 必填于 `crs` 属性)
  - `mesh2d_face_nodes` (节点拓扑)
  - `mesh2d_edge_nodes` (边拓扑)
  - `bottom_elevation` (河床高程, m, CF 标准名)
  - 可选: `roughness_manning`, `vegetation_density`, `substrate_class`

#### 3.1.2 时变场层
- **存储**: 结果使用 Zarr v3 (云) 或 NetCDF-4 (本地), 必须可选
- **必填字段**: `time`, `water_depth`, `velocity_x`, `velocity_y` (2D); 加 `velocity_z`, `temperature` (3D)
- **CF 元数据**: 全部字段含 `standard_name`, `units`, `cell_methods`
- **分块策略**: 时间维 chunk = 1, 空间维按 face_block (默认 4096) 切分; 云上自动跨 chunk 并发读

#### 3.1.3 物种与栖息地参数库
- **格式**: Apache Parquet (主) + GeoParquet (空间分布)
- **核心表**:
  - `species` (taxon_id PK, 学名, 中文名, IUCN 状态, 流域分布)
  - `life_stage` (species, stage 即产卵/稚鱼/幼鱼/成鱼, 时间窗口)
  - `swimming_performance` (species, stage, temp_C, burst/prolonged/sustained 速度 cm/s, 数据源 DOI)
  - `hsi_curve` (species, stage, variable 即 depth/velocity/substrate/cover, x, suitability ∈ [0,1])
  - `bioenergetics` (Wisconsin 公式参数: CA/CB/RA/RB/SDA/EA/...)
  - `passage_criteria` (jump_height_max, leap_speed_min, fatigue_curve_id)
- **种子数据**: 集成 FishBase, FishXing 鱼种库, USFWS HSI 文献库, 中国《淡水鱼类志》数据

#### 3.1.4 配置层
- **格式**: YAML 1.2, 严格 JSON-Schema 校验, 不允许未声明字段
- **顶层 schema** (示意):

```yaml
openlimno: 0.1
case:
  name: lemhi_2024
  crs: EPSG:32612
mesh:
  uri: file://lemhi.ugrid.nc
hydrodynamics:
  backend: native-2d-gpu     # 或 schism, anuga, hec-ras-2d
  scheme: fv-roe-wb
  cfl: 0.4
  boundaries:
    upstream:  { type: discharge, series: file://Q_2024.csv }
    downstream:{ type: rating-curve, ref: file://rc.csv }
habitat:
  species: [oncorhynchus_mykiss]
  stages:  [spawning, fry]
  metric:  wua-time
output:
  uri: s3://my-bucket/lemhi/2024/
  format: zarr
  vars: [water_depth, velocity_magnitude, wua, hsi_*]
provenance:
  emit: true
ensemble:                    # 不确定性是一等公民
  size: 64
  perturb:
    - { var: roughness_manning, dist: lognormal, mu: -2.3, sigma: 0.2 }
```

### 3.2 BMI — 求解器接口

每个 L1/L2 求解器实现 BMI 2.0 (NOAA OWP 标准) 的扩展子集:

```text
# 生命周期
initialize(config_path) -> status
update(dt_seconds)       -> status
update_until(t)          -> status
finalize()               -> status

# 时间
get_start_time(); get_end_time(); get_current_time(); get_time_step(); get_time_units()

# 输入/输出变量
get_input_var_names();  get_output_var_names()
get_var_grid(name); get_var_type(name); get_var_units(name); get_var_itemsize(name)
get_value(name);   get_value_at_indices(name, idx)
set_value(name);   set_value_at_indices(name, idx)

# 网格
get_grid_rank(grid); get_grid_size(grid); get_grid_type(grid)
get_grid_nodes_per_face(grid); get_grid_face_nodes(grid); ...

# OpenLimno 扩展 (前缀 ol_*)
ol_get_provenance() -> json     # 算法、参考文献、版本
ol_get_capabilities() -> list   # 例如 ["wet-dry", "subgrid", "gpu"]
ol_export_to_wedm(uri)          # 直接输出符合 WEDM 的结果
```

### 3.3 耦合协议

#### 3.3.1 时间步模式
- **lockstep**: 所有模块同 `dt`
- **subcycle**: 慢模块 (种群 d) 包慢循环, 快模块 (水力 s) 内层多步
- **adaptive**: 由 CFL/物理稳定性反馈驱动

#### 3.3.2 变量交换
- **强类型**: 每条耦合连线声明源/汇 var, 单位转换由 coupler 自动 (基于 CF units)
- **位置匹配**: source 和 sink 网格不同时, 使用守恒插值 (面积权重 / SCRIP 权重)
- **隐式选项**: 关键耦合 (温度 ↔ 流量) 支持牛顿外迭代

#### 3.3.3 耦合配置示例

```yaml
coupling:
  mode: subcycle
  pairs:
    - { source: hydrodynamics.water_depth,  sink: habitat.water_depth }
    - { source: hydrodynamics.velocity,     sink: habitat.velocity }
    - { source: thermal.temperature,        sink: habitat.temperature }
    - { source: habitat.fish_density,       sink: ibm.spatial_density }
```

### 3.4 进程间通信

| 场景 | 协议 | 数据 |
|---|---|---|
| 同进程 | 直接函数调用 | C ABI / Arrow C Data Interface (零拷贝) |
| 同机多进程 | Unix 域套接字 + Arrow Flight | Arrow RecordBatch |
| 跨机/云 | gRPC + Arrow Flight | Arrow RecordBatch |
| 持久化 | NetCDF/Zarr/Parquet | WEDM |

零拷贝路径: numpy ↔ Arrow ↔ C++ Eigen ↔ CUDA device 全程不拷贝。

### 3.5 工作流

- **首选**: Snakemake (Python 友好, 科研社区接受度高)
- **可选**: CWL (跨工具更通用), Nextflow (云/HPC 强)
- **必备工作流**:
  - `calibrate`: 参数校准 (PEST++/Latin Hypercube/CMA-ES)
  - `uq-mc`: 蒙特卡洛不确定性
  - `uq-pce`: 多项式混沌展开
  - `da-enkf`: 集合卡尔曼滤波同化
  - `scenario-cmip6`: CMIP6 强迫情景跑批
  - `regression-test`: 自动跑全部基准

---

## 4. 模块规格

### 4.1 水动力 — `openlimno.hydrodynamics`

#### 4.1.1 双轨实现

| 后端 | A 轨 (包装) | B 轨 (自研) |
|---|---|---|
| 1D | HEC-RAS 1D / MIKE11 (BMI) | Saint-Venant FV, well-balanced, 隐式时间 |
| 2D | SCHISM-2D / ANUGA / HEC-RAS-2D | SWE FV-Roe + WB, 干湿动方程, GPU (CUDA/HIP) |
| 3D | SCHISM-3D / Delft3D-FM | NH-SWE, σ-z 混合, GPU (远期) |

#### 4.1.2 1D Saint-Venant (B 轨)

控制方程:
```
∂A/∂t + ∂Q/∂x = q_lat
∂Q/∂t + ∂(Q²/A)/∂x + gA·∂h/∂x = -gA·S_f + q_lat·v_lat
```
- 离散: Preissmann 4 点隐式 (默认), 可选 Lax-Wendroff 显式
- 摩阻: Manning, 可逐段标定
- 涵洞/桥梁/堰: 内嵌局部模型 (HEC-RAS 兼容)

#### 4.1.3 2D SWE (B 轨)

```
∂h/∂t + ∇·(h·u) = 0
∂(h·u)/∂t + ∇·(h·u⊗u + ½gh²I) = -gh∇z_b - C_f|u|u + ν_t∇·(h∇u)
```
- 网格: 三角/四边形非结构, MFEM/PUMI 后端
- 数值: 二阶 FV, Roe + Harten 熵修正, well-balanced (Audusse), MUSCL 重构
- 干湿: 非负重构 + 局部重力倾斜处理 (Bollermann 2011)
- 时间: 显式 SSP-RK2, 自适应 CFL ≤ 0.4
- 并行: 域分解 ParMETIS, 单 GPU 1M 元素 50 步/秒 (目标)
- 子格地形: 可选 (Casulli 2009) 用于稀疏网格高精度

#### 4.1.4 验证套件 (强制通过)
- 静水 well-balanced 测试 (机器精度)
- 抛物碗 (Thacker 解析解)
- Toro 1D Riemann 集
- 圆柱绕流
- USGS Lemhi River 与 River2D 对比 (RMSE 流速 < 10%)
- Boscastle 2004 洪水真实案例

### 4.2 水温 — `openlimno.thermal`

- 1D 平流-扩散 + 表面热通量 (短波/长波/感热/潜热)
- 河岸遮蔽: DEM + 太阳轨迹 (Heat Source 模型经验)
- 2D 深度平均温度
- 3D σ 层温度 (与 3D 水动力共网格)
- 校准接口: 标定与遥测温度链 RMSE < 0.5 °C

### 4.3 水质 — `openlimno.waterquality`

最小集 (v1):
- DO (Streeter-Phelps + 温度修正)
- Nitrogen (NH4-NO3-NO2)
- TSS (与泥沙模块耦合)

扩展集 (v2): WASP 兼容反应网络, 用户可声明 SBML/反应 YAML。

### 4.4 泥沙与河床演变 — `openlimno.sediment`

- 推移质: Meyer-Peter-Müller, Wong-Parker
- 悬移质: van Rijn, Wu-Wang-Jia
- 床面演化: Exner 方程, 多粒级隐藏暴露 (Hirano-Parker)
- 与栖息地耦合: 提供 `substrate_class` 时变场, 直接进入 HSI

### 4.5 栖息地评估 — `openlimno.habitat` ⭐

**这是 OpenLimno 的核心差异化模块, 重点设计**

#### 4.5.1 评估方法谱系

| 方法 | 输入 | 输出 | 对标 |
|---|---|---|---|
| HSI 单变量 | h, u, sub, cov | HSI ∈ [0,1] | PHABSIM |
| HSI 复合 (几何/算术/最小) | 上述 | 综合 HSI | PHABSIM |
| Fuzzy HSI | 上述 + 模糊规则 | HSI 分布 | EVHA |
| Bayesian HSI | 监测数据先验 | HSI 后验分布 | 文献新方法 |
| WUA-Q | 多流量水力结果 | WUA-Q 曲线 | PHABSIM/R2D 核心产品 |
| WUA-time | 时间序列水力 | 时序 WUA | 超 PHABSIM |
| 漂移-觅食栖息地 | h, u, drift conc | 净能量收益 | NREI 模型 (Hayes 2007+) |
| 持久化栖息地 | 时序栖息地 | 栖息地持续天数, 阈值穿越频次 | 现代生态流量指标 |

#### 4.5.2 HSI 曲线表示

支持四种内部表达, 任选其一存到 WEDM:
1. **分段线性**: `[(x_i, hsi_i)]` (PHABSIM 兼容)
2. **B 样条**: 节点 + 系数 (光滑可微)
3. **Fuzzy**: 三角/梯形隶属函数 + 规则集
4. **Bayesian Beta**: 每点 (α, β), 输出区间

```python
class HSICurve:
    species: str
    life_stage: str
    variable: Literal["depth", "velocity", "substrate", "cover", "temperature"]
    representation: Literal["piecewise", "spline", "fuzzy", "bayesian"]
    data: ArrayLike
    references: list[Doi]
```

#### 4.5.3 WUA 计算

```
WUA = Σ_i  A_i · CSI_i
CSI_i = f(HSI_h, HSI_v, HSI_sub, HSI_cov)
   f ∈ {geometric_mean, arithmetic_mean, min, weighted_geometric, fuzzy_inference}
```

并行实现: 直接在 Zarr/NetCDF 时序场上向量化, 单核 100M 元胞·步 < 5 秒 (目标)。

#### 4.5.4 生态流量产品

直接产出常用决策指标:
- **WUA-Q 曲线** (绘流量-栖息地)
- **栖息地时间序列**: 含极小值期、变化率
- **生境持久性**: %time HSI > 阈
- **Tennant / Texas / Wetted-perimeter** 经典方法 (基线对比用)
- **环境流量推荐 (e-flow recommendation)**: 多目标 Pareto 前沿 (栖息地 vs 水量 vs 发电 vs 灌溉)

### 4.6 过鱼通过性 — `openlimno.passage`

#### 4.6.1 涵洞/堰水力
- 渐变流 (Hagar)、跳跃流、倒灌流统一处理
- HY-8 涵洞库 (FHWA) 兼容
- 自动检测堰流/孔流转换

#### 4.6.2 鱼类游泳模型
- 三段式: burst (< 20 s), prolonged (20 s – 200 min), sustained (> 200 min)
- 温度依赖: 多项式或 Brett 风格曲线
- 疲劳曲线: log(time) ~ a + b·U
- 数据源: FishBase, FishXing 数据库, 中国流域种类补充

#### 4.6.3 通过性算法
- **确定性 (FishXing 兼容)**: 给定流量、鱼种、长度, 返回 pass/fail + 临界点
- **概率性 (默认)**: 蒙特卡洛 N=1000, 抽样 (鱼长度, 起跳能, 温度, 流量), 输出通过率分布
- **IBM 微观**: 每条虚拟鱼带能量, 在 2D/3D 速度场中走 Langevin 轨迹, 输出空间通过热图 (远期)

### 4.7 连通性 — `openlimno.connectivity`

- DCI (Dendritic Connectivity Index)
- 基于阻力面的最小代价路径
- 多目标拆坝优化 (与生态流量耦合, 用 NSGA-II/MOEA/D)

### 4.8 IBM/种群 — `openlimno.ibm`, `openlimno.population`

v1 仅占位接口; v2 重点实现; v3 与 InSTREAM/HexSim 互操作。

---

## 5. 部署形态

### 5.1 桌面 (生态学家)
- **打包**: Pixi (跨 Win/Mac/Linux), 一键 `pixi run openlimno-gui`
- **GUI**: Web 技术栈 (Tauri 壳), 不需要联网
- **数据**: 本地 NetCDF, 内置 SQLite 元数据
- **限制**: 默认串行 + 单 GPU, 不开 MPI

### 5.2 HPC 集群
- **打包**: Spack 配方 + Apptainer/Singularity 镜像
- **依赖**: MPI (OpenMPI/MPICH), CUDA/ROCm, 并行 HDF5
- **作业**: Slurm/PBS 模板, snakemake 自动生成
- **数据**: Lustre/GPFS, 并行 IO
- **目标性能**: 100M 元素 SWE 在 8×A100 上 < 1 分钟稳态

### 5.3 云原生
- **打包**: 多架构 OCI 镜像 (linux/amd64, linux/arm64), 体积 < 1 GB
- **编排**: Helm chart, Argo Workflows
- **存储**: S3/GCS/Azure Blob + Zarr v3
- **服务**: REST + Arrow Flight gRPC, OAuth2/OIDC
- **多租户**: 命名空间隔离 + 按运行计费的 provenance

### 5.4 嵌入式/实时 (runtime-min)
- **目标硬件**: ARM64 Linux (Jetson, RPi5), x86 工控机
- **镜像**: < 50 MB, 静态链接, 无 Python 依赖
- **能力子集**: 仅 1D 水动力 + 简易 HSI + 过鱼通过性, 无 GUI
- **数据**: SQLite + 增量 NetCDF (按小时滚动)
- **接口**: MQTT (传感器数据接入), HTTP (规则引擎)
- **场景**: 水电站生态流量调度, 鱼道通过率实时预警, 水质阈值告警

---

## 6. 算法选型与依据

| 决策点 | 选择 | 依据 |
|---|---|---|
| 网格库 | MFEM (核心) + GMSH (生成) | 协议兼容 Apache-2.0, 非结构 + 高阶 + 并行成熟 |
| 线性求解器 | PETSc / Hypre | HPC 事实标准 |
| 插值/重映射 | ESMF / SCRIP | 守恒映射事实标准 |
| 并行模式 | MPI + 一级 GPU + (可选 OpenMP) | HPC 兼容性最好 |
| 优化/校准 | PEST++, scipy.optimize, CMA-ES | PEST++ 在水文社区是事实标准 |
| UQ | UQLab / Chaospy / MUQ2 | 覆盖采样、PCE、贝叶斯反演 |
| ML 代理 | PyTorch + neuraloperator (FNO) | 社区大、模型可移植 (ONNX) |
| 数据同化 | DART / OpenDA | 集合方法成熟 |
| 工作流 | Snakemake (默认) + CWL (互操作) | 兼顾科研友好与可移植 |
| 容器 | OCI + Apptainer (HPC) | 跨平台标准 |
| 测试基准 | xarray.testing + pytest-regressions + numerical-fixtures | 数值回归健全 |

---

## 7. 验证 / 基准 套件 (强制 CI)

| 套件 | 目的 | 通过标准 |
|---|---|---|
| **MMS** Method of Manufactured Solutions (1D/2D/3D) | 收敛阶 | 二阶网格收敛 |
| **Toro Riemann** (1D SWE) | 激波/稀疏波 | L1 误差 < 0.5% (N=1000) |
| **Thacker 抛物碗** (2D) | 干湿 + 守恒 | 周期内质量守恒 < 1e-10 |
| **Lemhi River** (USGS) | 与 River2D 对照 | 流速 RMSE < 10% |
| **Boscastle 2004** (UK) | 真实洪水 | 与观测洪水边界 IoU > 0.9 |
| **PHABSIM 标准例** (Bovee 1997) | WUA-Q 曲线 | 曲线形状一致, 峰值流量 ±5% |
| **FishXing 涵洞例** | 通过性 | 临界流量 ±2% |
| **InSTREAM Lemhi** | IBM 长期模拟 | 种群轨迹定性一致 |

每次 PR 必跑前 5 项, 每周跑全套, 结果写入公开 dashboard。

---

## 8. API 草案

### 8.1 Python API (面向最终用户)

```python
import openlimno as ol

# 1. 加载场地
case = ol.Case.from_yaml("case.yaml")

# 2. 准备网格 (可从多种来源)
mesh = ol.mesh.from_dem("dem.tif", resolution=2.0).refine_at("breaches.geojson")
case.mesh = mesh

# 3. 选择水动力后端 (双轨)
case.hydro = ol.hydro.SWE2D(
    backend="native-gpu",     # 或 "schism", "anuga"
    cfl=0.4,
)

# 4. 栖息地与物种
case.habitat = ol.habitat.WUATime(
    species=["oncorhynchus_mykiss"],
    stages=["spawning", "fry"],
    composite="geometric_mean",
)

# 5. 不确定性
case.ensemble(size=64).perturb(
    "manning_n", dist="lognormal", mu=-2.3, sigma=0.2
)

# 6. 跑
result = case.run(executor="local")    # 或 "slurm", "k8s", "edge"

# 7. 分析
result.wua.plot.line(x="discharge")
result.water_depth.isel(time=-1).hvplot.quadmesh(geo=True)
result.export("output.zarr")
```

### 8.2 CLI

```bash
openlimno validate case.yaml
openlimno run case.yaml --executor slurm --partition gpu
openlimno wua case.yaml --species coho --stage spawning --plot
openlimno passage --culvert culvert.yaml --species rainbow_trout
openlimno calibrate case.yaml --observed gauges.csv --algo pestpp-ies
openlimno uq mc case.yaml --n 100
openlimno reproduce provenance.json
```

### 8.3 REST (云形态)

```
POST /v1/cases                  # 创建 case
GET  /v1/cases/{id}
POST /v1/cases/{id}/runs
GET  /v1/runs/{rid}/status
GET  /v1/runs/{rid}/output      # Arrow Flight ticket 或 Zarr URL
GET  /v1/species
GET  /v1/hsi-curves?species=&stage=
```

### 8.4 BMI (求解器开发者)

求解器作者只需实现 `IBmi` 接口的 25 个方法, 即可被 OpenLimno 调度、耦合、可视化。

---

## 9. 仓库与构建结构

```
openlimno/
├── SPEC.md                         # 本文件
├── docs/                           # MkDocs Material
├── pixi.toml                       # 跨平台环境
├── packages/
│   ├── core/                       # 内核 (语言择优, 暂占位)
│   ├── wedm/                       # 数据模型 schema + 校验
│   ├── hydro-native/               # B 轨自研
│   ├── hydro-schism/               # A 轨包装
│   ├── hydro-anuga/                #
│   ├── hydro-hecras/               #
│   ├── thermal/
│   ├── sediment/
│   ├── habitat/                    # ⭐ 重点
│   ├── passage/
│   ├── ibm/
│   ├── connectivity/
│   ├── coupler/
│   ├── runtime-min/                # 嵌入式瘦身路径
│   ├── ui-web/                     # Tauri + React
│   ├── ui-qgis/                    # QGIS 插件
│   └── cli/
├── workflows/                      # Snakemake/CWL
├── benchmarks/                     # 验证套件
├── examples/                       # 教程数据
└── tools/                          # 数据采集、HSI 学习等小工具
```

---

## 10. 路线图 (重新对齐用户优先级)

> 重点: 栖息地与生态流量 (4.5) 在 M1 就要可用; 包装路径优先, 自研路径并行推进; 四种部署形态从 M1 起就保持构建通过。

| 里程碑 | 时间 | 交付 | 验证 |
|---|---|---|---|
| **M0** | T+1 月 | 仓库骨架, WEDM v0.1 schema, BMI 适配框架, CI 多平台 | schema 校验通过 |
| **M1** | T+4 月 | 1D Saint-Venant (B 轨) + HEC-RAS-1D 包装 (A 轨) + HSI/WUA + WUA-Q 曲线 + 桌面 GUI alpha + runtime-min 雏形 | PHABSIM 标准例 |
| **M2** | T+8 月 | 2D SWE-FV (B 轨, CPU) + ANUGA/SCHISM 包装 + 时序栖息地 + 生态流量产品 + HPC 部署 + 云镜像 | River2D Lemhi 对照, Boscastle |
| **M3** | T+12 月 | 2D GPU 化 + 涵洞过鱼 + 鱼种数据库 + Web GUI beta + 嵌入式实时 demo | FishXing 标准例, 端到端实时 demo |
| **M4** | T+16 月 | 水温 + 泥沙耦合 + UQ (MC/PCE) + 校准框架 (PEST++) + Bayesian HSI | 加州水温遥测对比 |
| **M5** | T+20 月 | NREI 漂移-觅食栖息地 + 数据同化 (EnKF) + ML 代理 (FNO) | 不确定性带可视化 |
| **M6 / 1.0** | T+24 月 | 3D 求解器接入 + IBM/种群 v1 + 拆坝多目标优化 + 治理章程定稿 | InSTREAM 对照 |

---

## 11. 治理与社区

- **许可**: 代码 Apache-2.0, 数据/规格 CC-BY-4.0
- **托管**: GitHub (主) + Gitee 镜像 (中国合规)
- **治理**: 借鉴 NumFOCUS / Apache Way, 设立 PSC (项目指导委员会), 每月公开例会
- **同行评审**: 关键算法发 Geoscientific Model Development 期刊
- **学术互操作**: 与 SCHISM, Delft3D, HEC-RAS 团队建立兼容性测试; 申请加入 NOAA NextGen 框架
- **中文社区**: 设中文文档分站, 与水利部水利信息中心、中科院水生所建立用户组

---

## 12. 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| 数值方法在真实地形上失稳 | 中 | 高 | 双轨, 包装路径作为兜底 |
| 鱼类参数地区差异 (中国 vs 北美) | 高 | 中 | 数据库分区, 用户可贡献 |
| 四种部署形态分散精力 | 高 | 高 | 共享 80% 代码, runtime-min 做为编译选项而非分叉 |
| 生态学家不会用 Python/CLI | 高 | 中 | Web GUI + QGIS 插件 + Excel 模板导入 |
| GPU 移植难度 | 中 | 中 | 用 Kokkos/SYCL 抽象, 不直接绑 CUDA |
| 商业开源软件竞争 (DHI/HEC) | 中 | 中 | 互操作而非对抗, 走开放数据/可重复差异化 |
| 长期维护资金 | 高 | 高 | NSF/科技部专项 + 商业咨询服务双轨 |

---

## 13. 评审请关注

提请评审者重点对以下问题给反馈:

1. **WEDM 是否覆盖了你工作流里的全部数据?** 缺失字段请提 issue
2. **BMI 子集是否够用?** 你常用求解器有哪些没法实现的接口
3. **栖息地评估方法谱系 (4.5.1) 漏了哪种?** 漂移-觅食/Bayesian/Fuzzy 是否值得 v1
4. **双轨水动力策略实际可行吗?** 包装 SCHISM 的工程量评估
5. **runtime-min 子集划分是否合理?** 实时调度场景必备能力是否覆盖
6. **路线图节奏现实吗?** M1 4 个月做 PHABSIM 等价 + 双轨基础设施是否可达

---

## 附录 A. 与现有软件对照

| 功能 | OpenLimno 模块 | FishXing | PHABSIM | River2D |
|---|---|---|---|---|
| 1D 水力 | `hydrodynamics.SaintVenant` | — | ✓ (IFG4/MANSQ) | — |
| 2D 水力 | `hydrodynamics.SWE2D` | — | — | ✓ |
| 涵洞水力 | `passage.Culvert` | ✓ | — | — |
| HSI 曲线 | `habitat.HSICurve` | — | ✓ | ✓ |
| WUA-Q | `habitat.WUAQ` | — | ✓ | ✓ |
| WUA-time | `habitat.WUATime` | — | — | — |
| 鱼类游泳 | `passage.SwimmingModel` | ✓ | — | — |
| 概率通过性 | `passage.MonteCarlo` | — | — | — |
| 时变栖息地 | `habitat.PersistentHabitat` | — | — | — |
| Bayesian HSI | `habitat.BayesianHSI` | — | — | — |
| 漂移觅食 | `habitat.NREI` | — | — | — |
| 不确定性 | `workflows.uq.*` | — | — | — |
| 数据同化 | `workflows.da.*` | — | — | — |
| 气候情景 | `workflows.scenario_cmip6` | — | — | — |
| GPU | 全模块 | — | — | — |
| 云原生 | `deploy.k8s` | — | — | — |
| 嵌入式 | `runtime-min` | — | — | — |

---

## 附录 B. 参考文献骨架 (待补完)

- Bovee, K.D. (1986) IFIM stream habitat analysis
- Stalnaker et al. (1995) PHABSIM Reference Manual
- Steffler & Blackburn (2002) River2D Technical Manual
- FHWA HY-8 Culvert Hydraulic Analysis Program
- USFS FishXing Documentation
- Hipsey et al. (2019) AED2 water quality
- Hayes et al. (2007) NREI drift-feeding model
- Hatten et al. (2014) Bayesian HSI
- Audusse et al. (2004) Well-balanced SWE
- Bollermann et al. (2011) Dry-bed treatment
- Casulli (2009) Subgrid bathymetry

---

*— 本规格为草案, 任何条款在 1.0 发布前可被推翻。社区 issue/PR 是更新唯一通道。*
