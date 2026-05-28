**English** | [**中文**](#中文版)

# ⚖️ Apex Quant

### Adversarial Multi-Agent Debate Framework for Quantitative Analysis

[![License: CC BY-NC-SA 4.0](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc-sa/4.0/)
[![Paper](https://img.shields.io/badge/Paper-SSRN%206354961-blue)](https://papers.ssrn.com/abstract=6354961)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)

---

Apex Quant is an LLM-based multi-agent quantitative analysis framework. Its core mechanism requires three agents holding opposing stances to complete a structured debate before any decision is made. The framework is market-agnostic; the current implementation focuses on US equities due to the abundance of free data sources.

The project started as a personal US stock analysis dashboard for friends in October 2025 and evolved into the triangular debate architecture you see today. Open-sourced alongside the paper.

> **Language note:** Prompts, debate transcripts, analysis output, and the frontend are currently Chinese-only. The earlier inline `*_en` fields turned out to be unreliable — the Chronicler would occasionally drop one language side, leaving output with missing fields. Rather than patching this ad-hoc, the plan is a dedicated translation layer that renders each final report into multiple target languages (English, Japanese, etc.) as a clean downstream step.

---

## 🏛️ Core Architecture: Triangular Roundtable Debate

Most multi-agent trading frameworks assign agents to different **data types** (fundamentals, sentiment, technicals). Apex Quant assigns agents to different **stances**.

![triangle](images/triangle.png)

Three debaters hold fixed investment philosophies and must complete a structured debate before any decision is output:

- 🔴 **Zealot** — Always looking for reasons to go long. Builds the strongest bull case. Never exits easily.
- 🔵 **Reaper** — Not a bear, but a realist: is the current risk worth staying in?
- ⚖️ **Fulcrum** — The system's damper. Default stance is HOLD; any aggressive action must overcome resistance from both other agents. Decision stability comes from structure, not from smoothing historical data or averaging multiple samples.

A fourth agent sits **outside** the debate:

- 📜 **Chronicler** — Pure report synthesizer. Holds no market view and never touches raw data. Once the debate concludes, writes the final report from the argument chains alone. *Originally the Chronicler also moderated rounds and managed memory. But the same underlying AI tendency — wanting to smooth over disagreement — shows up differently in different seats: in **debaters** it leans on mutual concession (the constitution's information-increment / Bayesian-update rules push back against that); in the **moderator seat**, the specific model I had wired in (a Qwen variant) leaned hard the other way — **declaring the debate done the moment the three positions looked roughly aligned**, often after only one or two rounds. Debaters quickly read the room and started phoning it in, since the moderator was going to wrap things up shortly anyway. (A Claude-based variant of the moderator did somewhat better in side experiments, but not by enough to justify keeping AI in the chair.) The moderator role was therefore stripped out (see Stage 2 below), memory passing was demoted to deterministic code, and the Chronicler is left with one job only.*

**Key design insight:** The mirror of an optimist is not a pessimist, but a profit-taker. Reaper doesn't ask "will it drop?" but "is it still worth holding?"

---

## 🔄 Debate Flow

![flowchart](images/flowchart.png)

**Stage 1 — Independent Initialization:** All three debaters receive the same raw data simultaneously and form judgments independently, with no communication.

**Stage 2 — Open Debate:** After seeing each other's initial positions, agents engage in multi-round debate. The debate constitution requires each round to introduce new evidence or new angles — restating one's position doesn't count as valid argument, and rhetorical intensity doesn't equal argument strength. Whether to enter the next round is voted on by the three debaters themselves (each emits a `wants_continue` flag, same logic as the `debate_intensity` field): **as long as at least one debater wants to continue, the round goes on**; a hard cap of 10 rounds prevents runaways.

**Stage 3 — Report & Signatures:** The Chronicler synthesizes the final report with actionable instructions (BUY/SELL/HOLD + position size + entry/stop conditions), strictly within the envelope formed by the three debaters' final stances; Zealot, Reaper, and Fulcrum each attach a signature recording their own final position — users with different risk appetites can reference these.

**Dual outputs — long-term `action` + short-term tactical view.** Every report now carries two parallel views that don't replace each other: `action` / `operation_*` is the integrated strategic-and-tactical optimum (risk/reward over the long horizon plus current entry timing), while `short_term` is a decoupled near-term tactical forecast — `direction` ∈ {up / chop / down}, a `target` price, and `horizon_days` (typically 2–14 trading days, anchored to the next hard catalyst or the dominant technical cycle). Divergence between the two views is itself a valuable signal, not a bug — the Chronicler must explicitly explain in `debate_summary` why "long-run optimum" and "near-term tactical" point opposite ways when they do. Each debater's `short_term` *continues their persona* scoped to the horizon window — Zealot leans up (defaults to "chop" rather than "down" without strong evidence), Reaper leans down, Fulcrum treats short-term noise as "chop" by default — while execution-layer concepts (sizing, stop-loss) don't apply to the pure direction forecast. The `target` is a single number, except for `GENERAL`, where it's the three-price string `SPY=X; QQQ=Y; DIA=Z` (note: SPY/QQQ/DIA analyzed as individual ETFs still take a single number).

---

## 📜 Debate Constitution

All three agents have debate rules built into their system prompts, preventing debates from degenerating into ineffective loops:

- **Asymmetric burden of proof:** The further a stance diverges from the other two, the more counterarguments it must address; failure to rebut causes automatic convergence toward the opposing view
- **Mandatory Bayesian updating:** When the opponent presents valid new evidence, action parameters must be adjusted — purely rhetorical resistance is not permitted
- **Information increment requirement:** Each round must bring new content; sufficiently discussed points are treated as "priced in" with diminishing marginal persuasion
- **Dispute shelving mechanism:** When neither side has new evidence, the dispute must be explicitly shelved and a new argument direction opened
- **Raw data vs. `[推论]` (inference) tagging:** A `raw_data` field (e.g. `RSI=72.3`) is consensus — quote it and no one may overturn it. But a second-order *interpretation* of that data ("overbought", "trend reversal") must be tagged `[推论]`. The tag is a public declaration of "this is my reasoning, challenge the chain" — so rebutting a `[推论]` is legitimate debate, not data denial. Stating an inference in ground-truth voice ("obviously it's going to drop") is a format violation; any core claim that moves `action` / `direction` / `target` must carry the tag.

---

## 📸 System Interface

![dashboard](images/dashboard.png) ![debate](images/debate.png)

The verdict page shows the final decision, position recommendations, and risk management parameters; the debate page displays the complete argument chains from all three agents.

Each decision cycle's input spans multi-timeframe quantitative data, stock-specific news, company fundamentals, and macroeconomic indicators.

<details>
<summary>Quantitative Data Screenshots (Four Timeframes)</summary>

![technical1](images/technical1.png)
![technical2](images/technical2.png)
![technical3](images/technical3.png)
![technical4](images/technical4.png)

</details>

---

## 📄 Paper

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

## 📊 Data Sources

Each decision cycle is fed by the following data sources:

| Data Type | Source | Description |
|-----------|--------|-------------|
| Stock & ETF Prices | **Interactive Brokers (IBKR)** | Multi-timeframe candlesticks (1min / 5min / 1h / 1d), processed by `technical_snapshot_builder` (V15, session-aware) and `trend_analyzer` for simplified trend lines |
| Macro Benchmarks | **Interactive Brokers (IBKR)** | **SPY / QQQ / DIA** ETFs — used instead of SPX/NDX/INDU indices because ETFs deliver continuous pre/post-market quotes with real volume |
| Macroeconomic Indicators | **Alpha Vantage** | Federal funds rate, CPI, unemployment, GDP, treasury yields, etc. |
| Company Fundamentals | **Alpha Vantage / Finnhub** | Earnings, valuation metrics |
| Market News | **Finnhub** | Stock-specific news + general market news |
| Fear & Greed Index | **CNN Fear & Greed Index** | Market sentiment indicator |

> **Note:** IBKR market data requires an Interactive Brokers account and TWS/IB Gateway; Alpha Vantage and Finnhub offer free APIs (with rate limits).

**V15 session-aware snapshot.** Each technical snapshot carries `instrument_metadata` and `session_context`, both auto-resolved from the latest 1-minute bar timestamp via `pandas_market_calendars` (handles DST and early-close days). The JSON is reorganized by data completeness — `current_snapshot / daily_technicals / hourly_technicals / weekly_snapshot / positioning / cross_timeframe_summary / price_structure` — and fields that would mislead the AI during pre/post-market (e.g. `volume_ratio_vs_20d_daily_avg`) are deliberately nulled out. When the primary target is SPY or QQQ itself, it is automatically deduplicated from the macro backdrop.

**Symbol-prefixed fields (anti-laziness).** Live runs surfaced a recurring failure mode: with multiple instruments in scope (e.g. SPY/QQQ/DIA + a target stock), debaters would latch onto one favorite indicator and cross-reference numbers without keeping track of which symbol they belonged to. Two fixes:

- `analysis/symbol_prefix.py` flattens every nested data block so every leaf key starts with the owning symbol — e.g. `QQQ_daily_technicals_ma_20_daily_val`, `SPY_current_snapshot_last_price`. Ownership is now syntactically inseparable from the value.
- The debate constitution (`shared_rules.yaml`) and `task.yaml` add explicit anti-tunnel-vision rules: stock/ETF analysis must evaluate signals **against the prevailing macro regime**, and `GENERAL` runs must analyze SPY / QQQ / DIA as three independent lenses — divergence between them (e.g. tech going solo while industrials lag) is itself a required signal, not noise to be smoothed over. The `operation_target` for `GENERAL` is now a three-price string (`SPY=X; QQQ=Y; DIA=Z`) so the AI can't collapse the three lenses into one number.

**Per-symbol macro + sector backdrop.** `symbols.yaml` now tags every stock with its own primary benchmark and sector ETF (e.g. NVDA → QQQ + SMH, JPM → SPY + XLF). When a stock is analyzed, the prompt receives that stock's specific benchmark and sector context — not a generic SPY everywhere. The sector layer was added alongside (XLF / XLV / XLE / XLU / XLP / IGV / ITA / REMX) so the AI can reason "NVDA vs. its semis peers" and "JPM in a risk-off financial regime" instead of just "stock vs. broad market."

**Mechanical memory inheritance + DAG-driven run pool.** Child analyses (an individual stock) now inherit their parent's most recent debate snapshot (the matching sector ETF and the matching benchmark) as compressed context, provided the parent report is within `inheritance_max_age` (default 1h). To make sure that "parent" actually exists when "child" starts, `horizon_sentinel.py` builds a DAG from the `sector` field in `symbols.yaml` and runs the pool top-down: **GENERAL first → sector ETFs and broad-base ETFs → individual stocks (each one waiting for its sector ETF debate to finish)**. LLM concurrency is globally capped by a semaphore (raised substantially once DeepSeek lifted its default concurrency to 500 — the bottleneck is now IBKR's single-threaded request throughput, not the LLM side), and IBKR fetches are serialized with ≥1s spacing. Inheritance is on by default. *Earlier the Chronicler was supposed to manage this memory dynamically; after the moderator role was stripped, memory passing was demoted to a deterministic code path to keep behavior predictable.*

**Regional coverage + `runnable` flag.** This project now doubles as the backend for a multi-region dashboard. `symbols.yaml` carries a `region` field per symbol (`US` / `EU` / `JP`) and a `runnable` flag (default `true`):

- `runnable: true` — `horizon_sentinel` and `data_scheduler` schedule it automatically. The full US universe (stocks, ETFs, sector ETFs, `GENERAL`) is in this bucket.
- `runnable: false` — auto-scheduling skips it, but the frontend still shows the slot. Currently this covers EU equities (e.g. `RHM`), Tokyo-listed JP equities (e.g. `7974`, `7011`), and the regional macro placeholders `GENERAL_EU` / `GENERAL_JP`. IBKR doesn't carry data subscriptions for those markets on this account, so a companion Claude-Code-driven project runs them on an ad-hoc cadence and writes the resulting debate reports back to the same `data/debate/{SYMBOL}/` directory tree, which the frontend reads.

---

## 🗂️ Example Data

The `data/examples/` directory contains selected core data from a GENERAL (market-wide) analysis cycle on March 23, 2026, showing what the system's main inputs and outputs look like. **These on-disk snapshots predate three later changes**: the V15 session-aware schema, the SPX/NDX/INDU → SPY/QQQ/DIA benchmark switch, and the symbol-prefix flattening. So the files still show `SPX`, the older field names (`last_close`, `*_en` bilingual fields), and unprefixed nested keys. The JSON snippets below are rewritten to reflect the **current** schema.

```
data/examples/
├── debate/       GENERAL_Analysis_20260323T134100Z.json   # Debate result (full argument chains + final verdict)
├── news/         GENERAL_news_20260323T113922Z.json       # Market news (Finnhub)
├── economic/     economic_indicators_20260323T100524Z.json # Macroeconomic indicators
├── fear_greed/   fear_greed_latest_20260323T000000Z.json   # Fear & Greed Index + VIX
├── technical/    SPX_technical_20260323T134100Z.json       # SPX multi-timeframe technical snapshot
└── market_data/  SPX_5y_1d_20260323T000000Z.csv            # SPX 5-year daily OHLCV
                  SPX_7d_5m_20260323T134000Z.csv            # SPX 7-day 5-minute OHLCV
```

<details>
<summary><b>Debate Result Summary (click to expand)</b></summary>

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
<summary><b>Macroeconomic Indicators (click to expand)</b></summary>

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
<summary><b>Fear & Greed Index (click to expand)</b></summary>

```json
{
  "fear_greed": {"value": 12, "previous_close": 14, "one_week_ago": 21, "one_month_ago": 36},
  "vix": {"value": 30.3, "change_percent": 13.14}
}
```

</details>

<details>
<summary><b>Technical Snapshot — Selected Fields, Current Schema (click to expand)</b></summary>

Every leaf key carries its owning symbol up front, so cross-symbol references can never lose track of ownership:

```json
{
  "instrument_metadata": { "symbol": "QQQ", "asset_type": "ETF" },
  "session_context":     { "session": "REGULAR", "is_early_close": false },

  "QQQ_current_snapshot_last_price": 612.50,
  "QQQ_current_snapshot_last_volume": 18420300,

  "QQQ_minute_level_rsi_14_5min": 77.87,
  "QQQ_minute_level_atr_14_5min": 15.12,
  "QQQ_minute_level_liquidity_score_vol_per_bar": 0.0,

  "QQQ_hourly_technicals_ma_20_hourly_val": 610.25,
  "QQQ_hourly_technicals_ma_50_hourly_val": 615.50,
  "QQQ_hourly_technicals_rsi_14_hourly": 50.59,
  "QQQ_hourly_technicals_macd_hist_hourly": 0.556,
  "QQQ_hourly_technicals_bb_pct_b_hourly": 0.59
}
```

</details>

---

## ⚡ Quick Start

> If the steps below look intimidating, just install [Claude Code](https://claude.ai/claude-code), point it at this repo, and let it figure everything out. That's how this project's deployment, debugging, and open-source release were done.

### 1. Install Dependencies

```bash
git clone https://github.com/sst19910323/apex_parliament.git
cd apex_parliament
pip install -r requirements.txt
```

### 2. Configure API Keys

Edit `config/models.yaml` to add the models you want to use. You only need two or three (the author runs on Alibaba Cloud and uses DeepSeek + Qwen daily). Choose models that are smart enough and have long context windows.

`workflows/llm_client.py` contains a `role_mapping` that determines which model each role uses, indexed by key name in models.yaml. Temperature has role-specific presets:

- **Zealot 0.9, Reaper 0.8** — adversarial debaters need more exploration
- **Fulcrum 0.3** — a stubborn damper; its job is to hold ground, not to improvise
- **Chronicler 0.3** — the report writer; must stay faithful to what was actually said. (After the moderator role was stripped, Chronicler now does report writing only — memory is passed mechanically by code, and continuation is voted on by the debaters.)

```yaml
# config/models.yaml
default_model: "qwen3.6-plus"

models:
  qwen3-max:
    api_key: "your_dashscope_api_key"
    base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model_id: "qwen3-max"
    temperature: 0.8             # Can be overridden by role presets
  deepseek:
    api_key: "your_deepseek_api_key"
    base_url: "https://api.deepseek.com/v1"
    model_id: "deepseek-v4-flash"
    temperature: 0.8
  # Add more models in the same format...
```

Edit `config/data_sources.yaml` with data source API keys:

```yaml
news:
  api_key1: "your_finnhub_api_key_1"    # Finnhub News
  api_key2: "your_finnhub_api_key_2"
fundamentals:
  api_key: "your_finnhub_api_key"       # Finnhub Fundamentals
```

Edit `fetchers/api_key_manager.py` with Alpha Vantage API keys (free, multiple keys for rotation):

```python
self.keys = [
    'your_alpha_vantage_api_key_1',
    'your_alpha_vantage_api_key_2',
    ...
]
```

### 3. Configure Analysis Targets

Edit `config/symbols.yaml` to add or modify stocks, ETFs, and indices to analyze.

### 4. Start Services

Three services, each with a distinct role, run as persistent background processes:

```bash
python data_scheduler.py      # Low-frequency data collection (news, fundamentals — rate-limited by free APIs)
python horizon_sentinel.py    # AI debate scheduler (rolling batch market data fetch + LLM debate trigger)
python apex_quant_entry.py    # FastAPI backend (default port 8000)
```

You can also use `start.sh` / `stop.sh` for one-click management.

If `horizon_sentinel` was interrupted and needs a catch-up run:

```bash
python horizon_sentinel.py --run-once
```

---

## 📁 Project Structure

```
apex_parliament/
│
├── config/                          # Configuration
│   ├── models.yaml                  # LLM model config (API keys, model IDs, temperature, etc.)
│   ├── data_sources.yaml            # Data source config (cache policy, API keys, fetch params)
│   └── symbols.yaml                 # Analysis targets & IBKR contract mappings
│
├── prompts/                         # Agent Prompts (Debate Constitution)
│   ├── constitution/                # Agent soul definitions
│   │   ├── zealot_soul.yaml         #   🔴 Zealot — always long (debater)
│   │   ├── reaper_soul.yaml         #   🔵 Reaper — the realist (debater)
│   │   ├── fulcrum_soul.yaml        #   ⚖️ Fulcrum — the damper (debater)
│   │   ├── chronicler_soul.yaml     #   📜 Chronicler — final-report synthesizer (outside debate)
│   │   └── shared_rules.yaml        #   Shared debate rules
│   ├── formats/                     # Output format templates
│   │   ├── debate_output.yaml       #   Debate round output format
│   │   └── final_report_output.yaml #   Final report output format
│   └── tasks/
│       └── task.yaml                # Task instruction template
│
├── workflows/                       # Debate Engine Core
│   ├── nodes.py                     # LangGraph node definitions (init → debate → report)
│   ├── state.py                     # Debate state machine
│   ├── llm_client.py                # Unified LLM call layer (OpenAI-compatible protocol)
│   ├── prompt_manager.py            # Prompt loading & assembly
│   ├── xml_response_parser.py       # Debate round XML→JSON (XML is more fault-tolerant than JSON)
│   └── xml_final_report_parser.py   # Final report XML→JSON
│
├── fetchers/                        # Data Fetcher Modules
│   ├── api_key_manager.py           # Alpha Vantage API key rotation        ← active
│   ├── alpha_economic_fetcher.py    # Macro indicators (GDP, CPI, rates)    ← active (data_scheduler)
│   ├── alpha_fundamental_fetcher.py # Company fundamentals                  ← active (data_scheduler)
│   ├── finnhub_news_fetcher.py      # Finnhub news fetcher                  ← active (data_scheduler)
│   ├── fear_greed_fetcher.py        # CNN Fear & Greed Index                ← active (data_scheduler)
│   ├── interactive_stock_fetcher.py # IBKR market data                      ← active (horizon_sentinel)
│   ├── alpha_fundamental_news_fetcher.py  # Alpha Vantage news              ← deprecated
│   ├── finnhub_fundamental_fetcher.py     # Finnhub fundamentals            ← deprecated
│   ├── economic_data_fetcher.py     # Economic data aggregator              ← deprecated
│   ├── interactive_brokers_etf_profile.py # IBKR ETF profile                ← deprecated
│   ├── interactive_options_fundamentals_fetcher.py # IBKR options data      ← deprecated
│   └── option_collector.py          # Options data aggregator               ← deprecated
│
├── analysis/                        # Quantitative Analysis
│   ├── technical_snapshot_builder.py # Multi-timeframe technical indicator snapshots
│   ├── trend_analyzer.py            # Simplified trend line model
│   └── symbol_prefix.py             # Flatten nested data with {symbol}_ prefix on every leaf key
│
├── apex_quant_entry.py              # FastAPI backend entry point
├── data_scheduler.py                # Low-frequency data scheduler (news, fundamentals — API rate limited)
├── horizon_sentinel.py              # AI debate scheduler (DAG pool: GENERAL → sectors → stocks)
├── run_debate.py                    # LangGraph debate engine entry (called by horizon_sentinel)
├── clean_cache.py                   # Cache cleanup utility
├── start.sh / stop.sh               # Start/stop all three services
├── start_backend.sh / stop_backend.sh # Start/stop only the FastAPI backend
└── requirements.txt                 # Python dependencies
```

---

<details>
<summary>🕰️ <b>Development milestones (click)</b></summary>

Key milestones along the way — from an overconfident single agent to the current four-role architecture.

![timeline](images/timeline.png)

</details>

---

## ⚠️ Disclaimer

This project is for research and personal use only. It does not constitute investment advice.

---

## 📜 License

[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) — Non-commercial, attribution, share-alike.

---

<a id="中文版"></a>

# ⚖️ Apex Quant — 中文

### 基于对抗性多智能体辩论的量化分析框架

---

Apex Quant 是一个基于大语言模型的多智能体量化分析框架，核心机制是三个持有对立立场的 Agent 在做出任何决策之前，先完成结构化辩论。框架本身与市场无关，当前实现以美股为主，因为免费数据源最丰富。

项目起初是为了给自己和朋友们做一个美股分析看板，从2025年10月开始开发，演化出了现在这套三角辩论架构。伴随论文一起开源。

---

## 🏛️ 核心架构：三角圆桌辩论

大多数多智能体交易框架把不同的 Agent 分配给不同的**数据类型**（基本面、情绪、技术面）。Apex Quant 的不同在于：把 Agent 分配给不同的**立场**。

![triangle](images/triangle.png)

三位辩论者各自持有固定的投资哲学，在任何决策输出之前，必须先完成结构化辩论：

- 🔴 **Zealot**（狂热者）— 永远在找做多理由，构建最强的买入论据，绝不轻易出局
- 🔵 **Reaper**（收割者）— 不是空头，是现实主义者：当前风险值不值得继续持有？
- ⚖️ **Fulcrum**（支点）— 系统的阻尼器。默认立场是 HOLD，任何激进操作都需要同时突破另外两个 Agent 的阻力。不依赖历史数据平滑，不依赖多次采样取平均——决策的稳定性直接从结构中来。

辩论桌之外还有第四位 Agent：

- 📜 **Chronicler**（史官）— 纯报告综合者。不持有任何市场立场，也不接触原始数据。辩论结束后，仅凭三方论证链撰写最终报告。*史官最初还兼任秩序维护和记忆管理。但同一种 AI"和稀泥"的底层倾向，落到不同位置上表现不一样：落到**辩论者**身上，是互相妥协（这一面靠辩论宪法的"信息增量 / 贝叶斯更新"规则去对抗）；落到**裁判位**上，我手上挂的那套模型（一款 Qwen 变体）则反过来表现为——**只要三方立场看起来差不多，就急着判定辩论结束**，往往一两回合就收尾。辩论者很快读懂了空气，开始敷衍——反正裁判马上就要把它结束掉。（Claude 系的同款裁判侧测下来要好一些，但远没好到足以让我把 AI 留在裁判位上。）于是裁判职责被剥离（见下面 Stage 2），记忆传递降级为代码确定性逻辑，史官只剩"写报告"这一项。*

**关键设计洞察：** 乐观者的镜像不是悲观者，而是止盈者。Reaper 问的不是"会不会跌"，而是"还值不值得拿"。

---

## 🔄 辩论流程

![flowchart](images/flowchart.png)

**Stage 1 — 独立初始化：** 三位辩论者同时收到相同的原始数据，各自独立形成判断，互不通信。

**Stage 2 — 自由辩论：** 看到彼此的初始判断后展开多轮辩论。辩论宪法规定每轮必须引入新论据或新角度——重复己方立场不算有效论证，修辞强度不等于论证强度。是否进入下一轮由三位辩论者自己投票决定（每人输出一个 `wants_continue` 标记，与 `debate_intensity` 同一思路）：**只要有一人想继续，本轮就继续**；10 轮硬上限兜底防失控。

**Stage 3 — 报告与签名：** Chronicler 综合三方论证链，在三方最终立场构成的包络区间内撰写最终报告，输出可执行指令（BUY/SELL/HOLD + 仓位大小 + 入场/止损条件）；Zealot、Reaper、Fulcrum 各自附签自己最终轮的立场——风险偏好不同的使用者可以自行参考。

**双产品输出——长期 `action` + 短期局势预判。** 每份报告现在并行承载两套 view，互不替代：`action` / `operation_*` 是综合战略战术最优（长期风险收益 + 当下买卖时机的合力），而 `short_term` 是一个与长期估值解耦的短线方向预判——`direction` ∈ {上行/震荡/下行}，附 `target` 目标价 和 `horizon_days`（典型 2–14 交易日，按下一个硬事件或主导的技术周期锚定）。两套 view 出现分歧本身就是高价值信号，不是 bug——Chronicler 必须在 `debate_summary` 里显式说清楚"为什么综合最优 vs 短线最优会指向相反方向"。每位辩论者的 `short_term` 在 horizon 窗口内**延续各自人设**——Zealot 偏看涨（证据不足时默认"震荡"而非"下行"）、Reaper 偏看跌、Fulcrum 默认把短期噪音判为"震荡"——但执行层概念（仓位、止损）不延伸到纯方向预测。`target` 填单一数字，唯一例外是 `GENERAL`，填三价位字符串 `SPY=X; QQQ=Y; DIA=Z`（注意：SPY/QQQ/DIA 作为单一 ETF 被分析时仍填单一数字）。

---

## 📜 辩论宪法

三个 Agent 的系统提示里都内置了一套辩论规则，防止辩论退化成无效循环：

- **举证负担不对称：** 立场越偏离另外两方，需要反驳的论点越多；无法反驳则立场自动向对方收敛
- **贝叶斯强制更新：** 对方提出有效新证据时，必须调整自己的行动参数，不能只靠修辞抵抗
- **信息增量要求：** 每轮必须带来新内容，已充分讨论过的争议点视为已定价，边际说服力递减
- **争议搁置机制：** 双方均无新证据时，必须显式声明搁置该争议，开辟新的论证方向
- **原始数据 vs `[推论]` 标注：** `raw_data` 字段（如 `RSI=72.3`）是共识，引用即定，谁都不能推翻；但基于数据的二阶解读（"超买"、"趋势反转"）必须打 `[推论]` 标签。这个标签等于公开声明"这是我的推导、欢迎挑战推导链"——所以反驳一个 `[推论]` 是合法辩论，不是质疑数据。用 ground-truth 口气陈述推论（"显然要跌"）属于格式违规；任何会推动 `action` / `direction` / `target` 的核心判断都必须带标签。

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
| 股票 & ETF 行情 | **Interactive Brokers (IBKR)** | 多时间尺度 K 线（1min / 5min / 1h / 1d），经 `technical_snapshot_builder` (V15 session-aware) 和 `trend_analyzer` 提取简化趋势线 |
| 宏观基准 | **Interactive Brokers (IBKR)** | **SPY / QQQ / DIA** ETF —— 用 ETF 取代 SPX/NDX/INDU 指数，因为 ETF 在盘前盘后有连续报价和真实成交量 |
| 宏观经济指标 | **Alpha Vantage** | 联邦基金利率、CPI、失业率、GDP、国债收益率等 |
| 公司基本面 | **Alpha Vantage / Finnhub** | 财报、估值指标 |
| 市场新闻 | **Finnhub** | 个股新闻 + 大盘新闻 |
| 恐惧贪婪指数 | **CNN Fear & Greed Index** | 市场情绪指标 |

> **注意：** IBKR 行情需要盈透证券账户和 TWS/IB Gateway；Alpha Vantage 和 Finnhub 提供免费 API（有调用频率限制）。

**V15 session-aware 量化快照。** 每份技术快照都带有 `instrument_metadata` 和 `session_context`，由最新一根 1 分钟 bar 的时间戳通过 `pandas_market_calendars` 自动判定（正确处理夏令时和早收盘日）。JSON 按"数据完整性"重组：`current_snapshot / daily_technicals / hourly_technicals / weekly_snapshot / positioning / cross_timeframe_summary / price_structure`；盘前盘后会误导 AI 的字段（如 `volume_ratio_vs_20d_daily_avg`）会被主动置 null。当分析目标本身就是 SPY 或 QQQ 时，它会从宏观背景中自动去重。

**带标的前缀的字段（防 AI 偷懒）。** 实跑中发现一个反复出现的故障模式：多标的同时在场时（例如 SPY/QQQ/DIA + 目标个股），辩论者会过度专注某一套自己最熟的量化指标，并在跨标的引用时丢失数字归属。两个补丁：

- `analysis/symbol_prefix.py` 把所有嵌套数据扁平化，每一个 leaf key 都以所属标的开头——比如 `QQQ_daily_technicals_ma_20_daily_val`、`SPY_current_snapshot_last_price`。归属关系直接焊在 key 上，AI 想抹也抹不掉。
- 辩论宪法（`shared_rules.yaml`）和 `task.yaml` 增加了显式的防偏规则：分析个股/ETF 时必须**结合大盘 regime** 评估信号有效性；`GENERAL` 场景必须把 SPY / QQQ / DIA 当作三个独立镜头分别分析——三者的方向分歧本身就是必须解读的信号（比如科技独走、工业拖后），不允许被糊弄掉。`GENERAL` 的 `operation_target` 现在输出三价位字符串（`SPY=X; QQQ=Y; DIA=Z`），AI 没法把三个镜头压成一个数字。

**逐标的的大盘 + 板块背景。** `symbols.yaml` 现在给每只个股标注它自己的主基准和所属板块 ETF（例如 NVDA → QQQ + SMH，JPM → SPY + XLF）。分析某只个股时，提示词里塞的就是这只股票对应的基准和板块背景，而不是千篇一律的 SPY。同时新增了板块层（XLF / XLV / XLE / XLU / XLP / IGV / ITA / REMX），AI 可以推理"NVDA 在半导体同行里强弱如何"或"JPM 处于金融板块 risk-off 之中"，而不是只有"个股 vs 大盘"。

**机械化的记忆传递 + DAG 调度的运行池。** 子层分析（个股）现在会自动继承父层（对应板块 ETF + 对应基准）最近一次辩论快照作为压缩上下文，前提是父层报告在 `inheritance_max_age`（默认 1h）以内。为了保证开始辩论时"父层"确实已经存在，`horizon_sentinel.py` 会按 `symbols.yaml` 的 `sector` 字段构 DAG，自顶向下跑 pool：**先 GENERAL → 再板块 ETF 和宽基 ETF → 再个股（每只个股等自己所属的板块 ETF 辩论完成才入池）**。LLM 并发由全局 Semaphore 限制（DeepSeek 把默认并发上调到 500 之后，这个上限也大幅提高了——目前瓶颈在 IBKR 单线程请求吞吐，不在 LLM 这边），IBKR 拉数据强制串行 + 每次间隔 ≥1s。默认开启继承。*原本这部分记忆是想让史官动态管理的；裁判职责剥离之后，记忆传递降级为代码确定性逻辑，行为可预测。*

**多大区覆盖 + `runnable` 开关。** 这个项目现在还兼任一个多大区看板的后端。`symbols.yaml` 每条记录都带 `region` 字段（`US` / `EU` / `JP`）和 `runnable` 开关（默认 `true`）：

- `runnable: true` —— 由 `horizon_sentinel` 和 `data_scheduler` 自动调度。整个美股版图（个股、ETF、板块 ETF、`GENERAL`）都在这一桶里。
- `runnable: false` —— 自动调度直接跳过，但前端依然展示这个槽。目前覆盖欧股（如 `RHM`）、东证日股（如 `7974`、`7011`），以及两个大区宏观占位 `GENERAL_EU` / `GENERAL_JP`。这账号下 IBKR 没订阅这两个市场的数据，所以由一个 Claude-Code 驱动的伴生项目不定期手动跑，把辩论报告写回到同一棵 `data/debate/{SYMBOL}/` 目录里，前端从这里读取。

---

## 🗂️ 示例数据

`data/examples/` 目录包含 2026 年 3 月 23 日 GENERAL（大盘）分析周期的部分核心数据，展示系统主要的输入输出长什么样。**这些磁盘上的快照早于后来的三次改动**：V15 session-aware schema、SPX/NDX/INDU → SPY/QQQ/DIA 基准切换、以及标的前缀扁平化。所以文件里仍是 `SPX`、旧字段名（`last_close`、`*_en` 双语字段）、未加前缀的嵌套 key。下面折叠的 JSON 片段已经按**当前** schema 重写。

```
data/examples/
├── debate/       GENERAL_Analysis_20260323T134100Z.json   # 辩论结果（三方论证链 + 最终裁决）
├── news/         GENERAL_news_20260323T113922Z.json       # 大盘新闻（Finnhub）
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
<summary><b>技术分析快照 — 部分字段（当前 schema，点击展开）</b></summary>

每一个 leaf key 前都直接焊上所属标的，跨标的引用时不可能丢归属：

```json
{
  "instrument_metadata": { "symbol": "QQQ", "asset_type": "ETF" },
  "session_context":     { "session": "REGULAR", "is_early_close": false },

  "QQQ_current_snapshot_last_price": 612.50,
  "QQQ_current_snapshot_last_volume": 18420300,

  "QQQ_minute_level_rsi_14_5min": 77.87,
  "QQQ_minute_level_atr_14_5min": 15.12,
  "QQQ_minute_level_liquidity_score_vol_per_bar": 0.0,

  "QQQ_hourly_technicals_ma_20_hourly_val": 610.25,
  "QQQ_hourly_technicals_ma_50_hourly_val": 615.50,
  "QQQ_hourly_technicals_rsi_14_hourly": 50.59,
  "QQQ_hourly_technicals_macd_hist_hourly": 0.556,
  "QQQ_hourly_technicals_bb_pct_b_hourly": 0.59
}
```

</details>

---

## ⚡ 快速上手

> 如果下面的步骤看着头疼，装个 [Claude Code](https://claude.ai/claude-code)，把这个 repo 扔给它，让它帮你搞定一切。本项目的部署调试和开源整理就是这么完成的。

### 1. 安装依赖

```bash
git clone https://github.com/sst19910323/apex_parliament.git
cd apex_parliament
pip install -r requirements.txt
```

### 2. 配置 API Key

编辑 `config/models.yaml`，按格式添加你要用的模型。不需要全部填写，配两三个即可（作者本人服务器在阿里云，日常只用 DeepSeek + Qwen）。建议选择足够聪明、上下文足够长的模型。

`workflows/llm_client.py` 中的 `role_mapping` 决定了哪个角色使用哪个模型，按 models.yaml 中的 key 名索引。温度（temperature）有角色预设：

- **Zealot 0.9、Reaper 0.8** —— 对抗性辩论者需要更大的探索空间
- **Fulcrum 0.3** —— 顽固的阻尼器，职责是守住立场而不是发挥
- **Chronicler 0.3** —— 报告撰写者，必须忠于辩论实际发生的内容。（剥离裁判职责后，史官只管写报告——记忆由代码机械传递，是否进入下一轮由辩论者投票决定。）

```yaml
# config/models.yaml
default_model: "qwen3.6-plus"

models:
  qwen3-max:
    api_key: "your_dashscope_api_key"
    base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model_id: "qwen3-max"
    temperature: 0.8             # 可被角色预设覆盖
  deepseek:
    api_key: "your_deepseek_api_key"
    base_url: "https://api.deepseek.com/v1"
    model_id: "deepseek-v4-flash"
    temperature: 0.8
  # 按相同格式添加更多模型...
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
│   ├── constitution/                # Agent 灵魂设定
│   │   ├── zealot_soul.yaml         #   🔴 Zealot - 永远做多（辩论者）
│   │   ├── reaper_soul.yaml         #   🔵 Reaper - 现实主义者（辩论者）
│   │   ├── fulcrum_soul.yaml        #   ⚖️ Fulcrum - 阻尼器（辩论者）
│   │   ├── chronicler_soul.yaml     #   📜 Chronicler - 史官（辩论之外的最终报告撰写者）
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
│   ├── xml_response_parser.py       # 辩论轮次 XML→JSON（XML 比 JSON 容错率更高）
│   └── xml_final_report_parser.py   # 最终报告 XML→JSON
│
├── fetchers/                        # 数据采集模块
│   ├── api_key_manager.py           # Alpha Vantage API Key 轮询管理        ← 在用
│   ├── alpha_economic_fetcher.py    # 宏观经济指标（GDP、CPI、利率等）        ← 在用 (data_scheduler)
│   ├── alpha_fundamental_fetcher.py # 公司基本面（财报、估值）                ← 在用 (data_scheduler)
│   ├── finnhub_news_fetcher.py      # Finnhub 新闻采集                      ← 在用 (data_scheduler)
│   ├── fear_greed_fetcher.py        # CNN 恐惧贪婪指数                      ← 在用 (data_scheduler)
│   ├── interactive_stock_fetcher.py # IBKR 行情数据                         ← 在用 (horizon_sentinel)
│   ├── alpha_fundamental_news_fetcher.py  # Alpha Vantage 新闻              ← 废弃
│   ├── finnhub_fundamental_fetcher.py     # Finnhub 基本面                  ← 废弃
│   ├── economic_data_fetcher.py     # 经济数据聚合                           ← 废弃
│   ├── interactive_brokers_etf_profile.py # IBKR ETF 持仓                   ← 废弃
│   ├── interactive_options_fundamentals_fetcher.py # IBKR 期权数据           ← 废弃
│   └── option_collector.py          # 期权数据聚合                           ← 废弃
│
├── analysis/                        # 量化分析
│   ├── technical_snapshot_builder.py # 多时间尺度技术指标快照
│   ├── trend_analyzer.py            # 独立简化趋势线模型
│   └── symbol_prefix.py             # 把嵌套数据扁平化，每个 leaf key 加 {symbol}_ 前缀
│
├── apex_quant_entry.py              # FastAPI 后端入口
├── data_scheduler.py                # 低频数据采集调度器（新闻、基本面，受 API 限额约束）
├── horizon_sentinel.py              # AI 辩论调度器（DAG pool：GENERAL → 板块 → 个股）
├── run_debate.py                    # LangGraph 辩论引擎入口（horizon_sentinel 调用）
├── clean_cache.py                   # 缓存清理工具
├── start.sh / stop.sh               # 三个服务一键启停
├── start_backend.sh / stop_backend.sh # 仅启停 FastAPI 后端
└── requirements.txt                 # Python 依赖
```

---

<details>
<summary>🕰️ <b>开发重要时间点 (点击展开)</b></summary>

从最初一个过度自信的单 Agent，一路演化到今天的四角色架构，这是我的开发历程。

![timeline](images/timeline.png)

</details>

---

## ⚠️ 免责声明

本项目仅供研究与个人使用，不构成任何投资建议。

---

## 📜 许可证

[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) — 非商业使用，署名，相同方式共享。
