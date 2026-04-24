#!/usr/bin/env python3
"""
analysis/technical_snapshot_builder.py

(V15.0 - Session-Aware Schema)
Unified technical snapshot JSON builder with session awareness (pre-market/regular/after-hours/closed).

V15.0 changes:
- Session classified from the latest 1m bar's timestamp (not datetime.now()); DST and early-close days handled via pandas_market_calendars.
- New top-level blocks: instrument_metadata + session_context.
- Features regrouped by data completeness: current_snapshot / daily_technicals / hourly_technicals / weekly_snapshot / positioning / cross_timeframe_summary / price_structure.
- Session-specific fields are set to null when not applicable (change_since_regular_open_pct / vwap_dist_pct / volume_ratio_vs_20d_daily_avg).
- Field renames: last_close->last_price, daily_change_percent->change_vs_prior_regular_close_pct,
  intraday_trend_vs_open->change_since_regular_open_pct, intraday_vwap_dist_pct->vwap_dist_pct,
  volume_ratio_vs_avg_daily->volume_ratio_vs_20d_daily_avg, intraday_volume_ratio_vs_avg->volume_ratio_5m_vs_20bar_avg.
"""

from __future__ import annotations

import json
import math
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

import pandas as pd
import pandas_market_calendars as mcal
import pandas_ta as ta
import yaml

# 导入趋势分析模块
try:
    from .trend_analyzer import calculate_swing_points, calculate_simplified_trend
except ImportError:
    # Fallback for standalone testing
    from trend_analyzer import calculate_swing_points, calculate_simplified_trend


# ──────────────────────────── Logging Setup ──────────────────────────── #

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)


# ───────────────────── Feature Set & Grouping (V15.0) ───────────────────── #

FEATURE_GROUP_MAP = {
    # --- current_snapshot: live session-aware data ---
    "last_price": "current_snapshot",
    "last_wap": "current_snapshot",
    "change_vs_prior_regular_close_pct": "current_snapshot",
    "change_since_regular_open_pct": "current_snapshot",       # regular / after-hours only; else null
    "vwap_dist_pct": "current_snapshot",                        # regular only; else null
    "volume_ratio_vs_20d_daily_avg": "current_snapshot",        # null during pre-market (partial-day volume misleads)
    "volume_ratio_5m_vs_20bar_avg": "current_snapshot",
    "price_change_pct_5m": "current_snapshot",
    "rsi_14_5min": "current_snapshot",
    "atr_14_5min": "current_snapshot",
    "liquidity_score_vol_per_bar": "current_snapshot",

    # --- daily_technicals: 日线级指标 ---
    "ma_20_daily_val": "daily_technicals",
    "ma_50_daily_val": "daily_technicals",
    "ma_200_daily_val": "daily_technicals",
    "rsi_14_daily": "daily_technicals",
    "macd_hist_daily": "daily_technicals",
    "atr_14_daily_percent": "daily_technicals",
    "bb_pct_b_daily": "daily_technicals",
    "bb_width_pct_daily": "daily_technicals",
    "ma_cross_status": "daily_technicals",
    "ma_alignment": "daily_technicals",
    "obv_slope_5d": "daily_technicals",
    "volatility_regime_daily": "daily_technicals",
    "recent_gaps": "daily_technicals",
    "consolidation_days": "daily_technicals",

    # --- hourly_technicals ---
    "ma_20_hourly_val": "hourly_technicals",
    "ma_50_hourly_val": "hourly_technicals",
    "ma_20_slope_pct_hourly": "hourly_technicals",
    "rsi_14_hourly": "hourly_technicals",
    "macd_hist_hourly": "hourly_technicals",
    "atr_14_hourly": "hourly_technicals",
    "bb_pct_b_hourly": "hourly_technicals",
    "volume_ratio_vs_avg_hourly": "hourly_technicals",

    # --- weekly_snapshot ---
    "ma_40_weekly_val": "weekly_snapshot",
    "ma_200_weekly_val": "weekly_snapshot",

    # --- positioning ---
    "percent_from_52w_high_low": "positioning",
    "nearest_support_resistance": "positioning",
    "max_drawdown_30d": "positioning",
    "sharpe_ratio_30d": "positioning",
    "relative_strength_vs_spy": "positioning",
    "correlation_vs_spy": "positioning",
    "beta": "positioning",

    # --- cross_timeframe_summary ---
    "cross_timeframe_trend_alignment": "cross_timeframe_summary",
    "cross_timeframe_momentum_score": "cross_timeframe_summary",

    # --- price_structure (nested) ---
    "price_structure_tactical": "price_structure",
    "price_structure_strategic": "price_structure",
    "micro_flow_engine": "price_structure",
}

# Subkey mapping under "price_structure" (strip legacy prefix)
PRICE_STRUCTURE_SUBKEY = {
    "price_structure_tactical": "tactical",
    "price_structure_strategic": "strategic",
    "micro_flow_engine": "micro_flow_engine",
}

UNIFIED_FEATURES = list(FEATURE_GROUP_MAP.keys())


# ───────────────────── Session Classification (V15.0) ───────────────────── #

PREMARKET_START_ET_HOUR = 4   # 04:00 ET
AFTERHOURS_END_ET_HOUR = 20   # 20:00 ET

_NYSE_CALENDAR = None

def get_nyse_calendar():
    global _NYSE_CALENDAR
    if _NYSE_CALENDAR is None:
        _NYSE_CALENDAR = mcal.get_calendar('NYSE')
    return _NYSE_CALENDAR


def classify_session(bar_ts_utc: pd.Timestamp) -> Dict[str, Any]:
    """
    Classify the market session for a UTC bar timestamp.
    Regular-session bounds come from the NYSE calendar (DST + early-close aware).
      pre-market:  04:00 ET -> reg_open
      after-hours: reg_close -> 20:00 ET
    """
    if bar_ts_utc.tzinfo is None:
        bar_ts_utc = bar_ts_utc.tz_localize('UTC')
    else:
        bar_ts_utc = bar_ts_utc.tz_convert('UTC')

    et_ts = bar_ts_utc.tz_convert('America/New_York')
    date_et = et_ts.date()

    nyse = get_nyse_calendar()
    schedule = nyse.schedule(start_date=date_et, end_date=date_et)

    if schedule.empty:
        return {
            "current_session": "closed",
            "elapsed_minutes": None,
            "latest_bar_et": et_ts.isoformat(),
            "reg_open_utc": None,
            "reg_close_utc": None,
        }

    reg_open_utc = pd.Timestamp(schedule.iloc[0]['market_open']).tz_convert('UTC')
    reg_close_utc = pd.Timestamp(schedule.iloc[0]['market_close']).tz_convert('UTC')

    premarket_start_utc = pd.Timestamp(
        datetime(date_et.year, date_et.month, date_et.day, PREMARKET_START_ET_HOUR)
    ).tz_localize('America/New_York').tz_convert('UTC')
    afterhours_end_utc = pd.Timestamp(
        datetime(date_et.year, date_et.month, date_et.day, AFTERHOURS_END_ET_HOUR)
    ).tz_localize('America/New_York').tz_convert('UTC')

    if bar_ts_utc < premarket_start_utc or bar_ts_utc >= afterhours_end_utc:
        session = "closed"
        elapsed = None
    elif bar_ts_utc < reg_open_utc:
        session = "pre-market"
        elapsed = int((bar_ts_utc - premarket_start_utc).total_seconds() / 60)
    elif bar_ts_utc < reg_close_utc:
        session = "regular"
        elapsed = int((bar_ts_utc - reg_open_utc).total_seconds() / 60)
    else:
        session = "after-hours"
        elapsed = int((bar_ts_utc - reg_close_utc).total_seconds() / 60)

    return {
        "current_session": session,
        "elapsed_minutes": elapsed,
        "latest_bar_et": et_ts.isoformat(),
        "reg_open_utc": reg_open_utc,
        "reg_close_utc": reg_close_utc,
    }


def get_prior_regular_close_et(bar_ts_utc: pd.Timestamp) -> Optional[str]:
    """Close timestamp (ET ISO string) of the most recent completed regular session."""
    if bar_ts_utc.tzinfo is None:
        bar_ts_utc = bar_ts_utc.tz_localize('UTC')
    else:
        bar_ts_utc = bar_ts_utc.tz_convert('UTC')

    nyse = get_nyse_calendar()
    end_date = bar_ts_utc.tz_convert('America/New_York').date()
    start_date = end_date - pd.Timedelta(days=14)
    schedule = nyse.schedule(start_date=start_date, end_date=end_date)

    if schedule.empty:
        return None

    completed = schedule[schedule['market_close'] < bar_ts_utc]
    if completed.empty:
        return None

    last_close = pd.Timestamp(completed.iloc[-1]['market_close'])
    if last_close.tzinfo is None:
        last_close = last_close.tz_localize('UTC')
    return last_close.tz_convert('America/New_York').isoformat()


def load_instrument_metadata(symbol: str, symbols_config_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Resolve instrument type from symbols.yaml analysis_targets.
      stocks -> "stock" | etfs -> "etf" | benchmarks -> "benchmark" | else -> "unknown"
    """
    if symbols_config_path is None:
        symbols_config_path = Path(__file__).resolve().parents[1] / "config/symbols.yaml"

    inst_type = "unknown"
    try:
        if symbols_config_path.exists():
            with open(symbols_config_path, encoding='utf-8') as f:
                cfg = yaml.safe_load(f)
            targets = cfg.get('analysis_targets', {}) or {}
            sym_upper = symbol.upper()
            if sym_upper in [s.upper() for s in targets.get('stocks', []) or []]:
                inst_type = "stock"
            elif sym_upper in [s.upper() for s in targets.get('etfs', []) or []]:
                inst_type = "etf"
            elif sym_upper in [s.upper() for s in targets.get('benchmarks', []) or []]:
                inst_type = "benchmark"
    except Exception as e:
        log.warning(f"load_instrument_metadata failed for {symbol}: {e}")

    # Current stock / etf / benchmark all have volume + extended hours.
    # Reserved "index" type (e.g. if SPX/NDX are re-added) should set both flags to False.
    return {
        "instrument_type": inst_type,
        "has_volume": True,
        "has_extended_hours": True,
    }


# ──────────────────────────── Config & File Loading ──────────────────────────── #

def load_config(config_path: Optional[Path] = None) -> dict:
    if config_path:
        path_to_load = config_path
    else:
        path_to_load = Path(__file__).resolve().parents[1] / "config/data_sources.yaml"
        
    if not path_to_load.exists():
        # Fallback
        path_to_load = Path("config/data_sources.yaml")
        
    if not path_to_load.exists():
        log.error(f"Config file not found: {path_to_load}")
        raise FileNotFoundError(f"Config file not found: {path_to_load}")
        
    with open(path_to_load, encoding="utf-8") as f:
        return yaml.safe_load(f)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


# ──────────────────────────── Filename Parsing ──────────────────────────── #

def extract_time_tag_from_filename(csv_path: Path) -> Optional[str]:
    """
    提取 ISO 8601 (YYYYMMDDTHHMMSSZ) 时间戳。
    严格拒绝 "LATEST"。
    """
    try:
        filename_stem = csv_path.stem
        parts = filename_stem.split("_")
        candidate = parts[-1]
        
        if candidate == "LATEST":
            log.warning(f"[SKIP] Ignored legacy 'LATEST' file: {csv_path.name}")
            return None

        if ("T" in candidate and candidate.endswith("Z")) or candidate.isdigit():
            return candidate

        log.warning(f"[SKIP] Invalid time format '{candidate}' in {csv_path.name}. Ignoring.")
        return None
        
    except (ValueError, IndexError):
        return None


def get_latest_csv_for_resolution(symbol: str, cache_dir: Path, filename_duration: str, filename_resolution: str) -> Optional[Path]:
    """
    获取最新且**文件名合法**的 CSV 文件。
    """
    symbol_dir = cache_dir / symbol
    if not symbol_dir.exists():
        return None
    
    pattern = f"{symbol}_{filename_duration}_{filename_resolution}_*.csv"
    matching_files = list(symbol_dir.glob(pattern))
    
    if not matching_files:
        return None
    
    # 先过滤非法文件名
    valid_files = [f for f in matching_files if extract_time_tag_from_filename(f) is not None]
    
    if not valid_files:
        log.warning(f"[WARN] No valid timestamped files found for {symbol} (found {len(matching_files)} invalid/legacy).")
        return None
    
    # 按 mtime 排序取最新
    valid_files.sort(key=lambda p: p.stat().st_mtime)
    
    return valid_files[-1]


def extract_market_data_timestamp_iso(
    manual_paths: Optional[Dict[str, Path]] = None,
    symbol: str = None,
    config: dict = None
) -> Optional[str]:
    """
    提取基准时间戳。
    【严格逻辑】: 必须且只能使用 '2d_1m' (1分钟线) 的时间戳。
    如果不存 1m 数据，后续步骤无论如何都会失败，所以这里不需要 Fallback。
    """
    target_csv_path = None
    
    # 1m 数据的标准 Label/Params
    TARGET_LABEL = "2d_1m" 
    TARGET_DURATION = "2d"
    TARGET_RESOLUTION = "1m"
    
    if manual_paths:
        target_csv_path = manual_paths.get(TARGET_LABEL)
    else:
        cache_dir = Path(config['data_sources']['market_data']['cache_dir'])
        # 仅查找 1m 级别的文件
        target_csv_path = get_latest_csv_for_resolution(symbol, cache_dir, TARGET_DURATION, TARGET_RESOLUTION)
    
    if target_csv_path is None:
        log.error(f"❌ Failed to find VALID '{TARGET_LABEL}' market data file for {symbol}. Analysis cannot proceed.")
        return None
    
    return extract_time_tag_from_filename(target_csv_path)


# ──────────────────────────── Data Loading ──────────────────────────── #

def load_ohlcv(csv_path: Path, min_rows: int = 1) -> Optional[pd.DataFrame]:
    try:
        df = pd.read_csv(csv_path)
    except Exception as exc:
        log.warning(f"Unable to read {csv_path}: {exc}")
        return None

    df.columns = [col.lower() for col in df.columns]
    date_col = "datetime" if "datetime" in df.columns else "date"
    if date_col not in df.columns:
        return None

    df[date_col] = pd.to_datetime(df[date_col], utc=True, errors="coerce")
    
    df = df.dropna(subset=[date_col])
    df = df.sort_values(date_col)
    df = df.set_index(date_col)

    required_cols = ["open", "high", "low", "close", "volume", "wap", "barcount"]
    # 允许部分列缺失
    cols_to_use = [c for c in required_cols if c in df.columns]
    
    df = df[cols_to_use].dropna()
    if len(df) < min_rows:
        return None

    return df


def load_all_dataframes(
    symbol: str, 
    config: dict, 
    manual_paths: Optional[Dict[str, Path]] = None
) -> Optional[Dict[str, pd.DataFrame]]:
    """
    加载所有时间周期的数据框。
    【严格逻辑】: 必须凑齐 4 个周期 (1m, 5m, 1h, 1d)，缺一不可。
    """
    REQUIRED_SCHEDULES = {
        "2d_1m": "1m",
        "7d_5m": "5m",
        "2m_1h": "1h",
        "5y_1d": "1d",
    }
    
    data_frames = {}
    
    if manual_paths:
        for label, key in REQUIRED_SCHEDULES.items():
            if label not in manual_paths:
                log.error(f"Missing required manual path: {label}")
                return None
            df = load_ohlcv(manual_paths[label])
            if df is None:
                log.error(f"Failed to load dataframe from manual path: {label}")
                return None
            data_frames[key] = df
    else:
        cache_dir = Path(config['data_sources']['market_data']['cache_dir'])
        schedules = config['data_sources']['market_data']['schedules']
        
        found_count = 0
        for schedule in schedules:
            label = schedule.get('label')
            if label in REQUIRED_SCHEDULES:
                csv_path = get_latest_csv_for_resolution(
                    symbol, cache_dir, 
                    schedule['filename_duration'], 
                    schedule['filename_resolution']
                )
                if csv_path:
                    df = load_ohlcv(csv_path)
                    if df is not None:
                        data_frames[REQUIRED_SCHEDULES[label]] = df
                        found_count += 1
        
        # 强校验：必须全部找到
        if found_count != len(REQUIRED_SCHEDULES):
            log.error(f"Failed to find all required CSV schedules for {symbol}. Found {found_count}/{len(REQUIRED_SCHEDULES)}.")
            return None

    try:
        df_1d = data_frames["1d"]
        df_1w = df_1d.resample('W').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum',
            'wap': 'mean',
            'barcount': 'sum' if 'barcount' in df_1d.columns else 'count'
        }).dropna()
        data_frames["1w"] = df_1w
    except Exception as e:
        log.error(f"Failed to resample weekly data: {e}")
        return None

    return data_frames


# ──────────────────────────── Utility Functions ──────────────────────────── #

def safe_float(value: Any, precision: int = 4) -> Optional[float]:
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return None
    try:
        return round(float(value), precision)
    except (ValueError, TypeError):
        return None

def safe_int(value: Any) -> Optional[int]:
    val = safe_float(value, 0) 
    return int(val) if val is not None else None

BENCHMARK_DATA = {}

def get_benchmark_data(symbol: str, config: dict) -> Optional[pd.DataFrame]:
    global BENCHMARK_DATA
    if symbol in BENCHMARK_DATA:
        return BENCHMARK_DATA[symbol]
    
    cache_dir = Path(config['data_sources']['market_data']['cache_dir'])
    # 假设 SPY 至少有 5y_1d 数据
    spy_file = get_latest_csv_for_resolution(symbol, cache_dir, "5y", "1d")
            
    if not spy_file:
        return None
        
    df = load_ohlcv(spy_file, min_rows=252) 
    if df is not None:
        BENCHMARK_DATA[symbol] = df
        return df
    return None


# ─────────────────────── Indicator Calculation ─────────────────────── #

def calculate_all_features(
    data_frames: Dict[str, pd.DataFrame],
    config: dict,
    session_info: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Compute all technical indicators with session-aware null handling (V15.0).
    session_info is produced by classify_session() against the latest 1m bar.
    """
    features = {}

    df_1m = data_frames.get("1m")
    df_5m = data_frames.get("5m")
    df_1h = data_frames.get("1h")
    df_1d = data_frames.get("1d")
    df_1w = data_frames.get("1w")

    BENCHMARK_SYMBOL = "SPY"
    df_spy_1d = get_benchmark_data(BENCHMARK_SYMBOL, config)

    current_session = session_info.get("current_session", "closed")
    reg_open_utc = session_info.get("reg_open_utc")
    is_regular = current_session == "regular"
    is_regular_or_after = current_session in ("regular", "after-hours")
    is_premarket = current_session == "pre-market"

    # ──────────────── 1. Current Snapshot (minute / 5m level) ──────────────── #
    try:
        latest_1m = df_1m.iloc[-1]

        features["latest_data_timestamp_iso"] = latest_1m.name.isoformat()
        features["last_price"] = safe_float(latest_1m["close"])
        features["last_wap"] = safe_float(latest_1m["wap"])

        # change_since_regular_open_pct: anchored to today's regular session open
        # Populated during regular/after-hours; null in pre-market/closed.
        change_since_reg_open = None
        if is_regular_or_after and reg_open_utc is not None:
            today_regular = df_1m[df_1m.index >= reg_open_utc]
            if not today_regular.empty:
                open_price = today_regular.iloc[0]["open"]
                if open_price and open_price > 0:
                    change_since_reg_open = (latest_1m["close"] - open_price) / open_price * 100
        features["change_since_regular_open_pct"] = safe_float(change_since_reg_open, 2)

        # vwap_dist_pct: regular-session VWAP only; null otherwise
        vwap_dist = None
        if is_regular and reg_open_utc is not None:
            today_regular = df_1m[df_1m.index >= reg_open_utc]
            if not today_regular.empty and "volume" in today_regular.columns:
                vol_sum = today_regular["volume"].sum()
                if vol_sum > 0:
                    vwap = (today_regular["wap"] * today_regular["volume"]).sum() / vol_sum
                    if vwap > 0:
                        vwap_dist = (latest_1m["close"] - vwap) / vwap * 100
        features["vwap_dist_pct"] = safe_float(vwap_dist, 2)

        # 5m rolling volume ratio: always meaningful (rolling window)
        df_5m_ta = df_5m.copy()
        df_5m_ta["volume_sma20"] = df_5m_ta["volume"].rolling(20).mean()
        latest_5m = df_5m_ta.iloc[-1]
        vol_ratio_5m = (latest_5m["volume"] / latest_5m["volume_sma20"]) if latest_5m["volume_sma20"] > 0 else None
        features["volume_ratio_5m_vs_20bar_avg"] = safe_float(vol_ratio_5m, 2)

        features["price_change_pct_5m"] = safe_float(df_5m["close"].pct_change(1).iloc[-1] * 100, 2)

        df_5m_ta.ta.rsi(length=14, append=True)
        df_5m_ta.ta.atr(length=14, append=True)
        features["rsi_14_5min"] = safe_float(df_5m_ta.iloc[-1].get("RSI_14"), 2)
        features["atr_14_5min"] = safe_float(df_5m_ta.iloc[-1].get("ATRr_14"), 4)

        if "barcount" in df_1m.columns:
            avg_barcount = df_1m.iloc[-60:]["barcount"].mean()
            if avg_barcount > 0:
                features["liquidity_score_vol_per_bar"] = safe_float(latest_1m["volume"] / avg_barcount, 2)

    except Exception as e:
        log.error(f"Failed calculating current_snapshot features: {e}", exc_info=True)

    # ──────────────── 2. Hourly Level ──────────────── #
    try:
        df_1h_ta = df_1h.copy()
        df_1h_ta.ta.sma(length=20, append=True)
        df_1h_ta.ta.sma(length=50, append=True)
        df_1h_ta.ta.rsi(length=14, append=True)
        df_1h_ta.ta.macd(append=True)
        df_1h_ta.ta.atr(length=14, append=True)
        df_1h_ta.ta.bbands(length=20, std=2, append=True)
        df_1h_ta["volume_sma20"] = df_1h_ta["volume"].rolling(20).mean()
        
        latest_1h = df_1h_ta.iloc[-1]
        
        features["ma_20_hourly_val"] = safe_float(latest_1h.get("SMA_20"))
        features["ma_50_hourly_val"] = safe_float(latest_1h.get("SMA_50"))
        
        if len(df_1h_ta) >= 5 and "SMA_20" in df_1h_ta.columns:
            ma_now = latest_1h["SMA_20"]
            ma_prev = df_1h_ta.iloc[-5]["SMA_20"]
            if ma_prev > 0:
                slope = (ma_now - ma_prev) / ma_prev * 100
                features["ma_20_slope_pct_hourly"] = safe_float(slope, 3)
        
        features["rsi_14_hourly"] = safe_float(latest_1h.get("RSI_14"), 2)
        
        if "MACDh_12_26_9" in df_1h_ta.columns:
            features["macd_hist_hourly"] = safe_float(latest_1h["MACDh_12_26_9"], 3)
        
        features["atr_14_hourly"] = safe_float(latest_1h.get("ATRr_14"))
        
        bb_upper_col = next((c for c in df_1h_ta.columns if c.startswith("BBU_")), None)
        bb_lower_col = next((c for c in df_1h_ta.columns if c.startswith("BBL_")), None)
        
        if bb_upper_col and bb_lower_col:
            upper = latest_1h[bb_upper_col]
            lower = latest_1h[bb_lower_col]
            width = upper - lower
            if width > 0:
                pct_b = (latest_1h["close"] - lower) / width
                features["bb_pct_b_hourly"] = safe_float(pct_b, 2)
        
        features["volume_ratio_vs_avg_hourly"] = safe_float(
            latest_1h["volume"] / latest_1h["volume_sma20"] if latest_1h.get("volume_sma20", 0) > 0 else None, 2
        )
        
        if len(df_1h) > 20:
            swing_data = calculate_swing_points(
                df_1h, lookback_window=20, min_swing_pct=0.015, max_points=25
            )
            if swing_data:
                features["price_structure_tactical"] = swing_data
            
            micro_flow = calculate_simplified_trend(df_1h, target=30)
            if micro_flow:
                features["micro_flow_engine"] = micro_flow
        
    except Exception as e:
        log.error(f"Failed calculating hourly_features: {e}", exc_info=True)

    # ──────────────── 3. Daily Level ──────────────── #
    try:
        df_1d_ta = df_1d.copy()
        df_1d_ta.ta.sma(length=20, append=True)
        df_1d_ta.ta.sma(length=50, append=True)
        df_1d_ta.ta.sma(length=200, append=True)
        df_1d_ta.ta.rsi(length=14, append=True)
        df_1d_ta.ta.macd(append=True)
        df_1d_ta.ta.atr(length=14, append=True)
        df_1d_ta.ta.bbands(length=20, std=2, append=True)
        df_1d_ta.ta.obv(append=True)
        df_1d_ta["volume_sma20"] = df_1d_ta["volume"].rolling(20).mean()
        
        latest_1d = df_1d_ta.iloc[-1]

        # change_vs_prior_regular_close_pct: always populated, belongs to current_snapshot group.
        # During pre-market/after-hours this is the gap / extended-hours move vs the last regular close.
        features["change_vs_prior_regular_close_pct"] = safe_float(df_1d_ta["close"].pct_change(1).iloc[-1] * 100, 2)
        features["ma_20_daily_val"] = safe_float(latest_1d.get("SMA_20"))
        features["ma_50_daily_val"] = safe_float(latest_1d.get("SMA_50"))
        features["ma_200_daily_val"] = safe_float(latest_1d.get("SMA_200"))
        
        if len(df_1d_ta) >= 2 and "SMA_50" in df_1d_ta.columns and "SMA_200" in df_1d_ta.columns:
            sma50_now = latest_1d["SMA_50"]
            sma200_now = latest_1d["SMA_200"]
            sma50_prev = df_1d_ta.iloc[-2]["SMA_50"]
            sma200_prev = df_1d_ta.iloc[-2]["SMA_200"]
            
            if sma50_now > sma200_now and sma50_prev <= sma200_prev:
                 features["ma_cross_status"] = "Golden Cross"
            elif sma50_now < sma200_now and sma50_prev >= sma200_prev:
                 features["ma_cross_status"] = "Death Cross"
            else:
                 features["ma_cross_status"] = "Bullish" if sma50_now > sma200_now else "Bearish"
                 
            if "SMA_20" in df_1d_ta.columns:
                sma20_now = latest_1d["SMA_20"]
                features["ma_alignment"] = "Bullish" if sma20_now > sma50_now > sma200_now else \
                                           "Bearish" if sma20_now < sma50_now < sma200_now else "Mixed"
        
        features["rsi_14_daily"] = safe_float(latest_1d.get("RSI_14"), 2)
        
        if "MACDh_12_26_9" in df_1d_ta.columns:
            features["macd_hist_daily"] = safe_float(latest_1d["MACDh_12_26_9"], 3)
        
        features["atr_14_daily_percent"] = safe_float((latest_1d.get("ATRr_14", 0) / latest_1d["close"]) * 100, 2)
        
        bb_upper_col = next((c for c in df_1d_ta.columns if c.startswith("BBU_")), None)
        bb_lower_col = next((c for c in df_1d_ta.columns if c.startswith("BBL_")), None)
        
        if bb_upper_col and bb_lower_col:
            upper = latest_1d[bb_upper_col]
            lower = latest_1d[bb_lower_col]
            width = upper - lower
            if width > 0:
                pct_b = (latest_1d["close"] - lower) / width
                features["bb_pct_b_daily"] = safe_float(pct_b, 2)
                if latest_1d.get("SMA_20", 0) > 0:
                    features["bb_width_pct_daily"] = safe_float(width / latest_1d["SMA_20"] * 100, 2)
        
        # volume_ratio_vs_20d_daily_avg: null during pre-market (today's daily bar is partial with
        # negligible volume, ratio collapses to near-zero and misleads downstream readers).
        if is_premarket:
            features["volume_ratio_vs_20d_daily_avg"] = None
        else:
            features["volume_ratio_vs_20d_daily_avg"] = safe_float(
                latest_1d["volume"] / latest_1d.get("volume_sma20", 1) if latest_1d.get("volume_sma20", 0) > 0 else None, 2
            )
        
        if "OBV" in df_1d_ta.columns and len(df_1d_ta) >= 5:
            obv_now = latest_1d["OBV"]
            obv_prev = df_1d_ta.iloc[-5]["OBV"]
            if obv_prev != 0:
                slope = (obv_now - obv_prev) / abs(obv_prev) * 100
                features["obv_slope_5d"] = safe_float(slope, 2)
        
        atr_pct = features.get("atr_14_daily_percent", 0)
        if atr_pct:
            atr_pct_avg = (df_1d_ta["ATRr_14"] / df_1d_ta["close"] * 100).iloc[-60:].mean()
            features["volatility_regime_daily"] = "High" if atr_pct > atr_pct_avg * 1.25 else "Low" if atr_pct < atr_pct_avg * 0.75 else "Normal"

        if len(df_1d_ta) >= 2:
            prev_1d = df_1d_ta.iloc[-2]
            gap_pct = (latest_1d["open"] - prev_1d["close"]) / prev_1d["close"]
            features["recent_gaps"] = "Up" if gap_pct > 0.01 else "Down" if gap_pct < -0.01 else "None"
        
        if len(df_1d_ta) >= 5:
            is_consolidating = (df_1d_ta.iloc[-5:]["high"].max() - df_1d_ta.iloc[-5:]["low"].min()) / latest_1d["close"] < 0.05
            features["consolidation_days"] = 5 if is_consolidating else 0
            
    except Exception as e:
        log.error(f"Failed calculating daily_features: {e}", exc_info=True)

    # ──────────────── 4. Weekly Level ──────────────── #
    try:
        df_1w_ta = df_1w.copy()
        df_1w_ta.ta.sma(length=40, append=True)
        df_1w_ta.ta.sma(length=200, append=True)
        latest_1w = df_1w_ta.iloc[-1]
        
        features["ma_40_weekly_val"] = safe_float(latest_1w.get("SMA_40"))
        features["ma_200_weekly_val"] = safe_float(latest_1w.get("SMA_200"))
    except Exception as e:
        log.error(f"Failed calculating weekly_features: {e}")

    # ──────────────── 5. Positioning / Cross-timeframe / Strategic ──────────────── #
    # Note: market session is now determined at a higher level (classify_session on latest 1m bar)
    # and emitted under session_context in build_json_output.
    try:
        df_52w = df_1d.iloc[-252:]
        high_52w = df_52w["high"].max()
        low_52w = df_52w["low"].min()
        last_price = features.get("last_price")
        if last_price and (high_52w - low_52w) > 0:
            features["percent_from_52w_high_low"] = safe_float((last_price - low_52w) / (high_52w - low_52w) * 100, 2)
        
        df_30d = df_1d.iloc[-30:]
        features["nearest_support_resistance"] = {"support": safe_float(df_30d["low"].min()), "resistance": safe_float(df_30d["high"].max())}

        trend_1h = features.get("ma_20_slope_pct_hourly", 0) > 0
        trend_1d = features.get("ma_alignment") == "Bullish"
        if trend_1h and trend_1d: features["cross_timeframe_trend_alignment"] = "Bullish"
        elif not trend_1h and not trend_1d: features["cross_timeframe_trend_alignment"] = "Bearish"
        else: features["cross_timeframe_trend_alignment"] = "Mixed"
        
        mom_5m = features.get("rsi_14_5min", 50) > 50
        mom_1h = features.get("rsi_14_hourly", 50) > 50
        mom_1d = features.get("rsi_14_daily", 50) > 50
        mom_score = (1 if mom_5m else 0) + (1 if mom_1h else 0) + (1 if mom_1d else 0)
        features["cross_timeframe_momentum_score"] = "Strongly Bullish" if mom_score == 3 else "Bullish" if mom_score == 2 else "Bearish" if mom_score == 1 else "Strongly Bearish"

        roll_max = df_30d["close"].cummax()
        drawdown = (df_30d["close"] - roll_max) / roll_max
        features["max_drawdown_30d"] = safe_float(drawdown.min() * 100, 2)

        returns_30d = df_30d["close"].pct_change().dropna()
        if not returns_30d.empty and returns_30d.std() > 0:
            sharpe = (returns_30d.mean() / returns_30d.std()) * math.sqrt(252)
            features["sharpe_ratio_30d"] = safe_float(sharpe, 2)
        
        if df_spy_1d is not None:
            combined = pd.DataFrame({
                "symbol": df_1d["close"].pct_change(),
                "spy": df_spy_1d["close"].pct_change()
            }).dropna()
            
            if len(combined) > 30:
                rs_30d = (combined.iloc[-30:]["symbol"].add(1).cumprod().iloc[-1] /
                          combined.iloc[-30:]["spy"].add(1).cumprod().iloc[-1])
                features["relative_strength_vs_spy"] = safe_float(rs_30d, 3)

                corr_30d = combined.iloc[-30:]["symbol"].corr(combined.iloc[-30:]["spy"])
                features["correlation_vs_spy"] = safe_float(corr_30d, 3)
                
                if len(combined) > 60:
                    cov_60d = combined.iloc[-60:].cov().iloc[0, 1]
                    var_60d = combined.iloc[-60:]["spy"].var()
                    if var_60d > 0:
                        features["beta"] = safe_float(cov_60d / var_60d, 3)

        # --- 战略趋势计算 (L1 - Strategic) ---
        log.info("Calculating Strategic (Daily) trend analysis...")
        if df_1d is not None:
            lookback_2y = 252 * 2
            df_swing_daily = df_1d.iloc[-lookback_2y:] 
            swing_data_daily = calculate_swing_points(
                df_swing_daily, 
                lookback_window=20, 
                min_swing_pct=0.08, 
                max_points=25
            )
            if swing_data_daily:
                features["price_structure_strategic"] = swing_data_daily
        
    except Exception as e:
        log.error(f"Failed calculating contextual_features: {e}")

    return features


# ─────────────────────── JSON Building & Saving ─────────────────────── #

def build_json_output(
    all_features: Dict[str, Any],
    feature_list: List[str],
    group_map: Dict[str, str],
    symbol: str,
    timestamp_iso: str,
    instrument_metadata: Dict[str, Any],
    session_context: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Assemble the V15.0 session-aware JSON output.
    Top-level layout:
      symbol, market_data_timestamp_utc, latest_data_timestamp,
      instrument_metadata, session_context,
      current_snapshot, daily_technicals, hourly_technicals,
      weekly_snapshot, positioning, cross_timeframe_summary, price_structure
    """
    output_json = {
        "symbol": symbol,
        "market_data_timestamp_utc": timestamp_iso,
        "latest_data_timestamp": all_features.get("latest_data_timestamp_iso", timestamp_iso),
        "instrument_metadata": instrument_metadata,
        "session_context": session_context,
    }

    for key in feature_list:
        if key not in all_features:
            continue
        group = group_map.get(key)
        if not group:
            continue

        if group == "price_structure":
            sub_key = PRICE_STRUCTURE_SUBKEY.get(key, key)
            output_json.setdefault(group, {})[sub_key] = all_features[key]
        else:
            output_json.setdefault(group, {})[key] = all_features[key]

    return output_json


def save_json(json_data: Dict[str, Any], output_path: Path) -> bool:
    try:
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)
        log.info(f"Successfully generated JSON: {output_path.name}")
        return True
    except Exception as exc:
        log.error(f"Failed to write JSON to {output_path}: {exc}")
        return False


# ─────────────────────── Main Processing Function ─────────────────────── #

def process_symbol_technical_analysis(
    symbol: str, 
    manual_paths: Optional[Dict[str, Path]] = None,
    force_update: bool = False,
    config_path: Optional[Path] = None
) -> Optional[Path]:
    """
    处理单个股票的技术分析 (ISO 8601 Unified Mode)
    返回: 生成的 JSON 文件路径 (Optional)
    """
    log.info(f"--- Starting technical analysis for {symbol} (Unified Mode) ---")
    
    try:
        config = load_config(config_path) 
        output_base_dir = Path(config['data_sources']['technical_analysis']['output_dir'])
    except Exception as e:
        log.error(f"Failed to load config: {e}")
        return None
    
    # 提取时间戳字符串 (ISO 8601 Format: YYYYMMDDTHHMMSSZ)
    # 🔥 V14.1: 严格从 2d_1m 文件中提取，失败即中止
    market_data_timestamp_str = extract_market_data_timestamp_iso(
        manual_paths=manual_paths,
        symbol=symbol,
        config=config
    )
    
    if not market_data_timestamp_str:
        log.error(f"[ABORT] {symbol}: missing or invalid 1m data timestamp.")
        return None

    log.info(f"Market data base timestamp: {market_data_timestamp_str}")

    # Unified output path (ISO-named)
    symbol_output_dir = output_base_dir / symbol
    tech_path = symbol_output_dir / f"{symbol}_technical_{market_data_timestamp_str}.json"

    if not force_update and tech_path.exists():
        log.info(f"[OK] Technical analysis already exists: {tech_path.name}")
        log.info("  Skipping calculation (use force_update=True to regenerate).")
        return tech_path
    
    # Load data (validates all 4 resolutions present)
    log.info("Loading market data...")
    data_frames = load_all_dataframes(symbol, config, manual_paths)
    if not data_frames:
        log.error(f"Could not load all required dataframes for {symbol}. Aborting.")
        return None

    # Session classification from the latest 1m bar
    latest_bar_ts = data_frames["1m"].index[-1]
    session_info = classify_session(latest_bar_ts)
    prior_close_et = get_prior_regular_close_et(latest_bar_ts)

    session_context = {
        "current_session": session_info["current_session"],
        "elapsed_minutes": session_info["elapsed_minutes"],
        "latest_bar_et": session_info["latest_bar_et"],
        "prior_regular_close_et": prior_close_et,
    }
    log.info(
        f"Session: {session_context['current_session']} "
        f"(elapsed={session_context['elapsed_minutes']} min, "
        f"latest_bar_et={session_context['latest_bar_et']})"
    )

    instrument_metadata = load_instrument_metadata(symbol)

    # Feature calculation (session-aware)
    log.info("Calculating all features...")
    all_features = calculate_all_features(data_frames, config, session_info)
    log.info("Feature calculation complete.")

    # Build unified JSON (V15.0 structure)
    log.info("Building unified technical JSON...")
    tech_json = build_json_output(
        all_features, UNIFIED_FEATURES, FEATURE_GROUP_MAP,
        symbol, market_data_timestamp_str,
        instrument_metadata, session_context,
    )

    # 保存
    ensure_dir(symbol_output_dir)
    saved = save_json(tech_json, tech_path)

    log.info(f"--- Finished analysis for {symbol} ---")
    
    return tech_path if saved else None

# ─────────────────────── Example Usage ──────────────────────── #

if __name__ == "__main__":
    symbol_to_run = "AAPL" 
    
    tech_file = process_symbol_technical_analysis(symbol_to_run)
    
    if tech_file:
        log.info(f"\n[OK] Analysis complete for {symbol_to_run}")
        log.info(f"  Output file: {tech_file}")
    else:
        log.error(f"\n[FAIL] Analysis failed for {symbol_to_run}")