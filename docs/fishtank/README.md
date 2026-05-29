# OpenLimno Fishtank — 封闭鱼缸生态机理模型

`openlimno.fishtank` 是一个**封闭淡水鱼缸 (microcosm) 的机理 ODE + ABM 模型**:
模拟氮循环(TAN→NO₂→NO₃)、附着生物膜定殖、溶解氧与(可选)碳酸盐/pH 动态,
并提供本地浏览器 Studio(3D 虚拟鱼缸 + 时序/校准面板)。

## 这是什么

模型核心:双 Monod 硝化(TAN→NO₂→NO₃)+ 附着生物膜 + 溶解氧平衡,
并提供鱼个体 + AOB/NOB 生物膜斑块的 agent-based model。可选 Tier-2
碳酸盐/pH 诊断。技术规范见 [`SPEC.md`](./SPEC.md)。

## 快速上手

```bash
pip install -e ".[fishtank]"          # 在 repo 根目录
python -m openlimno.fishtank run examples/fishless_cycle.yaml
# 或: openlimno fishtank run examples/fishless_cycle.yaml
```

经典 fishless cycle:氨峰(~day 7)→ 亚硝峰(~day 15,滞后)→ 硝酸盐累积,
整体跨 **3-4 周**。

`run` 输出四个产物:`timeseries.csv` / `events_log.csv` / `warnings.json` /
`provenance.json`(参数指纹、版本、摘要)。浏览器 Studio:

```bash
python -m openlimno.fishtank studio   # http://127.0.0.1:8768
```

## 典型场景库

每个典型情形都附一个**对 ODE 与 ABM 两个面板都自洽**的现成案例
(`examples/fishtank/*.yaml`,亦由 `library.scenarios()` 提供,Studio 顶部
"Preset" 下拉可一键加载)。关键约束:无鱼循环的氨峰本身致命,所以有鱼场景
用 `feed` 事件驱动氮源(ODE 折算等效剂量、ABM 按存活鱼比例排泄),要存活的
养鱼缸则从已建立的生物膜起步。

| 场景 | 现象 |
|---|---|
| `fishless_cycle`(默认) | 经典级联:氨→亚硝→硝酸盐,无鱼受险 |
| `seeded_instant_cycle` | 引入成熟滤材 → 氨峰被压制(快速跑缸) |
| `fish_in_disaster` | 未跑缸就放 10 条鱼重投喂 → 游离氨中毒、多数鱼死 |
| `mature_stocked_tank` | 成熟滤材 + 适度投喂 + 周期换水 → 全员存活、pH 稳 |
| `old_tank_syndrome` | 重负荷低碱度 60 天 → 碳酸盐缓冲耗尽、pH 崩 |

```bash
python -m openlimno.fishtank run examples/fishtank/mature_stocked_tank.yaml
```

## 代码模块(`src/openlimno/fishtank/`)

| 模块 | 内容 |
|---|---|
| `state.py` | Chemistry/Params dataclass + NH₃ pKa(T) |
| `processes.py` | monod / oxidation_fluxes / **derivatives**(模型心脏) |
| `solver.py` | solve_ivp + 事件分段 |
| `events.py` | 换水/投喂/加药 + repeat_days |
| `calibration.py` | align / rmse / fit |
| `carbonate.py` | Tier-2 pH(brentq)+ 诊断 pH 崩 |
| `agent.py` | agent-based model:鱼个体 + AOB/NOB 生物膜斑块 |
| `library.py` | 物种/设备参数库 + 典型场景库 `scenarios()` |
| `io.py` | scenario YAML / observations / reproducible outputs |
| `cli.py` | `run` / `validate` / `calibrate` / `studio` |
| `studio.py` / `studio_http.py` | 本地浏览器 Studio + ABM Agents 页 + 3D 虚拟鱼缸 + matplotlib 绘图 |
| `vendor/` | Three.js 运行时与 MIT license,用于离线 3D 虚拟鱼缸 |

## 跑测试

```bash
pytest tests/unit/test_fishtank_tier1.py
ruff check src/openlimno/fishtank tests/unit/test_fishtank_tier1.py
```

## 与 OpenLimno 主项目的关系

fishtank 是 OpenLimno 的 **microcosm 尺度切片**,与主项目的 macrocosm
(河流/湖泊/IBM)形成方法论对照:同样的"状态→过程→求解→校验→应用"骨架,
尺度从 km 级降到 120 L;同一个场景既能用单格 ODE 跑,也能用鱼个体 +
生物膜 patch 的 ABM 跑。
