"""
Fear & Greed Index Fetcher (Path-Fixed Edition)
(V9.1 - Absolute Path Enforcement)

- 修正: 强制将 YAML 中的相对路径解析为基于 PROJECT_ROOT 的绝对路径。
- 解决: 防止在不同目录下运行脚本导致生成错误路径。
- 核心: 保持 V9.0 的数据源时间戳命名逻辑不变。
"""

from __future__ import annotations

import json
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

import yaml
import cloudscraper
from bs4 import BeautifulSoup


# ------------------------------
# Constants
# ------------------------------

# 确保 PROJECT_ROOT 指向 /opt/apex_quant (假设脚本在 /opt/apex_quant/data/)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config" / "data_sources.yaml"

# 默认绝对路径 fallback
DEFAULT_CACHE_DIR = PROJECT_ROOT / "data" / "cache" / "fear_greed"

FILE_PREFIX = "fear_greed_latest_"
BROWSER_ARGS = {'browser': 'chrome', 'platform': 'windows', 'desktop': True}


@dataclass
class FearGreedConfig:
    cache_dir: Path


# ------------------------------
# Configuration
# ------------------------------

def load_config(override_path: Optional[Path] = None) -> FearGreedConfig:
    path = override_path or CONFIG_PATH
    user_cfg = {}
    
    # 1. 读取 YAML
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as fp:
                data = yaml.safe_load(fp) or {}
                user_cfg = data.get("data_sources", {}).get("fear_greed", {})
        except Exception:
            pass
    
    # 2. 获取路径字符串 (优先用 YAML，没有则用默认)
    raw_path_str = user_cfg.get("cache_dir")
    
    if raw_path_str:
        path_obj = Path(raw_path_str)
        # 关键修正：如果是相对路径 (data/...)，则拼接 PROJECT_ROOT
        if not path_obj.is_absolute():
            final_path = PROJECT_ROOT / path_obj
        else:
            final_path = path_obj
    else:
        # 没有配置则使用默认的绝对路径
        final_path = DEFAULT_CACHE_DIR

    return FearGreedConfig(cache_dir=final_path)


# ------------------------------
# Core Logic
# ------------------------------

def _fetch_data_and_extract_time() -> Tuple[Optional[Dict], Optional[datetime]]:
    """
    抓取数据并提取数据的“真实时间”。
    Returns:
        (Payload Dict, Source Datetime Object)
    """
    scraper = cloudscraper.create_scraper(browser=BROWSER_ARGS)
    
    # === 1. Fetch FGI (主时间源) ===
    fgi_result = {}
    source_dt = None
    
    try:
        resp = scraper.get("https://feargreedmeter.com/", timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            script = soup.find("script", id="__NEXT_DATA__")
            if script:
                raw = json.loads(script.string)
                data = raw['props']['pageProps']['data']['fgi']['latest']
                
                # 提取源日期 (e.g., "2025-12-11")
                date_str = data.get('date')
                if date_str:
                    try:
                        # 解析为 UTC 0点
                        dt = datetime.strptime(date_str, "%Y-%m-%d")
                        source_dt = dt.replace(tzinfo=timezone.utc)
                    except ValueError:
                        print(f"[fear_greed] ⚠️ Date format parse error: {date_str}")

                fgi_result = {
                    "value": int(data.get('now', 0)),
                    "previous_close": int(data.get('previous_close', 0)),
                    "one_week_ago": int(data.get('one_week_ago', 0)),
                    "one_month_ago": int(data.get('one_month_ago', 0)),
                    "source_date": date_str
                }
    except Exception as e:
        print(f"[fear_greed] ⚠️ FGI fetch error: {e}")

    # 礼貌性间隔
    time.sleep(1)

    # === 2. Fetch VIX (辅助数据) ===
    vix_result = {}
    try:
        headers = {"Referer": "https://feargreedmeter.com/", "Origin": "https://feargreedmeter.com"}
        resp = scraper.get("https://api2.mmeter.app/data/public/vix", headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if "quote" in data and data["quote"]:
                item = data["quote"][0]
                ts = item.get("timestamp")
                vix_time_utc = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None
                
                vix_result = {
                    "value": item.get("price"),
                    "change_percent": item.get("changesPercentage"),
                    "data_timestamp_utc": vix_time_utc
                }
    except Exception as e:
        print(f"[fear_greed] ⚠️ VIX fetch error: {e}")

    if not fgi_result and not vix_result:
        return None, None

    # Fallback to system time if source date is missing
    if source_dt is None:
        print("[fear_greed] ⚠️ Could not determine source date. Fallback to system time.")
        source_dt = datetime.now(timezone.utc)

    final_payload = {
        "filename_timestamp_basis": source_dt.isoformat(),
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "feargreedmeter.com",
        "fear_greed": fgi_result,
        "vix": vix_result if vix_result else "N/A"
    }

    return final_payload, source_dt


# ------------------------------
# Public Interface
# ------------------------------

def download_latest(config_path: Optional[Path] = None) -> Optional[Path]:
    """
    下载数据，强制使用绝对路径保存。
    """
    print(f"[fear_greed] 🚀 Executing download_latest...")
    
    cfg = load_config(config_path)
    
    # 确保目录存在
    cfg.cache_dir.mkdir(parents=True, exist_ok=True)

    payload, source_dt = _fetch_data_and_extract_time()

    if payload is None or source_dt is None:
        print("[fear_greed] ❌ Failed to fetch data.")
        return None

    try:
        # 使用源时间生成文件名
        timestamp_str = source_dt.strftime("%Y%m%dT%H%M%SZ")
        filename = f"{FILE_PREFIX}{timestamp_str}.json"
        
        # 这里的 target_path 现在是绝对路径，不再受运行目录影响
        target_path = cfg.cache_dir / filename
        
        target_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        
        print(f"[fear_greed] 💾 Saved: {target_path}")
        return target_path
    except Exception as e:
        print(f"[fear_greed] ✗ Save failed: {e}")
        traceback.print_exc()
        return None


if __name__ == "__main__":
    download_latest()