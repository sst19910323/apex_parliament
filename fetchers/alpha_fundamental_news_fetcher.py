"""
alpha_fundamental_news_fetcher.py

基于 Alpha Vantage 的公司基础信息 & 新闻抓取器
- 公司基本面：市值、PE、PEG、EPS、股息、Beta、行业等
- 新闻：来源、发布时间、情绪分数、关联度等
- 需要 Alpha Vantage API key（通过 api_key_manager 管理）
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
import requests
import time

from .api_key_manager import key_manager

BASE_URL = "https://www.alphavantage.co/query"


# ──────────────────────────── 数据结构 ──────────────────────────── #

@dataclass
class CompanyFundamentals:
    """公司基础信息快照（Alpha Vantage OVERVIEW）"""
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
    last_updated: Optional[str] = None

    def to_dict(self) -> Dict[str, Optional[float]]:
        return asdict(self)


@dataclass
class NewsItem:
    """单条新闻记录（Alpha Vantage NEWS_SENTIMENT）"""
    symbol: str
    title: str
    url: str
    published: str
    source: str
    summary: str
    sentiment_score: Optional[float]
    sentiment_label: Optional[str]
    relevance_score: Optional[float]

    def to_dict(self) -> Dict[str, Optional[str]]:
        return asdict(self)


# ──────────────────────────── 主抓取器 ──────────────────────────── #

class AlphaFundamentalNewsFetcher:
    """
    Alpha Vantage 基本面 & 新闻数据抓取器。
    """

    def __init__(self):
        self.name = "AlphaFundamentalNewsFetcher"

    # -------- 工具函数 -------- #

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        if symbol.startswith("^"):
            return symbol
        return symbol.replace(".US", "")

    @staticmethod
    def _to_float(value: Optional[str]) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _make_request(self, params: Dict) -> Optional[Dict]:
        api_key = key_manager.get_key()
        if not api_key:
            print(f"  [{self.name}] ✗ No available API key")
            return None

        wait_time = key_manager.wait_if_needed(api_key)
        if wait_time > 0:
            print(f"  [{self.name}] Waiting {wait_time:.1f}s for rate limit...")
            time.sleep(wait_time)

        params["apikey"] = api_key

        try:
            response = requests.get(BASE_URL, params=params, timeout=10)
            key_manager.record_usage(api_key)
            data = response.json()

            if "Error Message" in data:
                print(f"  [{self.name}] ✗ API Error: {data['Error Message']}")
                return None

            if "Note" in data:
                print(f"  [{self.name}] ✗ Rate Limit: {data['Note']}")
                return None

            if "Information" in data:
                print(f"  [{self.name}] ⚠ Info: {data['Information']}")
                return None

            return data

        except Exception as exc:
            print(f"  [{self.name}] ✗ Request error: {exc}")
            return None

    # -------- 公司基础信息 -------- #

    def get_company_fundamentals(
        self,
        symbol: str,
        retry: int = 2,
    ) -> Optional[CompanyFundamentals]:
        """
        拉取单个公司的基础信息（OVERVIEW）。
        """
        symbol = self.normalize_symbol(symbol)

        for attempt in range(retry):
            params = {
                "function": "OVERVIEW",
                "symbol": symbol,
            }
            data = self._make_request(params)
            if not data:
                if attempt < retry - 1:
                    time.sleep(2)
                continue

            if "Symbol" not in data:
                if attempt < retry - 1:
                    time.sleep(2)
                continue

            fundamentals = CompanyFundamentals(
                symbol=data.get("Symbol", symbol),
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
                last_updated=datetime.utcnow().isoformat(),
            )
            return fundamentals

        print(f"  [{self.name}] ✗ Failed to get fundamentals for {symbol}")
        return None

    def get_batch_fundamentals(
        self,
        symbols: List[str],
    ) -> Dict[str, CompanyFundamentals]:
        results: Dict[str, CompanyFundamentals] = {}
        for symbol in symbols:
            fundamentals = self.get_company_fundamentals(symbol)
            if fundamentals:
                results[fundamentals.symbol] = fundamentals
        return results

    def fundamentals_to_dataframe(
        self,
        fundamentals: CompanyFundamentals,
    ) -> pd.DataFrame:
        df = pd.DataFrame([fundamentals.to_dict()]).set_index("symbol")
        return df

    def batch_fundamentals_to_dataframe(
        self,
        fundamentals_dict: Dict[str, CompanyFundamentals],
    ) -> pd.DataFrame:
        records = [item.to_dict() for item in fundamentals_dict.values()]
        if not records:
            return pd.DataFrame()
        df = pd.DataFrame(records).set_index("symbol")
        return df

    # -------- 新闻 -------- #

    def get_news(
        self,
        symbol: str,
        limit: int = 20,
        retry: int = 2,
    ) -> List[NewsItem]:
        symbol = self.normalize_symbol(symbol)

        for attempt in range(retry):
            params = {
                "function": "NEWS_SENTIMENT",
                "tickers": symbol,
                "limit": limit,
            }
            data = self._make_request(params)
            if not data:
                if attempt < retry - 1:
                    time.sleep(2)
                continue

            if "feed" not in data:
                if attempt < retry - 1:
                    time.sleep(2)
                continue

            news_items: List[NewsItem] = []
            for entry in data["feed"]:
                ticker_sentiment = None
                for ts in entry.get("ticker_sentiment", []):
                    if ts.get("ticker") == symbol:
                        ticker_sentiment = ts
                        break

                news_items.append(
                    NewsItem(
                        symbol=symbol,
                        title=entry.get("title", "N/A"),
                        url=entry.get("url", ""),
                        published=entry.get("time_published", ""),
                        source=entry.get("source", "Unknown"),
                        summary=entry.get("summary", ""),
                        sentiment_score=self._to_float(
                            ticker_sentiment.get("ticker_sentiment_score")
                            if ticker_sentiment else None
                        ),
                        sentiment_label=(
                            ticker_sentiment.get("ticker_sentiment_label")
                            if ticker_sentiment else None
                        ),
                        relevance_score=self._to_float(
                            ticker_sentiment.get("relevance_score")
                            if ticker_sentiment else None
                        ),
                    )
                )

            if news_items:
                return news_items

        print(f"  [{self.name}] ✗ Failed to get news for {symbol}")
        return []

    def get_batch_news(
        self,
        symbols: List[str],
        limit: int = 20,
    ) -> Dict[str, List[NewsItem]]:
        results: Dict[str, List[NewsItem]] = {}
        for symbol in symbols:
            items = self.get_news(symbol, limit=limit)
            if items:
                results[self.normalize_symbol(symbol)] = items
        return results

    def news_to_dataframe(self, news_items: List[NewsItem]) -> pd.DataFrame:
        if not news_items:
            return pd.DataFrame()
        df = pd.DataFrame([item.to_dict() for item in news_items])
        if not df.empty:
            df["published"] = pd.to_datetime(df["published"], errors="coerce")
            df = df.sort_values("published", ascending=False)
        return df


# ──────────────────────────── 简单测试 ──────────────────────────── #

if __name__ == "__main__":
    fetcher = AlphaFundamentalNewsFetcher()
    ticker = "AAPL"

    print("\n[Company Fundamentals]")
    fundamentals = fetcher.get_company_fundamentals(ticker)
    if fundamentals:
        print(fundamentals.to_dict())

    print("\n[News]")
    news_items = fetcher.get_news(ticker, limit=5)
    for item in news_items:
        print(item.to_dict())

    if fundamentals:
        df_fund = fetcher.fundamentals_to_dataframe(fundamentals)
        print("\nFundamentals DataFrame:")
        print(df_fund.T)

    if news_items:
        df_news = fetcher.news_to_dataframe(news_items)
        print("\nNews DataFrame:")
        print(df_news.head())