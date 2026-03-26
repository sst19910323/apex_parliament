#!/usr/bin/env python3
"""
从 Interactive Brokers 获取 ETF Profile 数据

职责：
- 获取 ETF 基础识别信息
- 获取实时/准实时行情数据
- 不包含量化指标（由 ETF Economics 模块负责）

使用示例：
    python data/scripts/interactive_brokers_etf_profile.py QQQ
    python data/scripts/interactive_brokers_etf_profile.py SPY --force
    python data/scripts/interactive_brokers_etf_profile.py --test  # 运行测试
"""

import os
import sys
import json
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ib_insync import IB, Stock, util
import yaml

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class IBETFProfileFetcher:
    """Interactive Brokers ETF Profile 数据获取器"""
    
    def __init__(self, config_path: str = "config/data_sources.yaml"):
        """
        初始化
        
        Args:
            config_path: 配置文件路径
        """
        config_full_path = PROJECT_ROOT / config_path
        
        if not config_full_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_full_path}")
        
        with open(config_full_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        etf_config = config['data_sources']['etf_profile']
        self.cache_dir = PROJECT_ROOT / etf_config['cache_dir']
        self.cooldown = etf_config['cooldown']
        self.fields = etf_config['fields']
        
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.ib = IB()
        self._connected = False
    
    def connect(self, host: str = '127.0.0.1', port: int = 7496, client_id: int = 2) -> bool:
        """
        连接到 IBKR TWS/Gateway
        
        Args:
            host: TWS/Gateway 地址
            port: 端口 (7497=TWS Paper, 4001=Gateway Paper, 7496=TWS Live, 4001=Gateway Live)
            client_id: 客户端 ID
        
        Returns:
            是否连接成功
        """
        if self._connected:
            logger.info("已存在活跃连接")
            return True
        
        try:
            self.ib.connect(host, port, clientId=client_id, timeout=20)
            self._connected = True
            logger.info(f"✓ 已连接到 IBKR: {host}:{port} (ClientID: {client_id})")
            return True
        except Exception as e:
            logger.error(f"✗ 连接 IBKR 失败: {e}")
            return False
    
    def disconnect(self):
        """断开连接"""
        if self._connected and self.ib.isConnected():
            self.ib.disconnect()
            self._connected = False
            logger.info("✓ 已断开 IBKR 连接")
    
    def _get_cache_path(self, symbol: str) -> Path:
        """获取缓存目录路径"""
        symbol_dir = self.cache_dir / symbol.upper()
        symbol_dir.mkdir(parents=True, exist_ok=True)
        return symbol_dir
    
    def _find_latest_cache(self, symbol: str) -> Optional[Path]:
        """查找最新的缓存文件"""
        cache_dir = self._get_cache_path(symbol)
        files = sorted(cache_dir.glob(f"{symbol.upper()}_profile_*.json"))
        return files[-1] if files else None
    
    def _is_cache_valid(self, cache_file: Path) -> bool:
        """检查缓存是否在有效期内"""
        if not cache_file.exists():
            return False
        age = time.time() - cache_file.stat().st_mtime
        return age < self.cooldown
    
    def _safe_float(self, value) -> Optional[float]:
        """安全转换为 float，NaN 返回 None"""
        if value is None or (isinstance(value, float) and value != value):  # NaN 检查
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    
    def _safe_int(self, value) -> Optional[int]:
        """安全转换为 int，NaN 返回 None"""
        if value is None or (isinstance(value, float) and value != value):  # NaN 检查
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
    
    def fetch_etf_profile(self, symbol: str, force: bool = False) -> Optional[Dict]:
        """
        获取 ETF Profile 数据
        
        职责：
        - 基础识别信息（名称、交易所等）
        - 实时/准实时行情数据
        
        不包含：
        - 量化指标（由 ETF Economics 计算）
        - 历史收益率、风险指标等
        
        Args:
            symbol: ETF 代码 (如 'QQQ', 'SPY')
            force: 是否强制刷新缓存
        
        Returns:
            ETF profile 数据字典，失败返回 None
        """
        symbol = symbol.upper()
        
        # 检查缓存
        if not force:
            latest_cache = self._find_latest_cache(symbol)
            if latest_cache and self._is_cache_valid(latest_cache):
                logger.info(f"✓ 使用缓存: {latest_cache.name}")
                with open(latest_cache, 'r', encoding='utf-8') as f:
                    return json.load(f)
        
        # 确保已连接
        if not self._connected:
            logger.error("未连接到 IBKR，请先调用 connect()")
            return None
        
        try:
            # 创建合约
            contract = Stock(symbol, 'SMART', 'USD')
            
            # 验证合约
            contracts = self.ib.qualifyContracts(contract)
            if not contracts:
                logger.error(f"✗ 无法找到标的: {symbol}")
                return None
            
            qualified_contract = contracts[0]
            logger.info(f"✓ 合约验证成功: {qualified_contract.symbol} @ {qualified_contract.primaryExchange}")
            
            # 获取合约详情（基础信息）
            details_list = self.ib.reqContractDetails(qualified_contract)
            if not details_list:
                logger.error(f"✗ 无法获取合约详情: {symbol}")
                return None
            
            details = details_list[0]
            
            # 获取实时行情数据（使用 reqMktData）
            ticker = self.ib.reqMktData(qualified_contract, '', False, False)
            self.ib.sleep(3)  # 等待数据填充
            
            # 构建 profile（基础信息 + 实时行情）
            profile = {
                # === 基础识别信息 ===
                "symbol": symbol,
                "name": details.longName or details.contract.localSymbol,
                "exchange": details.contract.primaryExchange,
                "currency": details.contract.currency,
                "category": getattr(details, 'category', ''),
                "industry": getattr(details, 'industry', ''),
                
                # === 实时行情数据 ===
                "current_price": self._safe_float(ticker.marketPrice()),
                "previous_close": self._safe_float(ticker.close),
                "current_volume": self._safe_int(ticker.volume),
                
                # 盘口数据（如果有实时订阅）
                "bid": self._safe_float(ticker.bid),
                "ask": self._safe_float(ticker.ask),
                "bid_size": self._safe_int(ticker.bidSize),
                "ask_size": self._safe_int(ticker.askSize),
                
                # 当日高低
                "day_high": self._safe_float(ticker.high),
                "day_low": self._safe_float(ticker.low),
                
                # === 元数据 ===
                "data_source": "Interactive Brokers",
                "fetched_at": datetime.now().isoformat(),
                "has_fundamentals": False  # ETF 通常没有基本面数据
            }
            
            # 取消实时数据订阅（节省资源）
            self.ib.cancelMktData(qualified_contract)
            
            # 如果实时数据为空，使用历史数据补全（作为备用方案）
            if profile["current_price"] is None:
                logger.info("实时数据为空，尝试使用历史数据...")
                try:
                    bars = self.ib.reqHistoricalData(
                        qualified_contract,
                        endDateTime='',
                        durationStr='2 D',
                        barSizeSetting='1 day',
                        whatToShow='TRADES',
                        useRTH=True,
                        formatDate=1
                    )
                    
                    if bars and len(bars) >= 1:
                        latest_bar = bars[-1]
                        profile["current_price"] = float(latest_bar.close)
                        profile["current_volume"] = int(latest_bar.volume)
                        profile["day_high"] = float(latest_bar.high)
                        profile["day_low"] = float(latest_bar.low)
                        
                        if len(bars) >= 2:
                            profile["previous_close"] = float(bars[-2].close)
                        
                        logger.info(f"✓ 使用历史数据补全: ${latest_bar.close:.2f}")
                    
                except Exception as e:
                    logger.warning(f"⚠ 历史数据补全失败: {e}")
            
            # 保存到文件
            timestamp = int(time.time())
            cache_dir = self._get_cache_path(symbol)
            cache_file = cache_dir / f"{symbol}_profile_{timestamp}.json"
            
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(profile, f, indent=2, ensure_ascii=False)
            
            logger.info(f"✓ ETF Profile 已保存: {cache_file}")
            
            return profile
            
        except Exception as e:
            logger.error(f"✗ 获取 {symbol} profile 失败: {e}", exc_info=True)
            return None
    
    def get_contract_details_raw(self, symbol: str) -> Optional[Dict]:
        """
        获取原始的 ContractDetails（用于调试，查看所有可用字段）
        
        Args:
            symbol: ETF 代码
            
        Returns:
            所有可用字段的字典
        """
        if not self._connected:
            logger.error("未连接到 IBKR")
            return None
        
        try:
            contract = Stock(symbol.upper(), 'SMART', 'USD')
            qualified = self.ib.qualifyContracts(contract)
            
            if not qualified:
                logger.error(f"无法验证合约: {symbol}")
                return None
            
            contract = qualified[0]
            details_list = self.ib.reqContractDetails(contract)
            
            if not details_list:
                logger.error(f"无法获取合约详情: {symbol}")
                return None
            
            details = details_list[0]
            
            # 提取所有非私有字段
            result = {
                "ContractDetails": {},
                "Contract": {}
            }
            
            # ContractDetails 字段
            for attr in dir(details):
                if not attr.startswith('_') and not callable(getattr(details, attr)):
                    value = getattr(details, attr)
                    if value is not None and value != '':
                        result["ContractDetails"][attr] = str(value)
            
            # Contract 字段
            for attr in dir(details.contract):
                if not attr.startswith('_') and not callable(getattr(details.contract, attr)):
                    value = getattr(details.contract, attr)
                    if value is not None and value != '':
                        result["Contract"][attr] = str(value)
            
            return result
            
        except Exception as e:
            logger.error(f"获取原始详情失败: {e}")
            return None
    
    def __enter__(self):
        """上下文管理器入口"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self.disconnect()


# ============================================
# 测试用例
# ============================================

def run_tests():
    """运行测试用例"""
    logger.info("=" * 60)
    logger.info("开始测试 IBETFProfileFetcher")
    logger.info("=" * 60)
    
    # 测试 1: 连接测试
    logger.info("\n【测试 1】连接到 IBKR")
    fetcher = IBETFProfileFetcher()
    
    if not fetcher.connect():
        logger.error("✗ 连接失败，终止测试")
        logger.info("\n请确保:")
        logger.info("  1. TWS/Gateway 已启动")
        logger.info("  2. 已启用 API 连接 (Configure > API > Settings)")
        logger.info("  3. 端口号正确 (7496=TWS Paper, 4001=Gateway Paper)")
        return
    
    # 测试 2: 获取知名 ETF 数据
    test_symbols = ['QQQ', 'SPY']
    
    for symbol in test_symbols:
        logger.info(f"\n【测试 2.{test_symbols.index(symbol) + 1}】获取 {symbol} Profile")
        
        # 第一次获取 (会请求 API)
        profile = fetcher.fetch_etf_profile(symbol, force=True)
        
        if profile:
            logger.info(f"✓ 成功获取 {symbol} 数据:")
            logger.info(f"  - 名称: {profile.get('name')}")
            logger.info(f"  - 交易所: {profile.get('exchange')}")
            logger.info(f"  - 当前价格: ${profile.get('current_price')}")
            logger.info(f"  - 前收盘价: ${profile.get('previous_close')}")
            logger.info(f"  - 当前成交量: {profile.get('current_volume'):,}" if profile.get('current_volume') else "  - 当前成交量: N/A")
            logger.info(f"  - Bid/Ask: ${profile.get('bid')} / ${profile.get('ask')}")
            logger.info(f"  - 日内高低: ${profile.get('day_high')} / ${profile.get('day_low')}")
        else:
            logger.error(f"✗ 获取 {symbol} 失败")
        
        time.sleep(1)  # 避免请求过快
    
    # 测试 3: 缓存测试
    logger.info(f"\n【测试 3】缓存机制测试 (使用 QQQ)")
    
    # 使用缓存 (不强制刷新)
    profile_cached = fetcher.fetch_etf_profile('QQQ', force=False)
    
    if profile_cached:
        logger.info("✓ 成功使用缓存")
    else:
        logger.warning("⚠ 缓存未命中或失效")
    
    # 测试 4: 无效标的测试
    logger.info(f"\n【测试 4】无效标的测试")
    invalid_profile = fetcher.fetch_etf_profile('INVALID_SYMBOL_XYZ')
    
    if invalid_profile is None:
        logger.info("✓ 正确处理无效标的")
    else:
        logger.error("✗ 应返回 None 但返回了数据")
    
    # 测试 5: 查看原始字段（调试用）
    logger.info(f"\n【测试 5】查看 QQQ 原始 ContractDetails 字段")
    raw_data = fetcher.get_contract_details_raw('QQQ')
    if raw_data:
        logger.info("✓ 原始字段:")
        print(json.dumps(raw_data, indent=2, ensure_ascii=False))
    
    # 断开连接
    fetcher.disconnect()
    
    logger.info("\n" + "=" * 60)
    logger.info("测试完成")
    logger.info("=" * 60)


# ============================================
# 主函数
# ============================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='从 Interactive Brokers 获取 ETF Profile 数据',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python interactive_brokers_etf_profile.py QQQ
  python interactive_brokers_etf_profile.py SPY --force
  python interactive_brokers_etf_profile.py --test
  python interactive_brokers_etf_profile.py QQQ --raw  # 查看原始字段
        """
    )
    
    parser.add_argument(
        'symbol',
        nargs='?',
        help='ETF 代码 (如 QQQ, SPY)'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='强制刷新缓存'
    )
    parser.add_argument(
        '--host',
        default='127.0.0.1',
        help='IBKR 主机地址 (默认: 127.0.0.1)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=7496,
        help='IBKR 端口 (默认: 7496 = TWS Paper Trading)'
    )
    parser.add_argument(
        '--test',
        action='store_true',
        help='运行测试用例'
    )
    parser.add_argument(
        '--raw',
        action='store_true',
        help='查看原始 ContractDetails 字段（调试用）'
    )
    
    args = parser.parse_args()
    
    # 运行测试
    if args.test:
        run_tests()
        return
    
    # 正常使用
    if not args.symbol:
        parser.error("请提供 ETF 代码或使用 --test 运行测试")
    
    with IBETFProfileFetcher() as fetcher:
        if not fetcher.connect(args.host, args.port):
            sys.exit(1)
        
        # 查看原始字段
        if args.raw:
            raw_data = fetcher.get_contract_details_raw(args.symbol.upper())
            if raw_data:
                print(json.dumps(raw_data, indent=2, ensure_ascii=False))
                sys.exit(0)
            else:
                logger.error(f"获取 {args.symbol} 原始字段失败")
                sys.exit(1)
        
        # 获取 Profile
        profile = fetcher.fetch_etf_profile(args.symbol.upper(), force=args.force)
        
        if profile:
            print(json.dumps(profile, indent=2, ensure_ascii=False))
            sys.exit(0)
        else:
            logger.error(f"获取 {args.symbol} 失败")
            sys.exit(1)


if __name__ == '__main__':
    main()