"""
Data Scheduler (V3.5 - Simplified & Root Compatible)

职责: 唯一职责是作为“生产者”，按计划调用所有数据获取模块，
填充 data/ 目录。

变更 (V3.5):
1. 适配 Fear & Greed 新版 YAML 结构 (扁平化 cooldown)。
2. 移除 Fear & Greed 历史数据下载逻辑。
3. 保持 Finnhub 涓流模式和路径兼容性。
"""

import logging
import sys
import time
import random
from datetime import datetime, timedelta, time as dt_time
from pathlib import Path
from typing import Dict, Any, List

import pandas_market_calendars as mcal
import pytz
import yaml
from apscheduler.schedulers.blocking import BlockingScheduler

# ─────────────────────────── 路径与环境设置 ─────────────────────────── #

def resolve_project_root() -> Path:
    """
    智能查找项目根目录。
    """
    current_path = Path(__file__).resolve()
    
    # 1. 检查脚本所在目录 (根目录运行场景)
    if (current_path.parent / "config").exists() and (current_path.parent / "data").exists():
        return current_path.parent

    # 2. 向上查找 (子目录运行场景)
    for parent in current_path.parents:
        if (parent / "config").exists() and (parent / "data").exists():
            return parent
            
    # Fallback: 默认向上两级
    return current_path.parents[1]

PROJECT_ROOT = resolve_project_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

print(f"[DataScheduler] Project Root resolved to: {PROJECT_ROOT}")

# ─────────────────────────── 导入 Fetchers ─────────────────────────── #
try:
    # --- Fear & Greed (已简化，只导入 latest) ---
    from fetchers.fear_greed_fetcher import download_latest as download_fg_latest

    # --- Alpha Vantage Economic ---
    from fetchers.alpha_economic_fetcher import AlphaEconomicFetcher

    # --- Finnhub News ---
    from fetchers.finnhub_news_fetcher import FinnhubNewsFetcher

    # --- Alpha Fundamental (可选) ---
    try:
        from fetchers.alpha_fundamental_fetcher import AlphaFundamentalFetcher
        HAS_FUNDAMENTALS = True
    except ImportError:
        HAS_FUNDAMENTALS = False
        print("⚠️ AlphaFundamentalFetcher not found. Fundamentals job will be skipped.")

except ImportError as e:
    print(f"CRITICAL ERROR: Failed to import fetcher modules. {e}")
    print("Hint: Ensure 'data' is a python package (has __init__.py) or sys.path is correct.")
    sys.exit(1)

# --- 全局配置 ---
CONFIG_SOURCES_PATH = PROJECT_ROOT / "config" / "data_sources.yaml"
CONFIG_SYMBOLS_PATH = PROJECT_ROOT / "config" / "symbols.yaml"

SCHEDULER_TIMEZONE = pytz.timezone('America/New_York')
START_TIME_ET = dt_time(6, 0, 0) # 启动时间基准：美东 6:00 AM

# --- 日志配置 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)-8s] (%(name)s) %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logging.getLogger('apscheduler.executors.default').setLevel(logging.WARNING)
logging.getLogger('apscheduler.schedulers.blocking').setLevel(logging.INFO)
logger = logging.getLogger("DataScheduler")


# ─────────────────────────── 辅助函数 ─────────────────────────── #

def load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        logger.critical(f"YAML config file not found: {path}. Exiting.")
        sys.exit(1)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.critical(f"Error loading YAML {path}: {e}", exc_info=True)
        sys.exit(1)

def get_trading_calendar(exchange: str = 'NYSE') -> mcal.MarketCalendar:
    try:
        return mcal.get_calendar(exchange)
    except Exception as e:
        logger.critical(f"Failed to get trading calendar: {e}")
        sys.exit(1)

def is_trading_day(calendar: mcal.MarketCalendar, check_date: datetime) -> bool:
    date_str = check_date.strftime('%Y-%m-%d')
    try:
        schedule = calendar.schedule(start_date=date_str, end_date=date_str)
        return not schedule.empty
    except Exception as e:
        logger.warning(f"Failed to check trading day for {date_str}: {e}. Defaulting to True.")
        return True

def find_next_start_date(calendar: mcal.MarketCalendar) -> datetime:
    now_et = datetime.now(SCHEDULER_TIMEZONE)
    start_date = now_et.date()

    if now_et.time() > START_TIME_ET:
        start_date += timedelta(days=1)

    try:
        valid_days = calendar.valid_days(
            start_date=start_date,
            end_date=start_date + timedelta(days=10)
        )
        next_trading_date = valid_days[0].date()
    except IndexError:
        logger.critical("Failed to find next trading day in the next 10 days.")
        sys.exit(1)
    
    first_run_time = SCHEDULER_TIMEZONE.localize(
        datetime.combine(next_trading_date, START_TIME_ET)
    )
    return first_run_time


# ─────────────────────────── 任务逻辑 ─────────────────────────── #

def run_fear_greed_job(scheduler: BlockingScheduler, configs: Dict, calendar: mcal.MarketCalendar):
    """
    (V3.5 Update) 适配扁平化 YAML 配置，只调用 download_latest
    """
    job_name = "FearGreed"
    logger.info(f"--- Triggered Job: {job_name} ---")
    
    cfg = configs['data_sources'].get('fear_greed', {})
    
    now_et = datetime.now(SCHEDULER_TIMEZONE)
    if not is_trading_day(calendar, now_et):
        logger.info(f"{job_name}: Skipped (Not a trading day).")
    else:
        try:
            # 这里的 config_path 是为了确保 fetcher 能找到配置文件（如果不在默认位置）
            download_fg_latest(config_path=CONFIG_SOURCES_PATH)
            logger.info(f"{job_name}: Task complete.")
        except Exception as e:
            logger.error(f"{job_name}: Failed: {e}", exc_info=True)

    # V3.5 修正：直接获取 cooldown，不再嵌套
    cooldown = cfg.get('cooldown', 86400) 
    
    next_run = datetime.now(pytz.utc) + timedelta(seconds=cooldown)
    scheduler.add_job(run_fear_greed_job, 'date', run_date=next_run, args=[scheduler, configs, calendar])
    logger.info(f"{job_name}: Next run: {next_run.astimezone(SCHEDULER_TIMEZONE)}")


def run_economic_job(scheduler: BlockingScheduler, configs: Dict, calendar: mcal.MarketCalendar):
    job_name = "AlphaEconomic"
    logger.info(f"--- Triggered Job: {job_name} ---")

    cfg = configs['data_sources'].get('economic_indicators', {})
    
    now_et = datetime.now(SCHEDULER_TIMEZONE)
    if not is_trading_day(calendar, now_et):
        logger.info(f"{job_name}: Skipped (Not a trading day).")
    else:
        try:
            fetcher = AlphaEconomicFetcher(config_path=CONFIG_SOURCES_PATH) 
            fetcher.download_all_data()
            logger.info(f"{job_name}: Tasks complete.")
        except Exception as e:
            logger.error(f"{job_name}: Failed: {e}", exc_info=True)

    cooldown = cfg.get('cooldown', 86400)
    next_run = datetime.now(pytz.utc) + timedelta(seconds=cooldown)
    scheduler.add_job(run_economic_job, 'date', run_date=next_run, args=[scheduler, configs, calendar])
    logger.info(f"{job_name}: Next run: {next_run.astimezone(SCHEDULER_TIMEZONE)}")


def run_fundamentals_job(scheduler: BlockingScheduler, configs: Dict, calendar: mcal.MarketCalendar):
    job_name = "AlphaFundamentals"
    
    if not HAS_FUNDAMENTALS:
        logger.warning(f"{job_name}: Module not found. Skipping.")
        return

    logger.info(f"--- Triggered Job: {job_name} ---")
    
    cfg = configs['data_sources'].get('alpha_fundamentals', {})
    symbols_cfg = configs['symbols'].get('analysis_targets', {})
    
    now_et = datetime.now(SCHEDULER_TIMEZONE)
    if not is_trading_day(calendar, now_et):
        logger.info(f"{job_name}: Skipped (Not a trading day).")
    else:
        try:
            fetcher = AlphaFundamentalFetcher()
            stock_list = [s.upper() for s in symbols_cfg.get('stocks', [])]
            random.shuffle(stock_list)
            
            for symbol in stock_list:
                fetcher.download_fundamentals(symbol)
                time.sleep(15) 
                
            logger.info(f"{job_name}: Tasks complete.")
        except Exception as e:
            logger.error(f"{job_name}: Failed: {e}", exc_info=True)

    cooldown = cfg.get('cooldown', 86400) 
    next_run = datetime.now(pytz.utc) + timedelta(seconds=cooldown)
    scheduler.add_job(run_fundamentals_job, 'date', run_date=next_run, args=[scheduler, configs, calendar])
    logger.info(f"{job_name}: Next run: {next_run.astimezone(SCHEDULER_TIMEZONE)}")


def run_finnhub_news_job(scheduler: BlockingScheduler, configs: Dict, calendar: mcal.MarketCalendar):
    job_name = "FinnhubNews"
    logger.info(f"--- Triggered Job: {job_name} ---")

    cfg = configs['data_sources'].get('news', {})
    symbols_cfg = configs['symbols'].get('analysis_targets', {})
    
    if not cfg or not symbols_cfg: 
        logger.warning(f"{job_name}: Missing config.")
        return

    now_et = datetime.now(SCHEDULER_TIMEZONE)
    if not is_trading_day(calendar, now_et):
        logger.info(f"{job_name}: Skipped (Not a trading day).")
    else:
        try:
            key1 = cfg.get('api_key1')
            key2 = cfg.get('api_key2')
            if not key1 or not key2:
                raise ValueError("API keys missing in config")

            fetcher1 = FinnhubNewsFetcher(api_key=key1, config_path=str(CONFIG_SOURCES_PATH))
            fetcher2 = FinnhubNewsFetcher(api_key=key2, config_path=str(CONFIG_SOURCES_PATH))
            
            stock_list = [s.upper() for s in symbols_cfg.get('stocks', [])]
            etf_list = [s.upper() for s in symbols_cfg.get('etfs', [])]
            
            tasks = stock_list + etf_list + ['GENERAL']
            random.shuffle(tasks)
            
            logger.info(f"{job_name}: Processing {len(tasks)} tasks (Shuffle + Trickle Mode).")

            chunk_size = 6
            group_size = 3 
            MICRO_DELAY = 5 
            MACRO_DELAY = 65 

            for i in range(0, len(tasks), chunk_size):
                try:
                    chunk = tasks[i : i + chunk_size]
                    group1 = chunk[0 : group_size]
                    group2 = chunk[group_size : chunk_size]
                    
                    # --- Key 1 Group ---
                    for symbol in group1:
                        try:
                            if symbol == 'GENERAL': 
                                fetcher1.download_general_news('GENERAL')
                            else: 
                                fetcher1.download_company_news(symbol) 
                            logger.info(f"  [Key1] Fetched {symbol}. Nap {MICRO_DELAY}s...")
                            time.sleep(MICRO_DELAY)
                        except Exception as e:
                            logger.error(f"{job_name}: [Key1] Failed for {symbol}: {e}")

                    # --- Key 2 Group ---
                    for symbol in group2:
                        try:
                            if symbol == 'GENERAL': 
                                fetcher2.download_general_news('GENERAL')
                            else: 
                                fetcher2.download_company_news(symbol) 
                            logger.info(f"  [Key2] Fetched {symbol}. Nap {MICRO_DELAY}s...")
                            time.sleep(MICRO_DELAY)
                        except Exception as e:
                            logger.error(f"{job_name}: [Key2] Failed for {symbol}: {e}")
                
                except Exception as batch_e:
                    logger.error(f"{job_name}: Batch critical error: {batch_e}")

                if (i + chunk_size < len(tasks)):
                    logger.info(f"{job_name}: Batch done. Cooling down {MACRO_DELAY}s...")
                    time.sleep(MACRO_DELAY)

            logger.info(f"{job_name}: Tasks complete.")

        except Exception as e:
            logger.error(f"{job_name}: Job Critical Failed: {e}", exc_info=True)

    cooldown = cfg.get('cooldown', 3600) 
    next_run = datetime.now(pytz.utc) + timedelta(seconds=cooldown)
    scheduler.add_job(run_finnhub_news_job, 'date', run_date=next_run, args=[scheduler, configs, calendar])
    logger.info(f"{job_name}: Next run: {next_run.astimezone(SCHEDULER_TIMEZONE)}")


# ─────────────────────────── 启动逻辑 ─────────────────────────── #

def start_scheduler():
    logger.info("==============================================")
    logger.info("Initializing Data Scheduler (V3.5 Root Compatible)")
    logger.info(f"Config Path: {CONFIG_SOURCES_PATH}")
    logger.info("==============================================")
    
    configs = {
        'data_sources': load_yaml(CONFIG_SOURCES_PATH).get('data_sources', {}),
        'symbols': load_yaml(CONFIG_SYMBOLS_PATH)
    }
    calendar = get_trading_calendar('NYSE')
    
    first_run_time = find_next_start_date(calendar)
    
    # 错峰启动
    run_time_finnhub = first_run_time
    run_time_feargreed = first_run_time + timedelta(minutes=3)
    run_time_av_economic = first_run_time + timedelta(minutes=5)
    run_time_av_funds = first_run_time + timedelta(minutes=8)
    
    logger.info(f"Base Start Time (ET): {first_run_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    
    scheduler = BlockingScheduler(timezone=pytz.utc) 
    
    scheduler.add_job(run_fear_greed_job, 'date', run_date=run_time_feargreed, args=[scheduler, configs, calendar])
    scheduler.add_job(run_finnhub_news_job, 'date', run_date=run_time_finnhub, args=[scheduler, configs, calendar])
    scheduler.add_job(run_economic_job, 'date', run_date=run_time_av_economic, args=[scheduler, configs, calendar])
    
    if HAS_FUNDAMENTALS:
        scheduler.add_job(run_fundamentals_job, 'date', run_date=run_time_av_funds, args=[scheduler, configs, calendar])
    
    logger.info("--- Scheduler initialized. Waiting for trigger... ---")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")

if __name__ == "__main__":
    start_scheduler()