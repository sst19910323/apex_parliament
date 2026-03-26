"""
Alpha Vantage Macroeconomic Data Fetcher
(V2 - ISO 8601 UTC Standard)

- 职责: 纯粹的“写入”执行器。
- 逻辑: 调度器调用 -> 联网获取 -> 保存为带 UTC 时间戳的 JSON。
- 命名: 使用 ISO 8601 (YYYYMMDDTHHMMSSZ) 格式，与系统其他部分统一。
"""

from __future__ import annotations

import json
import time
import traceback
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import requests
import yaml

# 假设 key_manager 在同一目录下或在 PYTHONPATH 中
try:
    from .api_key_manager import key_manager
except ImportError:
    # Fallback for standalone testing if needed, or just let it fail
    import sys
    print("⚠️ Warning: api_key_manager not found relative to this script.")
    key_manager = None

# ------------------------------
# Constants
# ------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "data_sources.yaml"
BASE_URL = "https://www.alphavantage.co/query"


@dataclass
class EconomicIndicator:
    """Single macroeconomic indicator"""
    symbol: str
    name: str
    value: float
    date: str
    unit: str
    meta: Optional[Dict] = None

    def to_dict(self) -> Dict:
        data = asdict(self)
        # 使用带时区的 UTC 时间
        data["fetched_at"] = datetime.now(timezone.utc).isoformat()
        return data


class AlphaEconomicFetcher:
    """
    Alpha Vantage Economic Indicators Fetcher (Write-Only)
    """

    def __init__(
        self,
        config_path: Optional[Path] = None,
        base_url: str = BASE_URL
    ):
        self.base_url = base_url
        self.name = "AlphaEconomicFetcher"
        
        # 路径处理
        self.config_path = config_path if config_path else DEFAULT_CONFIG_PATH
        
        self.cache_dir = PROJECT_ROOT / "data" / "cache" / "economic_indicators"
        self.indicators_config = []

        self._load_config()
        
        # Ensure cache directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _load_config(self):
        """Load configuration safely"""
        if not self.config_path.exists():
            print(f"[{self.name}] ⚠️ Config file not found: {self.config_path}")
            return

        try:
            with self.config_path.open("r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            
            econ_config = config.get("data_sources", {}).get("economic_indicators", {})
            
            # 如果配置里指定了 cache_dir，覆盖默认值
            if "cache_dir" in econ_config:
                self.cache_dir = Path(econ_config["cache_dir"])
            
            self.indicators_config = econ_config.get("indicators", [])
            
        except Exception as e:
            print(f"[{self.name}] ✗ Error loading config: {e}")

    # ────────────────────────── Cache Management (UTC Filenames) ────────────────────────── #

    def _save_indicators(self, indicators: Dict[str, EconomicIndicator]) -> Path:
        """
        Save indicators to JSON file using ISO 8601 UTC naming.
        Format: economic_indicators_YYYYMMDDTHHMMSSZ.json
        """
        now_utc = datetime.now(timezone.utc)
        
        # 使用 T 分隔符和 Z 后缀
        timestamp_str = now_utc.strftime("%Y%m%dT%H%M%SZ")
        filename = f"economic_indicators_{timestamp_str}.json"
        filepath = self.cache_dir / filename

        data = {
            "timestamp": int(now_utc.timestamp()), # 保留一个整数时间戳方便某些旧逻辑
            "fetched_at": now_utc.isoformat(),
            "indicators": {k: v.to_dict() for k, v in indicators.items()}
        }

        try:
            with filepath.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"  💾 Saved to: {filepath.name}")
            return filepath
        except Exception as e:
            print(f"[{self.name}] ✗ Failed to save file: {e}")
            return Path("")

    # ────────────────────────── API Requests ────────────────────────── #

    def _handle_invalid_key(self, api_key: str, message: str) -> None:
        """Invalidate API key"""
        if key_manager and hasattr(key_manager, "invalidate_key"):
            try:
                key_manager.invalidate_key(api_key, reason=message)
            except TypeError:
                key_manager.invalidate_key(api_key)

    def _make_request(self, params: Dict) -> Optional[Dict]:
        """Unified API request handling with key rotation"""
        if not key_manager:
            print(f"  [{self.name}] ❌ Key Manager not loaded.")
            return None

        api_key = key_manager.get_key()
        if not api_key:
            print(f"  [{self.name}] ⚠ No available API key!")
            return None

        # 速率限制等待
        wait_time = key_manager.wait_if_needed(api_key)
        if wait_time > 0:
            print(f"  [{self.name}] Waiting {wait_time:.1f}s for rate limit...")
            time.sleep(wait_time)

        params["apikey"] = api_key

        try:
            response = requests.get(self.base_url, params=params, timeout=10)
            key_manager.record_usage(api_key)
            data = response.json()

            # API 错误处理
            error_msg = data.get("Error Message") or data.get("Information")
            if error_msg:
                print(f"  [{self.name}] ✗ API Error: {error_msg}")
                if "apikey" in error_msg.lower() or "invalid or missing" in error_msg.lower():
                    self._handle_invalid_key(api_key, error_msg)
                return None

            if "Note" in data:
                print(f"  [{self.name}] ✗ Rate Limit Note: {data['Note']}")
                return None

            return data

        except Exception as exc:
            print(f"  [{self.name}] ✗ Request error: {exc}")
            return None

    def _extract_latest(self, data: Dict) -> Optional[Dict]:
        """Extract latest data point"""
        entries = data.get("data") if data else None
        if not entries:
            return None
        return entries[0]

    def _create_indicator(
        self,
        symbol: str,
        name: str,
        unit: str,
        raw_entry: Dict,
        meta: Optional[Dict] = None,
    ) -> Optional[EconomicIndicator]:
        if not raw_entry:
            return None
        try:
            value = float(raw_entry["value"])
        except (KeyError, TypeError, ValueError):
            return None

        return EconomicIndicator(
            symbol=symbol,
            name=name,
            value=value,
            date=raw_entry.get("date", ""),
            unit=unit,
            meta=meta,
        )

    # ────────────────────────── Single Indicator Fetch ────────────────────────── #

    def get_federal_funds_rate(self) -> Optional[EconomicIndicator]:
        params = {"function": "FEDERAL_FUNDS_RATE"}
        data = self._make_request(params)
        latest = self._extract_latest(data)
        return self._create_indicator(
            symbol="FEDERAL_FUNDS_RATE",
            name="Federal Funds Rate",
            unit="%",
            raw_entry=latest,
        )

    def get_cpi(self, interval: str = "monthly") -> Optional[EconomicIndicator]:
        params = {"function": "CPI", "interval": interval}
        data = self._make_request(params)
        latest = self._extract_latest(data)
        return self._create_indicator(
            symbol=f"CPI_{interval.upper()}",
            name=f"CPI ({interval})",
            unit="Index",
            raw_entry=latest,
            meta={"interval": interval},
        )

    def get_unemployment(self) -> Optional[EconomicIndicator]:
        params = {"function": "UNEMPLOYMENT"}
        data = self._make_request(params)
        latest = self._extract_latest(data)
        return self._create_indicator(
            symbol="UNEMPLOYMENT",
            name="Unemployment Rate",
            unit="%",
            raw_entry=latest,
        )

    def get_real_gdp(self, interval: str = "quarterly") -> Optional[EconomicIndicator]:
        params = {"function": "REAL_GDP", "interval": interval}
        data = self._make_request(params)
        latest = self._extract_latest(data)
        return self._create_indicator(
            symbol=f"REAL_GDP_{interval.upper()}",
            name=f"Real GDP ({interval})",
            unit="Billions of Dollars",
            raw_entry=latest,
            meta={"interval": interval},
        )

    def get_treasury_yield(
        self,
        maturity: str = "10year",
        interval: str = "monthly",
    ) -> Optional[EconomicIndicator]:
        params = {
            "function": "TREASURY_YIELD",
            "interval": interval,
            "maturity": maturity,
        }
        data = self._make_request(params)
        latest = self._extract_latest(data)
        return self._create_indicator(
            symbol=f"TREASURY_YIELD_{maturity.upper()}_{interval.upper()}",
            name=f"Treasury Yield {maturity} ({interval})",
            unit="%",
            raw_entry=latest,
            meta={"maturity": maturity, "interval": interval},
        )

    # ────────────────────────── Batch Fetch (Core Logic) ────────────────────────── #
    
    def _fetch_fresh_data(self) -> Dict[str, EconomicIndicator]:
        """(Internal) Fetch fresh data from API"""
        tasks = {
            "federal_funds_rate": self.get_federal_funds_rate,
            "cpi": lambda: self.get_cpi(interval="monthly"),
            "unemployment": self.get_unemployment,
            "real_gdp": lambda: self.get_real_gdp(interval="quarterly"),
            "treasury_10y": lambda: self.get_treasury_yield(maturity="10year"),
            "treasury_2y": lambda: self.get_treasury_yield(maturity="2year"),
        }

        print(f"\n🌐 Fetching {len(tasks)} economic indicators from API...")
        print("=" * 60)

        results = {}
        for name, func in tasks.items():
            print(f"\n[{name}]")
            try:
                indicator = func()
                if indicator:
                    results[name] = indicator
                    print(f"  ✓ {indicator.value} {indicator.unit} (as of {indicator.date})")
                else:
                    print("  ✗ Failed to fetch")
            except Exception as e:
                print(f"  ✗ Error executing task: {e}")

        print("\n" + "=" * 60)
        print(f"Fetched {len(results)}/{len(tasks)} indicators")

        return results

    # ────────────────────────── Scheduler Entry Point ────────────────────────── #

    def download_all_data(self) -> bool:
        """
        Execute full download and save process.
        Returns True if data was saved, False otherwise.
        """
        print(f"\n[{self.name}] 🚀 Executing scheduled download...")
        
        # 1. 总是执行拉取
        indicators = self._fetch_fresh_data()
        
        # 2. 如果拉取到了数据，就保存
        if indicators:
            saved_path = self._save_indicators(indicators)
            if saved_path:
                print(f"[{self.name}] ✅ Download complete.")
                return True
        
        print(f"[{self.name}] ⚠️  Download executed, but no data was fetched or saved.")
        return False

    @staticmethod
    def indicators_to_dataframe(indicators: Dict[str, EconomicIndicator]) -> pd.DataFrame:
        if not indicators:
            return pd.DataFrame()
        records = [item.to_dict() for item in indicators.values()]
        df = pd.DataFrame(records)
        if "symbol" in df.columns:
            df = df.set_index("symbol")
        return df


# ────────────────────────── Test Entry ────────────────────────── #

if __name__ == "__main__":
    
    # 简单的本地测试逻辑
    print("=" * 60)
    print("Testing AlphaEconomicFetcher (Scheduler-Only Mode)")
    print("=" * 60)

    # 实例化 fetcher (会尝试使用默认路径)
    fetcher = AlphaEconomicFetcher()

    # 模拟调度器调用
    print("\n[Scheduler Call - Executing download_all_data]")
    success = fetcher.download_all_data()

    if success:
        print("\n✅ Test run finished successfully.")
    else:
        print("\n❌ Test run finished with errors or no data.")