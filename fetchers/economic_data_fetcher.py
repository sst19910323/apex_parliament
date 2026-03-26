"""
Economic Data Fetcher (Event-Based / Mock)
职责: 为回测提供严格符合“发布时间”的宏观经济数据。
机制: 基于事件(Release Date)的查找，杜绝未来函数。
剧本: 包含 2024-2025 真实/预测日历，以及 2025 Q4 的“政府停摆”延迟发布黑天鹅。
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
import yaml

# 配置日志
log = logging.getLogger(__name__)

class EconomicDataFetcher:
    def __init__(self, config_path: str = "config/data_sources.yaml"):
        self.config = self._load_config(config_path)
        self.cache_dir = Path(self.config.get("cache_dir", "backtest/economic"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # === 1. 元数据模板 ===
        self.INDICATOR_METADATA = {
            "fed_rate": {
                "key": "federal_funds_rate",
                "symbol": "FEDERAL_FUNDS_RATE",
                "name": "Federal Funds Rate",
                "unit": "%",
                "meta": None
            },
            "cpi_yoy": {
                "key": "cpi",
                "symbol": "CPI_MONTHLY",
                "name": "CPI (monthly YoY)",
                "unit": "Index",
                "meta": {"interval": "monthly"}
            },
            "unemployment": {
                "key": "unemployment",
                "symbol": "UNEMPLOYMENT",
                "name": "Unemployment Rate",
                "unit": "%",
                "meta": None
            },
            "gdp_real_qoq": {
                "key": "real_gdp",
                "symbol": "REAL_GDP_QUARTERLY",
                "name": "Real GDP (Annualized)",
                "unit": "Billions of Dollars",
                "meta": {"interval": "quarterly"}
            },
            # 市场数据：虽然是实时的，但为了统一接口，我们假设每天都能取到最新的"昨日收盘"
            # 这里简化为每月更新，发布日为当月1号
            "us10y": {
                "key": "treasury_10y",
                "symbol": "TREASURY_YIELD_10YEAR_MONTHLY",
                "name": "Treasury Yield 10year",
                "unit": "%",
                "meta": {"maturity": "10year"}
            },
            "us2y": {
                "key": "treasury_2y",
                "symbol": "TREASURY_YIELD_2YEAR_MONTHLY",
                "name": "Treasury Yield 2year",
                "unit": "%",
                "meta": {"maturity": "2year"}
            }
        }

        # === 2. 事件驱动数据表 (Release Date -> Value) ===
        # 只有当 target_date >= release_date 时，系统才能看到这条数据。
        
        self.DATA_EVENTS = {
            # --- FOMC Rate Decision (发布日 = 会议结束日) ---
            "fed_rate": [
                {"release": "2024-09-18", "value": 4.75}, # Cut 50bps
                {"release": "2024-11-07", "value": 4.50}, # Cut 25bps
                {"release": "2024-12-18", "value": 4.25}, # Cut 25bps
                {"release": "2025-01-29", "value": 4.25}, # Hold (Inflation rebound?)
                {"release": "2025-03-19", "value": 4.00}, # Cut 25bps
                {"release": "2025-05-07", "value": 4.00}, # Hold
                {"release": "2025-06-18", "value": 3.75}, # Cut 25bps
                {"release": "2025-07-30", "value": 3.75}, # Hold
                {"release": "2025-09-17", "value": 3.50}, # Cut 25bps
                {"release": "2025-10-29", "value": 3.50}, # Hold
                {"release": "2025-12-10", "value": 3.25}, # Cut 25bps
            ],

            # --- CPI YoY (发布日 = 通常每月10-15号) ---
            "cpi_yoy": [
                {"release": "2024-10-10", "value": 324.8, "ref": "2024-09"},
                {"release": "2024-11-13", "value": 326.1, "ref": "2024-10"},
                {"release": "2024-12-11", "value": 327.5, "ref": "2024-11"},
                {"release": "2025-01-15", "value": 328.2, "ref": "2024-12"},
                {"release": "2025-02-12", "value": 329.0, "ref": "2025-01"},
                {"release": "2025-03-12", "value": 329.8, "ref": "2025-02"},
                {"release": "2025-04-10", "value": 330.5, "ref": "2025-03"},
                {"release": "2025-05-14", "value": 331.2, "ref": "2025-04"},
                {"release": "2025-06-11", "value": 332.0, "ref": "2025-05"},
                {"release": "2025-07-11", "value": 332.8, "ref": "2025-06"},
                {"release": "2025-08-13", "value": 333.5, "ref": "2025-07"},
                # 2025-09 CPI (通常10月发) 因政府停摆延迟
                {"release": "2025-11-20", "value": 334.2, "ref": "2025-09 (Delayed)"}, 
                {"release": "2025-11-20", "value": 335.0, "ref": "2025-10 (Delayed)"}, 
            ],

            # --- Unemployment (发布日 = 通常每月第一个周五) ---
            "unemployment": [
                {"release": "2024-10-04", "value": 4.1, "ref": "2024-09"},
                {"release": "2024-11-01", "value": 4.1, "ref": "2024-10"},
                {"release": "2024-12-06", "value": 4.2, "ref": "2024-11"},
                {"release": "2025-01-10", "value": 4.2, "ref": "2024-12"},
                {"release": "2025-02-07", "value": 4.3, "ref": "2025-01"},
                {"release": "2025-03-07", "value": 4.4, "ref": "2025-02"},
                {"release": "2025-04-04", "value": 4.4, "ref": "2025-03"},
                {"release": "2025-05-02", "value": 4.5, "ref": "2025-04"},
                {"release": "2025-06-06", "value": 4.5, "ref": "2025-05"},
                {"release": "2025-07-03", "value": 4.4, "ref": "2025-06"}, # 周四(因独立日)
                {"release": "2025-08-01", "value": 4.3, "ref": "2025-07"},
                {"release": "2025-09-05", "value": 4.3, "ref": "2025-08"},
                # 2025-10 发布日 (发布9月数据) - 假设正常
                {"release": "2025-10-03", "value": 4.4, "ref": "2025-09"},
                # 2025-11 发布日 (发布10月数据) - 因停摆取消/延迟
                {"release": "2025-11-20", "value": 4.5, "ref": "2025-10 (Delayed)"},
            ],

            # --- Real GDP (发布日 = 季度后第一个月月底) ---
            "gdp_real_qoq": [
                {"release": "2024-10-30", "value": 2.8, "ref": "2024 Q3"},
                {"release": "2025-01-30", "value": 2.7, "ref": "2024 Q4"},
                {"release": "2025-04-24", "value": 2.5, "ref": "2025 Q1"},
                {"release": "2025-07-30", "value": 2.2, "ref": "2025 Q2"},
                {"release": "2025-10-30", "value": 2.0, "ref": "2025 Q3"},
            ],

            # --- Yields (简化为每月1日更新上月均值，模拟市场实时性) ---
            "us10y": [
                {"release": "2024-11-01", "value": 4.28},
                {"release": "2024-12-01", "value": 4.45}, # Trump trade peak?
                {"release": "2025-01-01", "value": 4.40},
                {"release": "2025-02-01", "value": 4.50},
                {"release": "2025-03-01", "value": 4.55},
                {"release": "2025-04-01", "value": 4.60},
                {"release": "2025-05-01", "value": 4.65},
                {"release": "2025-06-01", "value": 4.60},
                {"release": "2025-07-01", "value": 4.55},
                {"release": "2025-08-01", "value": 4.50},
                {"release": "2025-09-01", "value": 4.45},
                {"release": "2025-10-01", "value": 4.40},
                {"release": "2025-11-01", "value": 4.35},
            ],
             "us2y": [
                {"release": "2024-11-01", "value": 4.15},
                {"release": "2024-12-01", "value": 4.25},
                {"release": "2025-01-01", "value": 4.30},
                {"release": "2025-02-01", "value": 4.35},
                {"release": "2025-03-01", "value": 4.40},
                {"release": "2025-04-01", "value": 4.45},
                {"release": "2025-05-01", "value": 4.40},
                {"release": "2025-06-01", "value": 4.35},
                {"release": "2025-07-01", "value": 4.30},
                {"release": "2025-08-01", "value": 4.25},
                {"release": "2025-09-01", "value": 4.20},
                {"release": "2025-10-01", "value": 4.15},
                {"release": "2025-11-01", "value": 4.10},
            ]
        }

    def _load_config(self, path: str) -> Dict:
        try:
            with open(path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            return config.get("data_sources", {}).get("economic_indicators", {})
        except Exception:
            return {}

    def _find_latest_value(self, indicator_key: str, target_date_str: str) -> Optional[Dict]:
        """
        在事件列表中查找 <= target_date 的最新一条数据
        """
        events = self.DATA_EVENTS.get(indicator_key, [])
        latest = None
        
        for event in events:
            if event["release"] <= target_date_str:
                latest = event
            else:
                # 因为事件是按时间排序的（假设），一旦超过 target_date，后面的都不用看了
                # 如果没排序，这里不能 break，要继续找。为了安全起见，这里假设没排序
                continue
                
        return latest

    def fetch_snapshot(self, target_date: datetime) -> Optional[Path]:
        """
        根据目标日期，查找截止到该日期(含)为止，市场已知的最新宏观数据。
        """
        target_date_str = target_date.strftime("%Y-%m-%d")
        fetched_at_iso = target_date.isoformat()
        
        log.info(f"🔎 Fetching Economic Snapshot for market date: {target_date_str}")
        
        indicators_output = {}
        
        for lookup_key, meta in self.INDICATOR_METADATA.items():
            latest_event = self._find_latest_value(lookup_key, target_date_str)
            
            if latest_event:
                output_key = meta["key"]
                
                # 构造符合 V5 格式的指标对象
                indicator_obj = {
                    "symbol": meta["symbol"],
                    "name": meta["name"],
                    "value": latest_event["value"],
                    "date": latest_event["release"], # 这里的 date 指的是数据 Release Date (生效日)
                    "unit": meta["unit"],
                    "meta": meta["meta"],
                    "ref_period": latest_event.get("ref", "N/A"), # 增加参考周期字段 (e.g., "2024-10")
                    "fetched_at": fetched_at_iso
                }
                indicators_output[output_key] = indicator_obj
            else:
                log.warning(f"⚠️ No historical data found for {lookup_key} before {target_date_str}")

        # 构造最终 Payload
        payload = {
            "timestamp": int(target_date.timestamp()),
            "fetched_at": fetched_at_iso,
            "indicators": indicators_output,
            "note": "Mock Data with Realistic Lag & Release Schedule (Event-Based)"
        }

        # 保存
        timestamp = int(target_date.timestamp())
        filename = f"economic_indicators_{timestamp}.json"
        save_path = self.cache_dir / filename

        try:
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            log.info(f"✅ Economic Snapshot Saved: {filename}")
            return save_path
        except Exception as e:
            log.error(f"Failed to save economic snapshot: {e}")
            return None

if __name__ == "__main__":
    fetcher = EconomicDataFetcher("config/data_sources_backtest.yaml")
    
    # 测试点 1: 11月14日 (CPI 发布日 11月13日 之后 -> 应该看到 11月13日的数据)
    print("\n--- Test: Nov 14, 2024 ---")
    fetcher.fetch_snapshot(datetime(2024, 11, 14))

    # 测试点 2: 11月12日 (CPI 发布日 11月13日 之前 -> 应该看到 10月10日的数据)
    print("\n--- Test: Nov 12, 2024 ---")
    fetcher.fetch_snapshot(datetime(2024, 11, 12))
    
    # 测试点 3: 2025年政府停摆期间 (11月1日 -> 应该只能看到9月的数据，看不到10月的)
    print("\n--- Test: Nov 01, 2025 (Shutdown Scenario) ---")
    fetcher.fetch_snapshot(datetime(2025, 11, 1))