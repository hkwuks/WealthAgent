# 因子功能前端上线设计（FACTOR-UI v0.1）

> 日期: 2026-11-21 · 状态: 待评审
> 前提: 引擎层已通（`scripts/verify_factor_engine.py` 全绿），本次只解决「人能看到、且看到的不是假的」
> 约束: 不新建面板，不重写引擎；按现有前端分区落位

---

## 1. 结论先行

因子引擎在前端有且只有一个落点：**基金量化 Tab → 研究区 → 因子暴露**。

那个面板已经存在（`frontend/src/fundQuant/panels/FactorExposure.ts`），也已经接上了接口。但它现在展示的内容**有三处是编的**：

| 展示项 | 现在怎么来的 | 真不真 |
|---|---|---|
| 因子值 | `Factor.compute()` 真实计算 | ✅ 真 |
| 同类百分位 `rank_pct` | `value * 100` 截断到 5~95 | ❌ 假，和"同类"无关 |
| 权重 | 按 category 分配，但 28 个因子同属 `technical` | ❌ 全是 3.57%，无信息 |
| 历史因子暴露变化（近1年） | 拿当前值画一根柱 | ❌ 完全没有历史 |
| 雷达图 | 28 个轴 | ⚠️ 真，但读不出东西 |
| `n_funds_in_category` | `max(50, n*5)` 硬编码 | ❌ 假 |

所以「前端上线」的实质不是加功能，是**把三个谎言换成真话，并补两个必需的接口契约**。

---

## 2. 现状盘点：前端 12 个分区，因子只在 1 个

| 分区 | 面板 | 现在显示什么 | 与因子的关系 |
|---|---|---|---|
| 组合概览 | `KPIBar` | `/portfolio/status` | 无关 |
| 净值走势 | `NavChart` | `/nav/{code}` | 无关 |
| 信号列表 | `SignalList` | `/signal/latest`，库里 0 条 | 无关 |
| 组合配置 | `Allocation` | `/allocation/optimize` | 无关 |
| **选基排名** | `FundRanking` | `/selection/screen` | **同一个因子引擎** |
| 归因分析 | `Attribution` | `/attribution/brinson` | 无关 |
| 月度收益 | `MonthlyReturns` | `/portfolio/monthly-returns` | 无关 |
| 基金详情 | `DetailPanel` | 静态 + 有「打开因子暴露」按钮 | 入口 |
| 回测 | `BacktestPanel` | `/backtest/run` | 无关 |
| 参数扫描 | `ParamScanPanel` | `/backtest/param-scan` | 无关 |
| 模拟交易 | `PaperTradePanel` | `/paper-trade/*` | 无关 |
| **研究区 > 因子暴露** | `FactorExposure` | `/factors/exposure/{code}` | **主战场** |

只改 `FactorExposure` 一处，就能覆盖因子的全部可视化。`FundRanking` 是第二处，因为它在用同一套因子但走了一条**并行实现**（见 D5）。

---

## 3. 三类断点

### 3.1 数据断（阻塞一切，优先级最高）

前端所有面板都从 `state.fundPool` 拿基金。`fundPool` 来自 `/api/funds`，该接口读 `data/backend/funds.json`。实测：

```
data/backend/funds.json  →  JSON 解析失败（尾部多了 " []\n  }\n]"），接口静默返回 []
worktree 里这个文件根本不存在 → 返回 []
```

**后果**：`fundPool` 为空 → 选基金下拉框空 → 研究区永远无法打开 → 因子面板哪怕算得再对也没人看得见。

净值数据同样如此：`nav_history` 表只有 1 只基金（`510300`，500 行，是我自检时注入的）。用户自己的 27 只基金一条都没有。

实测这 27 只里 **23 只可从东财拉到净值**，4 只拉不到（`968040/968041/968048/968067`，香港互认基金，东财无数据，不可解）。

### 3.2 契约断（改一行就能通）

| 断点 | 位置 | 后果 |
|---|---|---|
| `load_all()` 只在暴露接口里调 | `backend/api/fund_quant.py:881` | `/factors/list` 返回 0 个因子，量化引擎 Tab 的「已注册因子」显示 0 |
| `NavFeed.get_factor_input()` 忽略 `as_of` | `backend/fund_quant/factors/nav_feed.py:27` | 任何"回看历史某天"的调用都拿到**最新**一段。不修就无法画真历史，且一画就是前视偏差 |
| `info_ratio` 因子 `FrozenInstanceError` | 因子内部改 `meta.params`，而 `FactorMeta` 是 frozen | 暴露接口里显示「计算失败: FrozenInstanceError」 |

### 3.3 假数据（面试官一眼看穿）

见 §1 表格。核心三处：`rank_pct`、`weight`、历史图。

---

## 4. 修复设计

### D1 恢复数据通路 —— 否则前端是空壳

| 项 | 做法 |
|---|---|
| `funds.json` | 从主仓库那份里截掉尾部垃圾，得到 27 只合法记录，写进 worktree。**不动主仓库的文件** |
| 净值入库 | 调已有的 `POST /data/collect`，对 27 只基金逐个拉 5 年净值，落 `nav_history` |
| 拉不到的 4 只 | 记录在案，接口对它们返回「数据不足」而不是报错 |

验收：
- `GET /api/funds` 返回 27 条
- `SELECT count(DISTINCT fund_code) FROM nav_history` ≥ 23
- 打开基金量化 Tab，净值走势面板有图

### D2 `NavFeed` 支持 `as_of` —— 一处改动，两个消费方受益

```python
def get_factor_input(self, symbols, as_of, lookback):
    # 按 as_of 二分截断，取截至该日的最后 lookback 根
    i = bisect.bisect_right(self._dates, str(as_of))
    return self._values[max(0, i - lookback):i]
```

`NavFeed` 现在只存 `{symbol: list[float]}`，需要同时存日期轴。构造时一并传入（`feed_from_storage` 已经有 `date` 字段可用）。

验收：`scripts/verify_factor_engine.py` 新增一条断言 —— 同一序列，`as_of=今天` 与 `as_of=半年前` 的 `tech_roc_20` 必须不同。

### D3 真·同类百分位 —— 只对能比的池子算

**发现**：用户 27 只基金分散在 11 个 `fund_type` 里，每类 1~3 只，横截面分位没有统计意义。

因此只在**有可比池**时算，否则诚实地返回 `null`：

| 代码类型 | 比较池 | 分位是否计算 |
|---|---|---|
| ETF（`data/etf_pool.json` 里的 120 只） | 同类别（宽基/行业/跨境/商品/债券）内 | ✅ 算 |
| 场外基金 | 同 `fund_type` 且成员 ≥ 5 | ✅ 算 |
| 其余 | — | ❌ 返回 `null`，前端隐藏该列 |

实现：暴露接口加一个可选的池内批量计算（实测 28 因子 × 120 标的 = 0.41s，可接受，且可 `lru_cache` 按 `(池, 日期)` 缓存）。

验收：同一天同一个池子里，某因子的 `rank_pct` 分布应接近均匀，且极值不超过 0/100。

### D4 权重与方向用研究结论，不用直觉

已有产物 `reports/factor_rolling_ic.json`（36 月窗口、12 月步长、9 个窗口）：
存活 10 个，淘汰 12 个（`std` 全族、`rank` 全族、`skew` 全族、`roc_60`）。

设计：

- **方向**：`technical.py` 里 9 个因子的 `direction` 按数据改（`ma_gap_10/20`、`max_gap_10/20` → +1；`roc_5` → −1 等）。这是研究已经跑出来的结论，不是新判断。
- **权重**：`w_i ∝ max(|recent_ic_i|, 0)`，淘汰的因子权重为 0；全为 0 时退化为等权。
- **不再硬编码 category 权重表**（28 个因子同属一类，那张表没有区分度）。

验收：暴露接口返回的权重里，至少有一个为 0（淘汰因子），且权重和 = 1。

### D5 删掉 `_compute_factor_simple`，走同一个引擎

`backend/fund_quant/strategy/selection/multi_factor.py:196` 有一份**平行的**因子实现，只认 10 个硬编码因子名。一旦 28 个 `tech_*` 注册进 Registry，它对每个都 `return 0.0`，导致选基排名全 0。

这正是「不要自己再重复写轮子」。做法：删掉 `_compute_factor_simple`，改为

```python
feed = NavFeed({code: nav_values})
val = FactorRegistry.get(name)().compute([code], as_of, lookback, feed).get(code)
```

验收：选基排名面板的总分不再是全 0.0000，且与因子暴露面板对同一基金同一因子给出一致的原始值。

### D6 前端 3 处显示改造（只改 `FactorExposure.ts`）

| 改什么 | 怎么改 |
|---|---|
| 雷达图 28 轴 → 7 轴 | 按算子聚合（同算子 4 个窗口取均值），轴标签用中文名（收益率/均线偏离/波动率/距高点/RSV/涨幅分位/收益偏度） |
| 历史图换成真图 | 调新接口拿 12 个月末的因子快照，画真正的折线；拿不到历史就整块隐藏，**不再用当前值画假柱** |
| 百分位列为空时隐藏 | `rank_pct === null` 时整个 `<th>`/`<td>` 不渲染 |
| 权重为 0 的因子 | 表格里灰显，标「已淘汰」 |

另外补 `fx-*` 的 CSS（现有代码里用到 `fx-radar-chart`/`fx-tbody`/`fx-history-chart`，`style.css` 里 **0 条**匹配）。

### D7 小修

`info_ratio` 等因子改 `meta` 的地方换成 `dataclasses.replace()` 或直接不改（`FactorMeta` 是 frozen 是设计意图，不该绕过）。

---

## 5. 明确不做

| 不做 | 理由 |
|---|---|
| 新建因子面板 | 现有研究区够用，多一个面板就是多一处要维护的假数据 |
| 做因子 IC 热力图 | 结论已在 `reports/`，前端再画一遍是重复 |
| 把 VOL-001 做成卖出信号 | 那是 P2，属策略层，不属于「前端上线」 |
| 修 `fund_ranking` 默认隐藏问题 | 规划层面的事，不是 bug |
| 补 4 只香港互认基金的净值 | 东财无数据，实测确认不可解 |
| 兼容旧接口返回结构 | 现有前端已按新结构解析，不需要 |

---

## 6. 实施顺序与工作量

按依赖排序，每步都可独立验收：

| 序 | 任务 | 依赖 | 估时 | 卡住什么 |
|---|---|---|---|---|
| 1 | D1 数据通路（funds.json + 净值入库） | 无 | 20 分钟 | 一切 |
| 2 | D2 `NavFeed` 支持 `as_of` | 无 | 15 分钟 | D6 的历史图 |
| 3 | D7 `FrozenInstanceError` | 无 | 5 分钟 | — |
| 4 | D4 方向 + 权重 | 无 | 20 分钟 | D3 的分位无意义 |
| 5 | D3 真百分位 | 1, 4 | 40 分钟 | — |
| 6 | D5 删并行实现 | 2 | 30 分钟 | 选基排名 |
| 7 | D6 前端 3 处 + CSS | 2, 3, 5 | 60 分钟 | 上线 |
| 8 | 端到端验证脚本 | 全部 | 20 分钟 | — |

**总计约 3.5 小时**，其中第 1 步不完成的话后面全部是纸上作业。

---

## 7. 需要你决策的 3 个问题

### Q1. 数据修复要不要碰主仓库？

`funds.json` 只在主仓库 `/mnt/f/WorkSpace/PyCharm/基金估值/data/backend/` 存在且尾部损坏，worktree 里没有。

- **A（推荐）**：读主仓库那份、截掉尾部垃圾、写一份到 worktree。主仓库一个字节不动。
- **B**：你在主仓库里自己修，我这边只等文件出现。

### Q2. 百分位算不出来时，怎么显示更好？

用户 27 只基金分散在 11 个类型里，大部分类型只有 1~2 只成员。

- **A（推荐）**：能算的（ETF 池内）显示真实百分位，不能算的**整列隐藏**。
- **B**：一律显示，不能算的填 50%，并在表头标注「估算」。
- **C**：干脆去掉这一列，只留因子值和权重。

### Q3. 权重口径用哪个？

- **A（推荐）**：滚动 IC 加权（存活因子按 |recent_ic| 分权，淘汰因子 0 权重），与研究结论一致。
- **B**：等权 28 个因子。简单，但把已证明无效的 12 个因子也算进去。
- **C**：只用存活的 10 个因子，等权。

---

## 附：本次调查的关键证据

```
# 因子引擎本身没问题（28 因子 × 120 标的 = 0.41s）
✔ 注册 28 个因子，分类: {'technical': 28}
✔ 归一化映射正确（6 个用例）
✔ compute 通过 28 个
✔ 暴露接口返回 28 个因子，权重和 0.9996，总分 0.3101

# 但数据层是空的
nav_history: 1 个代码 / 500 行（510300，自检注入）
fund_metadata: 0 行
signals: 0 行

# /api/funds 因为 JSON 尾部损坏返回 0 条
# funds.json 前 4010 字节可以正常解析出 27 只基金

# 用户 27 只基金净值可拉取性
OK 23/27；失败 4 只（968040/968041/968048/968067，香港互认，东财无数据）

# 目录里的读法（27 只的 fund_type 分布）
ETF 基金 / QDII-普通股票 / 债券型-混合一级 / 债券型-混合二级 /
指数型-其他 / 指数型-固收 / 指数型-海外股票 / 指数型-股票 /
海外混合 / 混合型-偏债 / 混合型-偏股
```
