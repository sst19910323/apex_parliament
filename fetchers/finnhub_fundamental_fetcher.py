"""
data/finnhub_fundamental_fetcher.py

从 Finnhub 获取公司基本面数据（带缓存和 YAML 配置）
"""

import json
import time
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict
from datetime import datetime
import requests
import yaml


@dataclass
class CompanyFundamentals:
    """公司基本面数据"""
    symbol: str
    name: str
    country: str
    currency: str
    exchange: str
    industry: str
    ipo_date: str
    market_cap: float
    outstanding_shares: float
    logo_url: str
    phone: str
    weburl: str
    
    # 财务指标
    pe_ratio: Optional[float] = None
    eps: Optional[float] = None
    beta: Optional[float] = None
    dividend_yield: Optional[float] = None
    week_52_high: Optional[float] = None
    week_52_low: Optional[float] = None
    
    # 元数据
    fetched_at: Optional[str] = None
    
    @classmethod
    def from_api_response(cls, symbol: str, data: Dict[str, Any]) -> 'CompanyFundamentals':
        """从 API 响应创建对象"""
        metric = data.get('metric', {})
        
        return cls(
            symbol=symbol,
            name=data.get('name', ''),
            country=data.get('country', ''),
            currency=data.get('currency', ''),
            exchange=data.get('exchange', ''),
            industry=data.get('finnhubIndustry', ''),
            ipo_date=data.get('ipo', ''),
            market_cap=data.get('marketCapitalization', 0.0),
            outstanding_shares=data.get('shareOutstanding', 0.0),
            logo_url=data.get('logo', ''),
            phone=data.get('phone', ''),
            weburl=data.get('weburl', ''),
            pe_ratio=metric.get('peNormalizedAnnual'),
            eps=metric.get('epsBasicExclExtraItemsNormalizedAnnual'),
            beta=metric.get('beta'),
            dividend_yield=metric.get('dividendYieldIndicatedAnnual'),
            week_52_high=metric.get('52WeekHigh'),
            week_52_low=metric.get('52WeekLow'),
            fetched_at=datetime.now().isoformat()
        )


class FinnhubFundamentalFetcher:
    """Finnhub 公司基本面获取器"""
    
    def __init__(self, api_key: Optional[str] = None, config_path: str = "config/data_sources.yaml"):
        """初始化"""
        self.config = self._load_config(config_path)
        self.api_key = api_key or self.config.get('api_key')
        
        if not self.api_key:
            raise ValueError("Finnhub API key not provided and not found in config")
        
        # 缓存配置
        self.cache_dir = Path(self.config.get('cache_dir', 'data/fundamentals'))
        self.cache_ttl = self.config.get('cooldown', 86400)
        
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # API 配置
        self.base_url = "https://finnhub.io/api/v1"
        self.rate_limit_delay = 1.0
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """加载 YAML 配置"""
        config_file = Path(config_path)
        
        if not config_file.exists():
            return {}
        
        with open(config_file, 'r', encoding='utf-8') as f:
            full_config = yaml.safe_load(f)
        
        return full_config.get('data_sources', {}).get('fundamentals', {})
    
    def _get_cache_path(self, symbol: str) -> Optional[Path]:
        """获取最新的缓存文件路径（如果存在）"""
        symbol_dir = self.cache_dir / symbol
        
        if not symbol_dir.exists():
            return None
        
        # 查找所有缓存文件
        pattern = f"{symbol}_fundamentals_*.json"
        existing_files = list(symbol_dir.glob(pattern))
        
        if not existing_files:
            return None
        
        # 返回最新的文件
        return max(existing_files, key=lambda p: p.stat().st_mtime)
    
    def _is_cache_valid(self, cache_path: Path) -> bool:
        """检查缓存是否有效"""
        if not cache_path or not cache_path.exists():
            return False
        
        cache_age = time.time() - cache_path.stat().st_mtime
        return cache_age < self.cache_ttl
    
    def _load_from_cache(self, symbol: str) -> Optional[CompanyFundamentals]:
        """从缓存加载"""
        cache_path = self._get_cache_path(symbol)
        
        if not self._is_cache_valid(cache_path):
            return None
        
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            print(f"[FINNHUB_FUNDAMENTALS][INFO] Loaded {symbol} from cache: {cache_path.name}")
            return CompanyFundamentals(**data)
        
        except Exception as e:
            print(f"[FINNHUB_FUNDAMENTALS][ERROR] Failed to load cache: {e}")
            return None
    
    def _save_to_cache(self, fundamentals: CompanyFundamentals) -> None:
        """保存到缓存（带时间戳）"""
        symbol = fundamentals.symbol
        symbol_dir = self.cache_dir / symbol
        symbol_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成新文件名（带时间戳）
        timestamp = int(time.time())
        cache_path = symbol_dir / f"{symbol}_fundamentals_{timestamp}.json"
        
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(asdict(fundamentals), f, indent=2, ensure_ascii=False)
            
            print(f"[FINNHUB_FUNDAMENTALS][INFO] Saved {symbol} to: {cache_path.name}")
            
            # 清理旧文件（只保留最新的）
            self._cleanup_old_files(symbol_dir, symbol)
        
        except Exception as e:
            print(f"[FINNHUB_FUNDAMENTALS][ERROR] Failed to save cache: {e}")
    
    def _cleanup_old_files(self, symbol_dir: Path, symbol: str) -> None:
        """清理旧的缓存文件（已禁用 - 由统一的 watch 任务管理）"""
        # 🔥 禁用自动清理，由外部 watch 任务统一管理历史数据
        pass
    
    def _fetch_from_api(self, symbol: str) -> Optional[CompanyFundamentals]:
        """从 API 获取数据"""
        url = f"{self.base_url}/stock/profile2"
        params = {
            'symbol': symbol,
            'token': self.api_key
        }
        
        try:
            print(f"[FINNHUB_FUNDAMENTALS][INFO] Fetching {symbol} from API...")
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if not data or 'name' not in data:
                print(f"[FINNHUB_FUNDAMENTALS][ERROR] No data found for {symbol}")
                return None
            
            fundamentals = CompanyFundamentals.from_api_response(symbol, data)
            
            # 保存到缓存
            self._save_to_cache(fundamentals)
            
            # 速率限制
            time.sleep(self.rate_limit_delay)
            
            return fundamentals
        
        except requests.exceptions.RequestException as e:
            print(f"[FINNHUB_FUNDAMENTALS][ERROR] API request failed: {e}")
            return None
        except Exception as e:
            print(f"[FINNHUB_FUNDAMENTALS][ERROR] Unexpected error: {e}")
            return None
    
    def get_fundamentals(self, symbol: str, force_refresh: bool = False) -> Optional[CompanyFundamentals]:
        """
        获取公司基本面数据
        
        Args:
            symbol: 股票代码
            force_refresh: 是否强制刷新（忽略缓存）
        
        Returns:
            CompanyFundamentals 对象，失败返回 None
        """
        # 检查缓存
        if not force_refresh:
            cached = self._load_from_cache(symbol)
            if cached:
                return cached
        
        # 从 API 获取
        return self._fetch_from_api(symbol)


# ────────────────────────── 测试入口 ────────────────────────── #

if __name__ == "__main__":
    import os
    
    # 优先使用环境变量，否则使用 YAML 配置
    api_key = os.getenv("FINNHUB_API_KEY")
    
    fetcher = FinnhubFundamentalFetcher(api_key=api_key)
    
    print("=" * 60)
    print("Testing FinnhubFundamentalFetcher")
    print("=" * 60)
    
    # 第一次调用（应该从 API 获取）
    print("\n[First call - should fetch from API if no valid cache]")
    fund1 = fetcher.get_fundamentals("BRK.B")
    
    if fund1:
        print(f"\nSymbol: {fund1.symbol}")
        print(f"Name: {fund1.name}")
        print(f"Industry: {fund1.industry}")
        print(f"Country: {fund1.country}")
        print(f"Market Cap: ${fund1.market_cap:,.0f}M")
        print(f"PE Ratio: {fund1.pe_ratio}")
        print(f"EPS: ${fund1.eps}")
        print(f"Beta: {fund1.beta}")
        print(f"52W High: ${fund1.week_52_high}")
        print(f"52W Low: ${fund1.week_52_low}")
        print(f"Website: {fund1.weburl}")
    
    # # 第二次调用（应该使用缓存）
    # print("\n[Second call - should use cache]")
    # fund2 = fetcher.get_fundamentals("AAPL")
    
    # if fund2:
    #     print(f"Loaded from cache: {fund2.name}")
    
    # # 强制刷新
    # print("\n[Force refresh]")
    # fund3 = fetcher.get_fundamentals("AAPL", force_refresh=True)
    
    # if fund3:
    #     print(f"Force refreshed: {fund3.name}")