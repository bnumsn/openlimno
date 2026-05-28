# OpenLimno Fishtank — 鱼缸生态模型 + 教学包

`openlimno.fishtank` 是一个**封闭淡水鱼缸 (microcosm) 的机理 ODE 模型**,
同时是一门 **4 学时硕士"水生态模型"课程**的完整载体 —— 带学生走完
"概念化 → 数学化 → 实现 → 校验 → 应用 → 发布"全过程。

## 这是什么

- **开源产品**:hobby 用户可装可用的氮循环 / pH 模拟器
- **教学包**:4 学时实验课,学生亲手把一个真实生态系统建成可发布的软件

模型核心:双 Monod 硝化(TAN→NO₂→NO₃)+ 附着生物膜 + 溶解氧平衡,
可选 Tier-2 碳酸盐/pH。科学经 2 轮 codex 复审验证(见 `../../reviews/`)。

## 快速上手

```bash
pip install -e .              # 在 repo 根目录
python -c "from openlimno.fishtank import simulate, Chemistry, Params; \
           r = simulate(Chemistry(), Params(), days=42); \
           print(r.timeseries[['day','TAN','NO2','NO3']].iloc[::28])"
```

经典 fishless cycle:氨峰(~day 7)→ 亚硝峰(~day 15,滞后)→ 硝酸盐累积,
整体跨 **3-4 周**。

## 文档地图

| 文件 | 用途 |
|---|---|
| [`SPEC.md`](./SPEC.md) | 技术规范:状态向量、ODE 系统、过程方程、参数表、模块契约 |
| [`COURSE_PLAN.md`](./COURSE_PLAN.md) | 4 学时分钟级教案(每节课时间表 + 板书 + 代码片段) |
| [`INSTRUCTOR_GUIDE.md`](./INSTRUCTOR_GUIDE.md) | 导师备课:易错点、提问脚本、应急预案、评估 |
| [`OPENSOURCE_GUIDE.md`](./OPENSOURCE_GUIDE.md) | 学生 fork/PR 异步教程(课程作业) |
| [`notebooks/`](./notebooks/) | 4 节课的 Jupyter notebook(实跑验证) |
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
| `library.py` | core | 物种/设备参数库 |
| `studio.py` | release | Streamlit UI + matplotlib 绘图 |

## 4 学时一览

1. **问题与数学** — 概念图 + ODE 推导 + Monod + 手写欧拉
2. **实现** — `simulate()` 跑出 spike-and-fall
3. **校验与校准** — 换水事件 + 拟合恢复真值
4. **应用与发布** — pH 模块 + Streamlit + 开源流程

## 跑测试

```bash
pytest tests/unit/test_fishtank_tier1.py tests/unit/test_studio_instream7_default_core.py
```

## 与 OpenLimno 主项目的关系

fishtank 是 OpenLimno 的 **microcosm 尺度切片**,与主项目的 macrocosm
(河流/湖泊/IBM)形成方法论对照:同样的"状态→过程→求解→校验→应用"骨架,
只是尺度从 km 级降到 120 L、从 GIS 网格降到单格、从个体模型降到 ODE。
fishtank 是把这套方法论教给学生的**最小可教学切片**。
