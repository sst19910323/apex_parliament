# data/finnhub_news_fetcher.py (V5.4 - ISO 8601 UTC Standard)

"""
Finnhub Company News Fetcher (Write-Only Executor) - Backtest Ready
(V5.4 - ISO 8601 UTC Standard)

- 职责: 纯粹的“写入”执行器。
- 逻辑: 全链路强制大写 (GENERAL, BRK.B)。
- 命名: 使用 ISO 8601 Basic Format (YYYYMMDDTHHMMSSZ) 格式化文件名。
- 时区: 强制 UTC (Zulu Time) 归一化。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import List, Optional, Dict, Any, Union
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, date, timezone
import requests
import yaml


# ------------------------------
# Helper Utilities (Absolute Time)
# ------------------------------

def ensure_utc(dt: datetime) -> datetime:
    """
    数据存储的唯一真理：UTC。
    如果传入的是 naive 时间，默认视为 UTC。
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass
class NewsArticle:
    """News article data structure"""
    category: str
    datetime: int
    headline: str
    id: int
    image: str
    related: str
    source: str
    summary: str
    url: str
    
    @property
    def datetime_str(self) -> str:
        # 显示时也建议统一为 UTC，或者标明时区
        return datetime.fromtimestamp(self.datetime, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')


class FinnhubNewsFetcher:
    """Finnhub news fetcher (Write-Only)"""
    
    def __init__(self, api_key: Optional[str] = None, config_path: str = "config/data_sources.yaml"):
        # 自动寻找 config
        self.config_file = Path(config_path)
        if not self.config_file.exists():
            # Fallback path logic
            self.config_file = Path(__file__).resolve().parents[1] / "config/data_sources.yaml"

        self.config = self._load_config()
        
        self.api_key = api_key or self.config.get('api_key1')
        self.cache_dir = Path(self.config.get('cache_dir', 'data/news'))
        self.default_days = self.config.get('days_back', 7)
        self.news_limit = self.config.get('news_limit', 50)
        
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.base_url = "https://finnhub.io/api/v1"
        self.rate_limit_delay = 1.0 
    
    def _load_config(self) -> Dict[str, Any]:
        if not self.config_file.exists(): return {}
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                full_config = yaml.safe_load(f)
            return full_config.get('data_sources', {}).get('news', {})
        except:
            return {}
    
    # 🔥🔥🔥 修正 1：ISO 8601 UTC 命名
    def _save_to_cache(self, cache_key: str, articles: List[NewsArticle], target_dt: datetime) -> Path: 
        """
        Save to cache. 使用 target_dt 的 ISO 8601 UTC 字符串命名。
        Format: {SYMBOL}_news_{YYYYMMDDTHHMMSSZ}.json
        """
        safe_key = cache_key.upper()
        
        key_dir = self.cache_dir / safe_key
        key_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. 确保 UTC
        target_utc = ensure_utc(target_dt)
        
        # 2. 生成 ISO 8601 字符串 (带 T 分隔符)
        timestamp_str = target_utc.strftime("%Y%m%dT%H%M%SZ")
        
        # e.g. data/news/SPY/SPY_news_20250101T100000Z.json
        cache_path = key_dir / f"{safe_key}_news_{timestamp_str}.json"
        
        try:
            data = [asdict(article) for article in articles]
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            print(f"[FINNHUB_NEWS][INFO] Saved {len(articles)} articles to: {cache_path.name}")
            return cache_path
        
        except Exception as e:
            print(f"[FINNHUB_NEWS][ERROR] Failed to save cache: {e}")
            raise 

    def _make_request(self, url: str, params: dict, context: str) -> Optional[List[NewsArticle]]:
        """通用请求处理"""
        try:
            if not self.api_key: return None
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if not data:
                return []
            
            if isinstance(data, list):
                if len(data) > self.news_limit:
                    data = data[:self.news_limit]
                
                # API返回的是Unix timestamps
                articles = [NewsArticle(**item) for item in data]
                articles.sort(key=lambda x: x.datetime, reverse=True)
                
                time.sleep(self.rate_limit_delay)
                return articles
            return []
            
        except Exception as e:
            print(f"[FINNHUB_NEWS][ERROR] API request failed for {context}: {e}")
            return None

    # --- Helper: Time Logic ---

    def _normalize_end_date(self, end_date: Optional[Union[str, datetime, date]]) -> datetime:
        """
        将输入的 end_date 归一化为 UTC datetime 对象。
        如果为 None，则返回当前 UTC 时间。
        """
        dt = None
        if end_date is None:
            dt = datetime.now(timezone.utc)
        elif isinstance(end_date, str):
            try:
                dt = datetime.strptime(end_date, '%Y-%m-%d')
            except ValueError:
                try:
                    dt = datetime.strptime(end_date, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    print(f"[FINNHUB_NEWS][WARN] Invalid date format '{end_date}', utilizing NOW (UTC).")
                    dt = datetime.now(timezone.utc)
        elif isinstance(end_date, date) and not isinstance(end_date, datetime):
            dt = datetime.combine(end_date, datetime.min.time())
        elif isinstance(end_date, datetime):
            dt = end_date
        else:
            dt = datetime.now(timezone.utc)
            
        return ensure_utc(dt)

    # --- Fetcher 1: 公司新闻 ---
    
    def _fetch_company_news_from_api(self, symbol: str, from_date: str, to_date: str) -> Optional[List[NewsArticle]]:
        url = f"{self.base_url}/company-news"
        params = {
            'symbol': symbol, 
            'from': from_date,
            'to': to_date,
            'token': self.api_key
        }
        return self._make_request(url, params, context=symbol)

    # --- Fetcher 2: 宏观新闻 ---

    def _fetch_general_news_from_api(self, category: str) -> Optional[List[NewsArticle]]:
        url = f"{self.base_url}/news"
        params = {
            'category': category.lower(), 
            'token': self.api_key
        }
        return self._make_request(url, params, context=category)

    # ────────────────────────── 调度器入口点 ────────────────────────── #

    def download_company_news(self, symbol: str, days: Optional[int] = None, end_date: Optional[Union[str, datetime]] = None) -> bool:
        """
        下载公司新闻 (支持回测时间)
        symbol: 外部传入大写 (e.g. "BRK.B")
        end_date: 可选。如果提供，则抓取该日期之前的数据 (格式: 'YYYY-MM-DD' 或 datetime)
        """
        symbol_upper = symbol.upper()
        
        # 计算时间窗口 (target_date 既用于 API 请求，也用于文件名命名)
        target_date = self._normalize_end_date(end_date)
        days_back = days or self.default_days
        from_date = target_date - timedelta(days=days_back)
        
        # 格式化为 Finnhub API 需要的 'YYYY-MM-DD'
        to_str = target_date.strftime('%Y-%m-%d')
        from_str = from_date.strftime('%Y-%m-%d')

        print(f"\n[FINNHUB_NEWS] 🚀 Downloading COMPANY: {symbol_upper} | Range: {from_str} -> {to_str}...")
        
        articles = self._fetch_company_news_from_api(
            symbol_upper, 
            from_str, 
            to_str
        )
        
        if articles is None: return False

        try:
            # 传递 target_date，内部会转为 ISO 8601 UTC 文件名
            self._save_to_cache(symbol_upper, articles, target_date)
            return True
        except:
            return False

    def download_general_news(self, category: str = 'GENERAL', end_date: Optional[Union[str, datetime]] = None) -> bool:
        """
        下载宏观新闻
        """
        category_upper = category.upper()
        
        # 使用传入的日期作为文件名时间戳 (即使 API 可能忽略日期)
        target_date = self._normalize_end_date(end_date)
        
        if end_date is not None:
            print(f"[FINNHUB_NEWS][WARN] 'end_date' passed for GENERAL news ({target_date.date()}), but Finnhub General API usually ignores dates and returns LATEST.")
        
        print(f"\n[FINNHUB_NEWS] 🚀 Downloading GENERAL: {category_upper}...")
        
        articles = self._fetch_general_news_from_api(category_upper)
        
        if articles is None: return False
        
        try:
            # 传递 target_date
            self._save_to_cache(category_upper, articles, target_date)
            return True
        except:
            return False

# ────────────────────────── Test Entry ────────────────────────── #

if __name__ == "__main__":
    print("Testing FinnhubNewsFetcher (V5.4 UTC Standard)...")
    try:
        fetcher = FinnhubNewsFetcher() 
        
        # Test 1: SPY (Historical Backtest Simulation)
        print("\n--- Test SPY (Historical: 2025-01-01 10:00:00 UTC) ---")
        # 模拟回测时间
        test_dt = datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        
        success = fetcher.download_company_news("SPY", days=7, end_date=test_dt)
        
        if success:
            print("✅ Download executed.")
        else:
            print("❌ Download failed.")

    except Exception as e:
        print(f"Test skipped or failed: {e}")