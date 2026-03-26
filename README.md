[**English**](README_EN.md) | **中文**

# ⚖️ Apex Quant

### 基于对抗性多智能体辩论的量化分析框架

[![License: CC BY-NC-SA 4.0](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc-sa/4.0/)
[![Paper](https://img.shields.io/badge/Paper-SSRN%206354961-blue)](https://papers.ssrn.com/abstract=6354961)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)

---

Apex Quant 是一个基于大语言模型的多智能体量化分析框架，核心机制是三个持有对立立场的 Agent 在做出任何决策之前，先完成结构化辩论。框架本身与市场无关，当前实现以美股为主，因为免费数据源最丰富。

项目起初是为了给自己和朋友们做一个美股分析看板，从2025年10月开始开发，演化出了现在这套三角辩论架构。伴随论文一起开源。

---

## 🏛️ 核心架构：三角圆桌辩论

大多数多智能体交易框架把不同的 Agent 分配给不同的**数据类型**（基本面、情绪、技术面）。Apex Quant 的不同在于：把 Agent 分配给不同的**立场**。

![triangle](images/triangle.png)

三个 Agent 各自持有固定的投资哲学，在任何决策输出之前，必须先完成结构化辩论：

- 🔴 **Zealot**（狂热者）— 永远在找做多理由，构建最强的买入论据，绝不轻易出局
- 🔵 **Reaper**（收割者）— 不是空头，是现实主义者：当前风险值不值得继续持有？
- ⚖️ **Fulcrum**（支点）— 系统的阻尼器。默认立场是 HOLD，任何激进操作都需要同时突破另外两个 Agent 的阻力。不依赖历史数据平滑，不依赖多次采样取平均——决策的稳定性直接从结构中来。

**关键设计洞察：** 乐观者的镜像不是悲观者，而是止盈者。Reaper 问的不是"会不会跌"，而是"还值不值得拿"。

---

## 🔄 辩论流程

![flowchart](images/flowchart.png)

**Stage 1 — 独立初始化：** 三个 Agent 同时收到相同的原始数据，各自独立形成判断，互不通信。

**Stage 2 — 自由辩论：** 看到彼此的初始判断后展开多轮辩论。辩论宪法规定每轮必须引入新论据或新角度——重复己方立场不算有效论证，修辞强度不等于论证强度。

**Stage 3 — 报告与签名：** Fulcrum 撰写最终报告，输出可执行指令（BUY/SELL/HOLD + 仓位大小 + 入场/止损条件）；Zealot 和 Reaper 各附少数派签名，记录异议——风险偏好不同的使用者可以自行参考。

---

## 📜 辩论宪法

三个 Agent 的系统提示里都内置了一套辩论规则，防止辩论退化成无效循环：

- **举证负担不对称：** 立场越偏离另外两方，需要反驳的论点越多；无法反驳则立场自动向对方收敛
- **贝叶斯强制更新：** 对方提出有效新证据时，必须调整自己的行动参数，不能只靠修辞抵抗
- **信息增量要求：** 每轮必须带来新内容，已充分讨论过的争议点视为已定价，边际说服力递减
- **争议搁置机制：** 双方均无新证据时，必须显式声明搁置该争议，开辟新的论证方向

---

## 📸 系统界面

![dashboard](images/dashboard.png) ![debate](images/debate.png)

裁决页面显示最终决策、仓位建议与风险控制参数；辩论页面可查看三个 Agent 的完整论证链。

每个决策周期的输入涵盖多时间尺度量化数据、个股新闻、公司基本面与宏观经济指标。

<details>
<summary>量化数据截图（四时间尺度）</summary>

![technical1](images/technical1.png)
![technical2](images/technical2.png)
![technical3](images/technical3.png)
![technical4](images/technical4.png)

</details>

---

## 📄 论文

> **Apex Quant: A Multi-Agent Debate Framework for Quantitative Trading**
> Shuting Sun · SSRN Technical Report · March 2026
> [→ https://papers.ssrn.com/abstract=6354961](https://papers.ssrn.com/abstract=6354961)

```bibtex
@techreport{sun2026apexquant,
  title  = {Apex Quant: A Multi-Agent Debate Framework for Quantitative Trading},
  author = {Sun, Shuting},
  year   = {2026},
  url    = {https://papers.ssrn.com/abstract=6354961}
}
```

---

## 📊 数据源

每个决策周期的输入由以下数据源组成：

| 数据类型 | 来源 | 说明 |
|---------|------|------|
| 股价 & 股指行情 | **Interactive Brokers (IBKR)** | 多时间尺度 K 线（1min / 5min / 1h / 1d），经 `technical_snapshot_builder` 计算技术指标，经 `trend_analyzer` 提取简化趋势线 |
| 宏观经济指标 | **Alpha Vantage** | 联邦基金利率、CPI、失业率、GDP、国债收益率等 |
| 公司基本面 | **Alpha Vantage / Finnhub** | 财报、估值指标 |
| 市场新闻 | **Finnhub** | 个股新闻 + 大盘新闻 |
| 恐惧贪婪指数 | **CNN Fear & Greed Index** | 市场情绪指标 |

> **注意：** IBKR 行情需要盈透证券账户和 TWS/IB Gateway；Alpha Vantage 和 Finnhub 提供免费 API（有调用频率限制）。

---

## 🗂️ 示例数据

`data/examples/` 目录包含 2026 年 3 月 23 日 GENERAL（大盘）分析周期的部分核心数据，展示系统主要的输入输出长什么样。

```
data/examples/
├── debate/       GENERAL_Analysis_20260323T134100Z.json   # 辩论结果（三方论证链 + 最终裁决）
├── economic/     economic_indicators_20260323T100524Z.json # 宏观经济指标
├── fear_greed/   fear_greed_latest_20260323T000000Z.json   # 恐惧贪婪指数 + VIX
├── technical/    SPX_technical_20260323T134100Z.json       # SPX 多时间尺度技术分析快照
└── market_data/  SPX_5y_1d_20260323T000000Z.csv            # SPX 5年日线行情
                  SPX_7d_5m_20260323T134000Z.csv            # SPX 7天5分钟线行情
```

<details>
<summary><b>辩论结果摘要 (点击展开)</b></summary>

```json
{
  "action": 40,
  "operation_type": "TRIM_POSITION",
  "operation_volume": "PILOT_SIZE",
  "debate_summary_en": "The debate evolved from a 'false consensus' to 'rational convergence.' Initially all three parties proposed action=65 for buying, but Reaper revealed that the geopolitical conflict had escalated to an L1-level supply chain shock and highlighted the lack of volume confirmation. Fulcrum shifted to neutral (action=50), Zealot eventually acknowledged L1 shocks invalidated his assumption. Final consensus converged on a defensive stance: action=40, TRIM_POSITION/PILOT_SIZE.",
  "reasoning": {
    "key_drivers": [
      {"direction": "bearish", "category": "macro", "factor_en": "Geopolitical conflict escalated to L1 supply chain shock"},
      {"direction": "bearish", "category": "technical", "factor_en": "Technical rebound lacks volume confirmation"}
    ]
  }
}
```

</details>

<details>
<summary><b>宏观经济指标 (点击展开)</b></summary>

```json
{
  "indicators": {
    "federal_funds_rate": {"value": 3.64, "date": "2026-02-01", "unit": "%"},
    "cpi":                {"value": 326.785, "date": "2026-02-01", "unit": "Index"},
    "unemployment":       {"value": 4.4, "date": "2026-02-01", "unit": "%"},
    "real_gdp":           {"value": 6125.904, "date": "2025-10-01", "unit": "Billions of Dollars"},
    "treasury_10y":       {"value": 4.13, "date": "2026-02-01", "unit": "%"},
    "treasury_2y":        {"value": 3.47, "date": "2026-02-01", "unit": "%"}
  }
}
```

</details>

<details>
<summary><b>恐惧贪婪指数 (点击展开)</b></summary>

```json
{
  "fear_greed": {"value": 12, "previous_close": 14, "one_week_ago": 21, "one_month_ago": 36},
  "vix": {"value": 30.3, "change_percent": 13.14}
}
```

</details>

<details>
<summary><b>技术分析快照 — 部分字段 (点击展开)</b></summary>

```json
{
  "symbol": "SPX",
  "minute_level_features": {
    "last_close": 6608.29,
    "rsi_14_5min": 77.87,
    "atr_14_5min": 15.12,
    "liquidity_score_vol_per_bar": 0.0
  },
  "hourly_features": {
    "ma_20_hourly_val": 6590.25,
    "ma_50_hourly_val": 6652.50,
    "rsi_14_hourly": 50.59,
    "macd_hist_hourly": 0.556,
    "bb_pct_b_hourly": 0.59
  }
}
```

</details>

---

## ⚡ 快速上手

### 1. 安装依赖

```bash
git clone https://github.com/sst19910323/apex_parliament.git
cd apex_parliament
pip install -r requirements.txt
```

### 2. 配置 API Key

编辑 `config/models.yaml`，将 LLM 的 API Key 填入对应模型配置：

```yaml
models:
  qwen3.5-plus:
    api_key: "your_dashscope_api_key"   # 阿里云 DashScope
  deepseek:
    api_key: "your_deepseek_api_key"    # DeepSeek
  grok:
    api_key: "your_xai_api_key"         # xAI Grok
  gemini:
    api_key: "your_gemini_api_key"      # Google Gemini
  kimi:
    api_key: "your_moonshot_api_key"    # Moonshot Kimi
```

编辑 `config/data_sources.yaml`，填入数据源 API Key：

```yaml
news:
  api_key1: "your_finnhub_api_key_1"    # Finnhub 新闻
  api_key2: "your_finnhub_api_key_2"
fundamentals:
  api_key: "your_finnhub_api_key"       # Finnhub 基本面
```

编辑 `fetchers/api_key_manager.py`，填入 Alpha Vantage API Key（免费，可申请多个用于轮询）：

```python
self.keys = [
    'your_alpha_vantage_api_key_1',
    'your_alpha_vantage_api_key_2',
    ...
]
```

### 3. 配置分析标的

编辑 `config/symbols.yaml`，添加或修改要分析的股票、ETF 和指数。

### 4. 启动服务

三个服务各司其职，正常部署后均为常驻后台进程：

```bash
python data_scheduler.py      # 低频数据采集（新闻、基本面等，受免费 API 调用次数限制）
python horizon_sentinel.py    # AI 辩论调度器（滚动批次获取行情 + 触发 LLM 辩论）
python apex_quant_entry.py    # FastAPI 后端 (默认端口 8000)
```

也可以用 `start.sh` / `stop.sh` 一键管理。

如果 `horizon_sentinel` 因故中断需要补跑一次：

```bash
python horizon_sentinel.py --run-once
```

---

## 📁 项目结构

```
apex_parliament/
│
├── config/                          # 配置文件
│   ├── models.yaml                  # LLM 模型配置（API Key、模型 ID、温度等）
│   ├── data_sources.yaml            # 数据源配置（缓存策略、API Key、采集参数）
│   └── symbols.yaml                 # 分析标的列表与 IBKR 合约映射
│
├── prompts/                         # Agent 提示词（辩论宪法）
│   ├── constitution/                # 三个 Agent 的灵魂设定
│   │   ├── zealot_soul.yaml         #   🔴 Zealot - 永远做多
│   │   ├── reaper_soul.yaml         #   🔵 Reaper - 现实主义者
│   │   ├── fulcrum_soul.yaml        #   ⚖️ Fulcrum - 阻尼器
│   │   └── shared_rules.yaml        #   共享辩论规则
│   ├── formats/                     # 输出格式模板
│   │   ├── debate_output.yaml       #   辩论轮次输出格式
│   │   └── final_report_output.yaml #   最终报告输出格式
│   └── tasks/
│       └── task.yaml                # 任务指令模板
│
├── workflows/                       # 辩论引擎核心
│   ├── nodes.py                     # LangGraph 节点定义（初始化→辩论→报告）
│   ├── state.py                     # 辩论状态机
│   ├── llm_client.py                # LLM 统一调用层（OpenAI 兼容协议）
│   ├── prompt_manager.py            # 提示词加载与组装
│   ├── xml_response_parser.py       # 辩论轮次 XML 解析
│   └── xml_final_report_parser.py   # 最终报告 XML 解析
│
├── fetchers/                        # 数据采集模块
│   ├── api_key_manager.py           # Alpha Vantage API Key 轮询管理
│   ├── alpha_economic_fetcher.py    # 宏观经济指标（GDP、CPI、利率等）
│   ├── alpha_fundamental_fetcher.py # 公司基本面（财报、估值）
│   ├── alpha_fundamental_news_fetcher.py  # Alpha Vantage 新闻
│   ├── finnhub_news_fetcher.py      # Finnhub 新闻采集
│   ├── finnhub_fundamental_fetcher.py     # Finnhub 基本面
│   ├── fear_greed_fetcher.py        # CNN 恐惧贪婪指数
│   ├── economic_data_fetcher.py     # 经济数据聚合
│   └── interactive_stock_fetcher.py # IBKR 行情数据
│
├── analysis/                        # 量化分析
│   ├── technical_snapshot_builder.py # 多时间尺度技术指标快照
│   └── trend_analyzer.py            # 独立简化趋势线模型
│
├── apex_quant_entry.py              # FastAPI 后端入口
├── data_scheduler.py                # 低频数据采集调度器（新闻、基本面，受 API 限额约束）
├── horizon_sentinel.py              # AI 辩论调度器（滚动批次获取行情 + 触发 LLM 辩论）
├── run_debate.py                    # 单次辩论运行脚本（调试用）
├── clean_cache.py                   # 缓存清理工具
├── start.sh / stop.sh               # 服务启停脚本
└── requirements.txt                 # Python 依赖
```

---

## ⚠️ 免责声明

本项目仅供研究与个人使用，不构成任何投资建议。

---

## 📜 许可证

[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) — 非商业使用，署名，相同方式共享。
