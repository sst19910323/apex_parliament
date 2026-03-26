"""
Alpha Vantage Company Fundamentals Fetcher (Write-Only Executor)
(V5.1 - ISO 8601 UTC Standard)

- 职责: 纯粹的"写入"执行器。
- 修正: 批量下载时单点故障不影响全局。
- 兼容: 自动处理 BRK.B -> BRK-B。
- 标准化: 文件名和时间戳强制统一为 ISO 8601 UTC (YYYYMMDDTHHMMSSZ)。
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, List

import requests
import yaml

# ─────────────────────────── 路径与环境设置 ─────────────────────────── #

def resolve_project_root() -> Path:
    """智能查找项目根目录"""
    current_path = Path(__file__).resolve()
    for parent in [current_path.parent] + list(current_path.parents):
        if (parent / "config").exists() and (parent / "data").exists():
            return parent
    return current_path.parents[1]

PROJECT_ROOT = resolve_project_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 尝试导入 Key Manager
try:
    from fetchers.api_key_manager import key_manager
except ImportError:
    print("WARNING: [AlphaFundamentalFetcher] Key Manager not found. Using Mock.")
    class PlaceholderKeyManager:
        def get_key(self, source_name: Optional[str] = None) -> Optional[str]:
            return "YOUR_PLACEHOLDER_KEY"
        def wait_if_needed(self, api_key: str) -> float: return 0.0 
        def record_usage(self, api_key: str): pass
    key_manager = PlaceholderKeyManager()

BASE_URL = "https://www.alphavantage.co/query"
CONFIG_PATH = PROJECT_ROOT / "config" / "data_sources.yaml"
SOURCE_NAME = "alpha_fundamentals"

# ──────────────────────────── Data Structure ──────────────────────────── #

@dataclass
class CompanyFundamentals:
    symbol: str
    name: Optional[str] = None
    description: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    market_cap: Optional[float] = None
    pe_ratio: Optional[float] = None
    peg_ratio: Optional[float] = None
    eps: Optional[float] = None
    dividend_yield: Optional[float] = None
    dividend_per_share: Optional[float] = None
    beta: Optional[float] = None
    revenue_ttm: Optional[float] = None
    profit_margin: Optional[float] = None
    return_on_equity_ttm: Optional[float] = None
    analyst_target_price: Optional[float] = None
    fifty_two_week_high: Optional[float] = None
    fifty_two_week_low: Optional[float] = None
    shares_outstanding: Optional[float] = None
    country: Optional[str] = None
    currency: Optional[str] = None
    fiscal_year_end: Optional[str] = None
    latest_quarter: Optional[str] = None
    # 使用 UTC aware time
    last_updated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Optional[str] | Optional[float]]:
        return asdict(self)

# ──────────────────────────── Config & Utilities ──────────────────────────── #

def load_config() -> Dict:
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f: 
            full_config = yaml.safe_load(f)
            return full_config.get('data_sources', {}).get(SOURCE_NAME, {})
    except:
        return {"cache_dir": "data/fundamentals"}

class AlphaFundamentalFetcher:
    def __init__(self):
        self.name = "AlphaFundamentalFetcher"
        self.config = load_config()
        cache_dir_relative = self.config.get("cache_dir", "data/fundamentals")
        self.cache_dir = PROJECT_ROOT / cache_dir_relative
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        symbol = symbol.upper()
        if symbol == "BRK.B": return "BRK-B"
        if symbol.startswith("^"): return symbol
        return symbol.replace(".US", "")

    @staticmethod
    def _to_float(value: Optional[str]) -> Optional[float]:
        try:
            if not value or value.strip().upper() in ["NONE", "NA", "-", "None"]:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _make_request(self, params: Dict) -> Optional[Dict]:
        api_key = key_manager.get_key(SOURCE_NAME) 
        if not api_key:
            print(f"  [{self.name}] ✗ No available API key")
            return None

        wait_time = key_manager.wait_if_needed(api_key)
        if wait_time > 0:
            print(f"  [{self.name}] ⏳ Waiting {wait_time:.1f}s for rate limit...")
            time.sleep(wait_time)

        params["apikey"] = api_key

        try:
            response = requests.get(BASE_URL, params=params, timeout=25)
            key_manager.record_usage(api_key)
            response.raise_for_status() 
            data = response.json()

            if "Error Message" in data:
                print(f"  [{self.name}] ✗ API Error: {data['Error Message']}")
                return None
            if "Information" in data:
                print(f"  [{self.name}] ⚠ API Rate Limit Reached: {data['Information']}")
                return None
            return data

        except Exception as exc:
            print(f"  [{self.name}] ✗ Network/Parse error: {exc}")
            return None

    def _save_to_cache(self, fundamentals: CompanyFundamentals, original_symbol: str):
        symbol = original_symbol.upper()
        symbol_dir = self.cache_dir / symbol
        symbol_dir.mkdir(parents=True, exist_ok=True)
        
        # 🔥 核心修正: 使用 ISO 8601 UTC 文件名 (YYYYMMDDTHHMMSSZ)
        now_utc = datetime.now(timezone.utc)
        timestamp_str = now_utc.strftime("%Y%m%dT%H%M%SZ")
        
        filename = f"{symbol}_fundamentals_{timestamp_str}.json"
        file_path = symbol_dir / filename
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(fundamentals.to_dict(), f, ensure_ascii=False, indent=4)
            print(f"  [{self.name}] 💾 Saved: {filename}")
        except Exception as e:
            print(f"  [{self.name}] ✗ Save failed: {e}")

    def download_fundamentals(self, symbol: str, retry: int = 2) -> bool:
        api_symbol = self.normalize_symbol(symbol)
        print(f"\n[{self.name}] 🚀 Downloading {symbol} (API: {api_symbol})...")
        
        for attempt in range(retry):
            params = {"function": "OVERVIEW", "symbol": api_symbol}
            data = self._make_request(params)
            
            returned_symbol = data.get("Symbol") if data else None
            if not data or not returned_symbol:
                if attempt < retry - 1:
                    time.sleep(2)
                continue
            
            try:
                fundamentals = CompanyFundamentals(
                    symbol=symbol, # 强制使用系统统一 symbol
                    name=data.get("Name"),
                    description=data.get("Description"),
                    sector=data.get("Sector"),
                    industry=data.get("Industry"),
                    market_cap=self._to_float(data.get("MarketCapitalization")),
                    pe_ratio=self._to_float(data.get("PERatio")),
                    peg_ratio=self._to_float(data.get("PEGRatio")),
                    eps=self._to_float(data.get("EPS")),
                    dividend_yield=self._to_float(data.get("DividendYield")),
                    dividend_per_share=self._to_float(data.get("DividendPerShare")),
                    beta=self._to_float(data.get("Beta")),
                    revenue_ttm=self._to_float(data.get("RevenueTTM")),
                    profit_margin=self._to_float(data.get("ProfitMargin")),
                    return_on_equity_ttm=self._to_float(data.get("ReturnOnEquityTTM")),
                    analyst_target_price=self._to_float(data.get("AnalystTargetPrice")),
                    fifty_two_week_high=self._to_float(data.get("52WeekHigh")),
                    fifty_two_week_low=self._to_float(data.get("52WeekLow")),
                    shares_outstanding=self._to_float(data.get("SharesOutstanding")),
                    country=data.get("Country"),
                    currency=data.get("Currency"),
                    fiscal_year_end=data.get("FiscalYearEnd"),
                    latest_quarter=data.get("LatestQuarter"),
                    # last_updated 已由 dataclass 默认工厂函数处理为 UTC
                )
                self._save_to_cache(fundamentals, symbol)
                return True
            except Exception as e:
                print(f"  [{self.name}] ✗ Parse/Save error: {e}")
                return False
        
        return False
    
    def download_batch_fundamentals(self, symbols: List[str]) -> Dict[str, bool]:
        results: Dict[str, bool] = {}
        print(f"\n[{self.name}] 📦 Batch download for {len(symbols)} symbols...")
        
        for i, symbol in enumerate(symbols, 1):
            print(f"\n[{self.name}] Progress: {i}/{len(symbols)}")
            
            # 每一个下载都独立 try-except，防止单点崩溃
            try:
                success = self.download_fundamentals(symbol)
                results[symbol] = success
            except Exception as e:
                print(f"  [{self.name}] 💥 CRITICAL ERROR downloading {symbol}: {e}")
                results[symbol] = False
            
            # 稍微休息一下，给 API 喘息
            if i < len(symbols):
                time.sleep(1)
        
        success_count = sum(results.values())
        print(f"\n[{self.name}] 📊 Batch complete: {success_count}/{len(symbols)} succeeded")
        return results

# Test Entry
if __name__ == "__main__":
    print("--- Alpha Fetcher Test (V5.1 UTC) ---")
    try:
        fetcher = AlphaFundamentalFetcher()
        fetcher.download_batch_fundamentals(["AAPL"])
    except Exception as e:
        print(f"Test Failed: {e}")