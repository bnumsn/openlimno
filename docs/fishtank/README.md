# OpenLimno Fishtank — 鱼缸生态模型 + 教学包

`openlimno.fishtank` 是一个**封闭淡水鱼缸 (microcosm) 的机理 ODE + ABM 模型**,
同时是一门 **4 学时硕士"水生态模型"课程**的完整载体 —— 带学生走完
"概念化 → 数学化 → 实现 → 校验 → 应用 → 发布"全过程。

## 这是什么

- **开源产品**:hobby 用户可装可用的氮循环 / pH 模拟器
- **教学包**:4 学时实验课,学生亲手把一个真实生态系统建成可发布的软件

模型核心:双 Monod 硝化(TAN→NO₂→NO₃)+ 附着生物膜 + 溶解氧平衡,
并提供鱼个体 + AOB/NOB 生物膜斑块的 agent-based model。可选 Tier-2
碳酸盐/pH。科学经 2 轮 codex 复审验证(见 `../../reviews/`)。

## 快速上手

```bash
pip install -e .              # 在 repo 根目录
python -m openlimno.fishtank run examples/fishless_cycle.yaml
# 或: openlimno fishtank run examples/fishless_cycle.yaml
```

经典 fishless cycle:氨峰(~day 7)→ 亚硝峰(~day 15,滞后)→ 硝酸盐累积,
整体跨 **3-4 周**。

## 典型场景库

每个典型情形都附一个**对 ODE 与 ABM 两个面板都自洽**的现成案例
(`examples/fishtank/*.yaml`,亦由 `library.scenarios()` 提供,Studio 顶部
"Preset" 下拉可一键加载)。关键约束:无鱼循环的氨峰本身致命,所以有鱼场景
用 `feed` 事件驱动氮源(ODE 折算等效剂量、ABM 按存活鱼比例排泄),要存活的
养鱼缸则从已建立的生物膜起步。

| 场景 | 教学点 |
|---|---|
| `fishless_cycle`(默认) | 经典级联:氨→亚硝→硝酸盐,无鱼受险 |
| `seeded_instant_cycle` | 引入成熟滤材 → 氨峰被压制(快速跑缸) |
| `fish_in_disaster` | 未跑缸就放 10 条鱼重投喂 → 游离氨中毒、多数鱼死(反面教材) |
| `mature_stocked_tank` | 成熟滤材 + 适度投喂 + 周期换水 → 全员存活、pH 稳 |
| `old_tank_syndrome` | 重负荷低碱度 60 天 → 碳酸盐缓冲耗尽、pH 崩(Hour-4 capstone) |

```bash
python -m openlimno.fishtank run examples/fishtank/mature_stocked_tank.yaml
```

## 文档地图

| 文件 | 用途 |
|---|---|
| [`SPEC.md`](./SPEC.md) | 技术规范:状态向量、ODE 系统、过程方程、参数表、模块契约 |
| [`COURSE_PLAN.md`](./COURSE_PLAN.md) | 4 学时分钟级教案(每节课时间表 + 板书 + 代码片段) |
| [`INSTRUCTOR_GUIDE.md`](./INSTRUCTOR_GUIDE.md) | 导师备课:易错点、提问脚本、应急预案、评估 |
| [`OPENSOURCE_GUIDE.md`](./OPENSOURCE_GUIDE.md) | 学生 fork/PR 异步教程(课程作业) |
| [`notebooks/`](./notebooks/) | 两条轨道:01–04 导读演示 + **`build_along_student.ipynb` 从零搭建**(学生填 5 个 TODO 写出科学核心)+ 答案钥匙 |
| [`exercises/`](./exercises/) | 课后练习 + 参考解答 |

## 代码模块(`src/openlimno/fishtank/`)

| 模块 | 标签 | 内容 |
|---|---|---|
| `state.py` | core | Chemistry/Params dataclass + NH₃ pKa(T) |
| `processes.py` | core | monod / oxidation_fluxes / **derivatives**(模型心脏) |
| `solver.py` | core | solve_ivp + 事件分段 |
| `events.py` | core | 换水/投喂/加药 + repeat_days |
| `calibration.py` | core | align / rmse / fit |
| `carbonate.py` | core | Tier-2 pH(brentq)+ 诊断 pH 崩 |
| `agent.py` | core | agent-based model:鱼个体 + AOB/NOB 生物膜斑块 |
| `library.py` | core | 物种/设备参数库 + 典型场景库 `scenarios()` |
| `io.py` | release | scenario YAML / observations / reproducible outputs |
| `cli.py` | release | `run` / `validate` / `calibrate` / `studio` |
| `studio.py` / `studio_http.py` | release | 本地浏览器 Studio + ABM Agents 页 + 3D 虚拟鱼缸 + matplotlib 绘图 |
| `vendor/` | release | Three.js 运行时与 MIT license,用于离线 3D 虚拟鱼缸 |

## 4 学时一览

1. **问题与数学** — 概念图 + ODE 推导 + Monod + 手写欧拉
2. **实现** — `simulate()` 跑出 spike-and-fall
3. **校验与校准** — 换水事件 + 拟合恢复真值
4. **应用与发布** — pH 模块 + ABM/3D 浏览器 Studio + 开源流程

## 跑测试

```bash
pytest tests/unit/test_fishtank_tier1.py
ruff check src/openlimno/fishtank tests/unit/test_fishtank_tier1.py
```

## 与 OpenLimno 主项目的关系

fishtank 是 OpenLimno 的 **microcosm 尺度切片**,与主项目的 macrocosm
(河流/湖泊/IBM)形成方法论对照:同样的"状态→过程→求解→校验→应用"骨架,
尺度从 km 级降到 120 L；同一个场景既能用单格 ODE 跑,也能用鱼个体 +
生物膜 patch 的 ABM 跑。fishtank 是把这套方法论教给学生的**最小可教学切片**。
