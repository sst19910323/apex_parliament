#!/usr/bin/env python3
"""
Horizon Sentinel - AI Parliament Scheduler (V8.0 - Rolling Batch & JIT Fetch)

核心逻辑:
1. [分组滚轮] 标的随机洗牌后分组 (每组5个)，GENERAL固定第一组最先执行。
2. [按需数据] 每组执行前，先串行从IBKR下载该组数据，再错开启动LLM分析。
3. [General守卫] 每组执行前检查GENERAL数据是否过期(阈值从yaml读)，过期则重新下载。
4. [API节流] 组内LLM任务间隔2秒错开启动，避免瞬间QPS爆炸。
5. [独立连接] 每个batch独立连接/断开IBKR，互不影响。
"""

import argparse
import asyncio
import logging
import sys
import time
import json
import random
import yaml
from datetime import datetime, time as dtime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Dict, List, Any, Tuple, Optional

# --- 引入市场日历库 ---
import pandas_market_calendars as mcal

# -----------------------------------------------------------------
# 路径设置
# -----------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# --- 导入组件 ---
try:
    from analysis.technical_snapshot_builder import process_symbol_technical_analysis
    from fetchers.interactive_stock_fetcher import MarketDataFetcher, MarketDataConfig, SymbolContract
    from run_debate import DebateEngine
except ImportError as e:
    print(f"CRITICAL ERROR: Failed to import required modules. {e}")
    sys.exit(1)

# ──────────────────────────────────────────────────────────────────────────────
# 配置常量 & 交易日辅助函数
# ──────────────────────────────────────────────────────────────────────────────
EASTERN = ZoneInfo("America/New_York")
RUN_TIMES = [dtime(9, 0)]
CHECK_INTERVAL = 60
BATCH_SIZE = 5
TASK_STAGGER_SECONDS = 2  # LLM任务启动间隔

# 宏观基准ETF（替代原 SPX/NDX/INDU 指数，有盘前盘后成交量）
BENCHMARK_SYMBOLS = ["SPY", "QQQ", "DIA"]

def get_trading_calendar(exchange: str = 'NYSE') -> mcal.MarketCalendar:
    try:
        return mcal.get_calendar(exchange)
    except Exception as e:
        logging.critical(f"Failed to get trading calendar: {e}")
        raise

def is_trading_day(calendar: mcal.MarketCalendar, check_date: datetime) -> bool:
    date_to_check = check_date.date()
    try:
        schedule = calendar.schedule(start_date=date_to_check, end_date=date_to_check)
        return not schedule.empty
    except Exception as e:
        logging.warning(f"Failed to check trading day for {date_to_check}: {e}. Defaulting to True.")
        return True

def get_now_et():
    return datetime.now(EASTERN)

# ──────────────────────────────────────────────────────────────────────────────
# Context Assembler (数据组装工)
# ──────────────────────────────────────────────────────────────────────────────
class ContextAssembler:
    def __init__(self, data_config: Dict):
        self.full_cfg = data_config.get('data_sources', {})
        self.root = PROJECT_ROOT

    def _get_max_age(self, section: str) -> float:
        cfg = self.full_cfg.get(section, {})
        return float(cfg.get('max_file_age', 315360000))

    def _find_latest(self, rel_dir: str, pattern: str, max_age_seconds: float) -> Optional[Path]:
        if not rel_dir: return None
        dir_path = self.root / rel_dir
        if not dir_path.exists(): return None
        
        files = list(dir_path.glob(pattern))
        if not files: return None
        
        latest_file = max(files, key=lambda f: f.stat().st_mtime)
        
        file_age = time.time() - latest_file.stat().st_mtime
        if file_age > max_age_seconds:
            logging.warning(f"⚠️ [Data Expired] {latest_file.name} is {file_age/3600:.1f}h old. Ignoring.")
            return None
            
        return latest_file

    def _read_file(self, path: Path) -> str:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logging.error(f"Read failed {path}: {e}")
            return "{}"

    def _get_path_str(self, path: Path) -> str:
        if not path: return None
        try:
            return str(path.relative_to(self.root)).replace("\\", "/")
        except:
            return str(path).replace("\\", "/")

    def _build_benchmark_data(self, exclude_symbol: Optional[str] = None) -> Tuple[str, Dict[str, str]]:
        """
        拼接 SPY/QQQ/DIA 的技术分析文本为单个 benchmark_data 字符串。
        若 exclude_symbol 命中 BENCHMARK_SYMBOLS（例如分析SPY时），则跳过该基准，避免数据重复。
        返回: (拼接文本, 各基准对应文件路径dict)
        """
        max_age = self._get_max_age('technical_analysis')
        ta_dir = self.full_cfg.get('technical_analysis', {}).get('output_dir')

        sections: List[str] = []
        used_paths: Dict[str, str] = {}
        exclude_upper = (exclude_symbol or "").upper()

        for sym in BENCHMARK_SYMBOLS:
            if sym == exclude_upper:
                continue
            p = self._find_latest(f"{ta_dir}/{sym}", f"{sym}_technical_*.json", max_age)
            if not p:
                continue
            content = self._read_file(p)
            sections.append(f"#### {sym} 技术分析\n{content}")
            used_paths[sym] = self._get_path_str(p)

        return "\n\n".join(sections), used_paths

    def assemble_general(self, exclude_symbol: Optional[str] = None) -> Tuple[Dict, Dict]:
        raw = {}
        paths = { "macro": {}, "benchmarks": {}, "symbol": {} }

        max_age = self._get_max_age('news')
        news_dir = self.full_cfg.get('news', {}).get('cache_dir', 'data/news')
        p = self._find_latest(f"{news_dir}/GENERAL", "GENERAL_news_*.json", max_age)
        if p:
            raw["general_news_data"] = self._read_file(p)
            paths["macro"]["general_news"] = self._get_path_str(p)

        max_age = self._get_max_age('economic_indicators')
        econ_dir = self.full_cfg.get('economic_indicators', {}).get('cache_dir')
        p = self._find_latest(econ_dir, "economic_indicators_*.json", max_age)
        if p:
            raw["macro_data"] = self._read_file(p)
            paths["macro"]["economic"] = self._get_path_str(p)

        max_age = self._get_max_age('fear_greed')
        fg_dir = self.full_cfg.get('fear_greed', {}).get('cache_dir')
        p = self._find_latest(fg_dir, "fear_greed_latest_*.json", max_age)
        if p:
            raw["fear_greed_data"] = self._read_file(p)
            paths["macro"]["fear_greed"] = self._get_path_str(p)

        # 基准ETF（SPY/QQQ/DIA）合并为 benchmark_data 字段，命中自己时跳过
        bench_text, bench_paths = self._build_benchmark_data(exclude_symbol=exclude_symbol)
        raw["benchmark_data"] = bench_text
        paths["benchmarks"] = bench_paths

        return raw, paths

    def assemble_stock(self, symbol: str) -> Tuple[Dict, Dict]:
        # 传入当前 symbol，若它是 SPY/QQQ/DIA 之一则在基准里排除，避免重复数据
        raw, paths = self.assemble_general(exclude_symbol=symbol)
        
        clean_sym = symbol.upper().replace(" ", ".")
        raw["symbol"] = clean_sym
        
        max_age = self._get_max_age('technical_analysis')
        ta_dir = self.full_cfg.get('technical_analysis', {}).get('output_dir')
        p = self._find_latest(f"{ta_dir}/{clean_sym}", f"{clean_sym}_technical_*.json", max_age)
        if p:
            raw["tech_data"] = self._read_file(p)
            paths["symbol"]["technical"] = self._get_path_str(p)

        max_age = self._get_max_age('alpha_fundamentals')
        fund_dir = self.full_cfg.get('alpha_fundamentals', {}).get('cache_dir')
        if fund_dir:
            p = self._find_latest(f"{fund_dir}/{clean_sym}", f"{clean_sym}_fundamentals_*.json", max_age)
            if p:
                content = self._read_file(p)
                raw["fundamentals_data"] = content
                paths["symbol"]["fundamentals"] = self._get_path_str(p)
                try:
                    js = json.loads(content)
                    for k in ["General", "CompanyProfile", "profile"]:
                        if k in js:
                            raw["profile_data"] = json.dumps(js[k], ensure_ascii=False)
                            break
                except: pass
        
        if "profile_data" not in raw: raw["profile_data"] = "{}"

        max_age = self._get_max_age('news')
        news_dir = self.full_cfg.get('news', {}).get('cache_dir')
        p = self._find_latest(f"{news_dir}/{clean_sym}", f"{clean_sym}_news_*.json", max_age)
        if p:
            raw["news_data"] = self._read_file(p)
            paths["symbol"]["news"] = self._get_path_str(p)

        return raw, paths

    def is_general_data_fresh(self, max_age_seconds: float) -> bool:
        """检查GENERAL依赖的基准ETF(SPY/QQQ/DIA)技术分析数据是否在阈值内"""
        ta_dir = self.full_cfg.get('technical_analysis', {}).get('output_dir')
        if not ta_dir:
            return False

        for sym in BENCHMARK_SYMBOLS:
            dir_path = self.root / ta_dir / sym
            if not dir_path.exists():
                return False
            files = list(dir_path.glob(f"{sym}_technical_*.json"))
            if not files:
                return False
            latest = max(files, key=lambda f: f.stat().st_mtime)
            age = time.time() - latest.stat().st_mtime
            if age > max_age_seconds:
                return False

        return True


# ──────────────────────────────────────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────────────────────────────────────

def chunk_list(data: list, size: int):
    """将列表切割为指定大小的子列表"""
    for i in range(0, len(data), size):
        yield data[i:i + size]


def fetch_and_calc_batch(
    symbols: List[str],
    symbols_config: Dict,
    include_benchmarks: bool = False
):
    """
    为一组标的串行下载IBKR数据并计算技术指标。
    每个batch独立连接/断开。

    Args:
        symbols: 需要下载的标的列表 (不含GENERAL)
        symbols_config: symbols.yaml配置
        include_benchmarks: 是否同时下载基准ETF(SPY/QQQ/DIA)，用于刷新GENERAL数据
    """
    # 构建下载列表: 基准ETF排最前面，确保GENERAL依赖数据先就绪
    download_list = []
    if include_benchmarks:
        for sym in BENCHMARK_SYMBOLS:
            if sym not in symbols:
                download_list.append(sym)
    download_list.extend(symbols)
    
    if not download_list:
        return

    logging.info(f"📥 [Batch Fetch] Downloading: {download_list}")
    
    md_config = MarketDataConfig.from_yaml(str(PROJECT_ROOT / "config/data_sources.yaml"))
    fetcher = MarketDataFetcher(md_config)
    contracts_def = symbols_config.get('symbol_contracts', {})
    
    connected = False
    try:
        connected = fetcher.connect_and_start(
            host="127.0.0.1", port=7496,
            client_id=random.randint(1000, 9999)
        )
        if not connected:
            logging.warning("⚠️ IBKR Connect failed. Will use cached data.")
    except Exception as e:
        logging.warning(f"⚠️ IBKR Connection error: {e}")

    try:
        # 串行下载 (盈透单线程限制)
        for sym in download_list:
            c_info = contracts_def.get(sym)
            if not c_info:
                logging.warning(f"  ⚠️ No contract config for {sym}, skipping fetch.")
                continue
            
            if connected:
                logging.info(f"  [Fetching] {sym}...")
                contract = SymbolContract(
                    symbol=c_info['symbol'],
                    sec_type=c_info['sec_type'],
                    exchange=c_info['exchange'],
                    currency=c_info['currency']
                )
                try:
                    fetcher.fetch_multi_resolutions(contract, force_refresh=True)
                except Exception as e:
                    logging.error(f"  [Fetch Error] {sym}: {e}")
            
            # 无论下载是否成功，都尝试重算指标 (可能用缓存)
            try:
                process_symbol_technical_analysis(sym, force_update=True)
            except Exception as e:
                logging.error(f"  [Calc Error] {sym}: {e}")

    finally:
        if connected:
            fetcher.disconnect_and_stop()
            logging.info("🔌 [Batch Fetch] IBKR Disconnected.")


# ──────────────────────────────────────────────────────────────────────────────
# 去重逻辑
# ──────────────────────────────────────────────────────────────────────────────

def _extract_ts_from_path(path_str: str) -> str:
    """提取文件名中的 ISO 8601 时间戳字符串 (YYYYMMDDTHHMMSSZ)"""
    if not path_str: return ""
    try:
        stem = Path(path_str).stem
        parts = stem.split('_')
        candidate = parts[-1]
        if ("T" in candidate and candidate.endswith("Z")) or candidate.isdigit():
            return candidate
        return ""
    except:
        return ""

def _check_analysis_exists(symbol: str, data_ts: str, data_config: Dict) -> bool:
    """检查是否已存在基于该数据版本的分析报告"""
    if not data_ts: return False
    
    base_out_dir = data_config.get('data_sources', {}).get('ai_analysis', {}).get('output_dir', 'data/debate')
    # [修复] 搜索子目录 output_dir/SYMBOL/
    symbol_dir = Path(PROJECT_ROOT) / base_out_dir / symbol.upper()
    
    if not symbol_dir.exists(): return False
    
    sym_pattern = f"{symbol}_Analysis_*.json"
    files = list(symbol_dir.glob(sym_pattern))
    if not files: return False
    
    latest_analysis = max(files, key=lambda f: f.name)
    latest_analysis_ts = _extract_ts_from_path(latest_analysis.name)
    
    return latest_analysis_ts >= data_ts


# ──────────────────────────────────────────────────────────────────────────────
# LLM辩论任务
# ──────────────────────────────────────────────────────────────────────────────

def run_debate_sync(engine, assembler, symbol: str, ctx_type: str, data_config: Dict):
    """
    同步执行单个标的的辩论任务。
    包含数据组装、完整性检查、去重检查、引擎调用。
    """
    # 1. 组装数据
    if symbol == "GENERAL":
        raw_data, paths = assembler.assemble_general()
    else:
        raw_data, paths = assembler.assemble_stock(symbol)
    
    # 2. 完整性检查
    if symbol != "GENERAL" and "tech_data" not in raw_data:
        logging.warning(f"⚠️ [Skip Debate] {symbol}: Tech Data missing or expired.")
        return
    
    # 3. 提取数据时间戳
    data_ts = ""
    if ctx_type == 'general':
        benchmarks = paths.get("benchmarks", {})
        ts_list = []
        for sym in BENCHMARK_SYMBOLS:
            ts = _extract_ts_from_path(benchmarks.get(sym))
            if ts: ts_list.append(ts)
        if ts_list: data_ts = max(ts_list)
    else:
        tech_path = paths.get("symbol", {}).get("technical")
        data_ts = _extract_ts_from_path(tech_path)
    
    # 4. 去重检查
    if data_ts and _check_analysis_exists(symbol, data_ts, data_config):
        logging.info(f"⏭️ [Skip Debate] {symbol}: Fresh analysis exists ({data_ts})")
        return
    
    # 5. 执行辩论
    logging.info(f"🚀 [Debate Start] {symbol} ({ctx_type}) | DataTS: {data_ts}")
    engine.run(symbol, ctx_type, raw_data, paths, 10)
    logging.info(f"✅ [Debate Done] {symbol}")


# ──────────────────────────────────────────────────────────────────────────────
# Phase 2: 分组滚轮执行 (Rolling Batch)
# ──────────────────────────────────────────────────────────────────────────────

async def run_analysis_phase(symbols_map: Dict, data_config: Dict, symbols_config: Dict):
    logging.info("\n>>> Phase 2: Rolling AI Debate (JIT Mode) <<<")
    
    engine = DebateEngine()
    assembler = ContextAssembler(data_config)
    
    # GENERAL数据过期阈值: 从yaml读 technical_analysis.max_file_age (默认3600s=1h)
    general_max_age = float(
        data_config.get('data_sources', {})
        .get('technical_analysis', {})
        .get('max_file_age', 3600)
    )
    
    # --- 1. 准备标的名单 (不含GENERAL)，随机洗牌 ---
    all_targets = []
    for s in symbols_map["stocks"]: all_targets.append((s, "stock"))
    for s in symbols_map["etfs"]:   all_targets.append((s, "etf"))
    random.shuffle(all_targets)
    
    # --- 2. 分组 ---
    batches = list(chunk_list(all_targets, BATCH_SIZE))
    if not batches:
        batches = [[]]
    
    # GENERAL的LLM辩论固定插入第一组
    batches[0].insert(0, ("GENERAL", "general"))

    total_targets = sum(len(b) for b in batches)
    logging.info(f"📊 Plan: {total_targets} targets split into {len(batches)} batches. "
                 f"(GENERAL LLM in batch 1)")

    # --- 3. 逐batch执行 ---
    loop = asyncio.get_running_loop()
    
    for i, batch in enumerate(batches):
        logging.info(f"\n⚡ Processing Batch {i+1}/{len(batches)} (Size: {len(batch)})")
        
        # 提取本组需要IBKR下载的标的 (排除GENERAL，GENERAL的指数数据单独处理)
        ibkr_symbols = [sym for sym, _ in batch if sym != "GENERAL"]
        
        # --- 步骤A: 每个batch都先检查GENERAL依赖数据(基准ETF)是否需要刷新 ---
        need_refresh_benchmarks = not assembler.is_general_data_fresh(general_max_age)
        if need_refresh_benchmarks:
            logging.info(f"🔄 [General Guard] Benchmark data stale (>{general_max_age:.0f}s), will refresh {BENCHMARK_SYMBOLS}.")
        else:
            logging.info(f"✅ [General Guard] Benchmark data fresh, skipping benchmark download.")

        # --- 步骤B: JIT数据下载 (串行，每batch独立连接) ---
        # 基准ETF (SPY/QQQ/DIA) 排在最前面下载，然后才是本组标的
        await loop.run_in_executor(
            None,
            fetch_and_calc_batch,
            ibkr_symbols,
            symbols_config,
            need_refresh_benchmarks  # include_benchmarks
        )
        
        # --- 步骤C: LLM辩论，错开启动 ---
        execution_queue = [(sym, ctx) for sym, ctx in batch]
        logging.info(f"   Execution Queue: {[s for s, _ in execution_queue]}")
        
        tasks = []
        for idx, (symbol, ctx_type) in enumerate(execution_queue):
            # 用 run_in_executor 把同步的辩论任务丢到线程池
            task = loop.run_in_executor(
                None,
                run_debate_sync,
                engine, assembler, symbol, ctx_type, data_config
            )
            tasks.append(task)
            
            # 错开启动: 非最后一个任务，等一下再发下一个
            if idx < len(execution_queue) - 1:
                await asyncio.sleep(TASK_STAGGER_SECONDS)
        
        # 等待本batch所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 记录异常
        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                sym = execution_queue[idx][0]
                logging.error(f"❌ [Debate Error] {sym}: {result}")
        
        logging.info(f"✅ Batch {i+1}/{len(batches)} Completed.")
        
        # batch间冷却 (最后一组不需要)
        if i < len(batches) - 1:
            await asyncio.sleep(5)
    
    logging.info("🏁 All batches completed.")


# ──────────────────────────────────────────────────────────────────────────────
# Main Entry
# ──────────────────────────────────────────────────────────────────────────────

def load_helpers():
    d_cfg = yaml.safe_load(open(PROJECT_ROOT / "config/data_sources.yaml", encoding='utf-8'))
    s_cfg = yaml.safe_load(open(PROJECT_ROOT / "config/symbols.yaml", encoding='utf-8'))
    t = s_cfg.get('analysis_targets', {})
    s_map = {
        "stocks": [s.upper() for s in t.get('stocks', [])],
        "etfs": [s.upper() for s in t.get('etfs', [])],
        "benchmarks": [s.upper() for s in t.get('benchmarks', [])],
    }
    return d_cfg, s_cfg, s_map

def main():
    logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

    parser = argparse.ArgumentParser()
    parser.add_argument("--run-once", action="store_true", help="立即执行一次分析，不进入守护模式")
    args = parser.parse_args()
    
    data_config, symbols_config, symbols_map = load_helpers()
    
    calendar = get_trading_calendar('NYSE')
    
    # --run-once: 立即执行一轮
    if args.run_once:
        logging.info("🚀 Run-Once Mode: Executing single analysis round...")
        asyncio.run(run_analysis_phase(symbols_map, data_config, symbols_config))
        logging.info("✅ Run-Once Complete.")
        sys.exit(0)
    
    # 守护模式
    executed = set()
    last_date = None
    
    logging.info("Sentinel Started (Daemon Mode - Rolling Batch)")
    while True:
        now = get_now_et()
        
        if last_date != now.date():
            executed.clear()
            last_date = now.date()
        
        if is_trading_day(calendar, now):
            for t in RUN_TIMES:
                t_str = t.strftime("%H:%M")
                if t_str in executed:
                    continue
                
                sched = datetime.combine(now.date(), t, tzinfo=EASTERN)
                
                if 0 <= (now - sched).total_seconds() <= 900:
                    logging.info(f"⏰ Triggering Scheduled Run: {t_str}")
                    asyncio.run(run_analysis_phase(symbols_map, data_config, symbols_config))
                    executed.add(t_str)
        else:
            if executed:
                logging.info("Non-trading day detected. Clearing executed list.")
                executed.clear()
        
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()