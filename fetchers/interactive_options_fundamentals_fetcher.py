"""
data/interactive_options_fundamentals_fetcher.py

期权基本面数据获取器（用于 AI 对话的第一步）

功能：
1. 使用盈透 API 获取期权链结构（所有到期日和执行价）
2. 采样部分执行价，获取成交量、持仓量、隐含波动率等指标
3. 聚合成"全景图"数据，供 AI 判断关注哪些期权

数据流程：
Step 1: reqSecDefOptParams() -> 获取所有到期日和执行价列表（秒级）
Step 2: 采样执行价（ATM 附近 + 高成交量区域）
Step 3: reqMktData() -> 批量请求采样的期权合约（2-3 分钟）
Step 4: 聚合成基本面数据并缓存

缓存策略：
- 每周更新一次（cooldown: 604800 秒 = 7 天）
- 缓存路径：data/cache/options/fundamentals/{symbol}/{symbol}_{timestamp}.json
"""

import json
import logging
import os
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from collections import defaultdict
import yaml

from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.common import TickerId

logger = logging.getLogger(__name__)


class IBOptionsFundamentalsApp(EWrapper, EClient):
    """
    盈透 API 应用（用于获取期权基本面）
    """
    
    def __init__(self):
        EClient.__init__(self, self)
        
        # 存储期权链结构
        self.option_chain_structure = {
            'expirations': [],
            'strikes': [],
            'exchange': '',
            'multiplier': '',
            'received': False
        }
        
        # 存储采样的期权数据
        self.option_data = {}  # {reqId: {'contract': ..., 'data': {...}}}
        self.pending_requests = set()
        self.completed_requests = set()
        
        # 线程同步
        self.structure_event = threading.Event()
        self.data_event = threading.Event()
    
    
    def error(self, reqId: TickerId, errorCode: int, errorString: str, advancedOrderRejectJson=""):
        """错误处理"""
        if errorCode in [2104, 2106, 2158]:  # 连接相关的信息性消息
            logger.info(f"Info {errorCode}: {errorString}")
        elif errorCode == 200:  # 合约不存在
            logger.warning(f"ReqId {reqId}: 合约不存在")
            if reqId in self.pending_requests:
                self.pending_requests.remove(reqId)
                self.completed_requests.add(reqId)
        else:
            logger.error(f"Error {errorCode} (ReqId {reqId}): {errorString}")
    
    
    def securityDefinitionOptionParameter(
        self, 
        reqId: int, 
        exchange: str,
        underlyingConId: int, 
        tradingClass: str, 
        multiplier: str,
        expirations: set, 
        strikes: set
    ):
        """
        回调：接收期权链结构数据
        
        Args:
            expirations: 所有到期日（格式：'20251121'）
            strikes: 所有执行价（格式：180.0）
        """
        logger.info(f"收到期权链结构: {len(expirations)} 个到期日, {len(strikes)} 个执行价")
        
        # 排序
        sorted_expirations = sorted(list(expirations))
        sorted_strikes = sorted(list(strikes))
        
        self.option_chain_structure = {
            'expirations': sorted_expirations,
            'strikes': sorted_strikes,
            'exchange': exchange,
            'multiplier': multiplier,
            'received': True
        }
        
        # 通知主线程
        self.structure_event.set()
    
    
    def securityDefinitionOptionParameterEnd(self, reqId: int):
        """期权链结构接收完成"""
        logger.info("期权链结构接收完成")
    
    
    def tickPrice(self, reqId: TickerId, tickType: int, price: float, attrib):
        """
        接收价格数据
        
        tickType:
        1 = Bid
        2 = Ask
        4 = Last
        """
        if reqId not in self.option_data:
            self.option_data[reqId] = {'data': {}}
        
        if tickType == 1:
            self.option_data[reqId]['data']['bid'] = price
        elif tickType == 2:
            self.option_data[reqId]['data']['ask'] = price
        elif tickType == 4:
            self.option_data[reqId]['data']['last'] = price
    
    
    def tickSize(self, reqId: TickerId, tickType: int, size: int):
        """
        接收数量数据
        
        tickType:
        5 = Last Size
        8 = Volume
        """
        if reqId not in self.option_data:
            self.option_data[reqId] = {'data': {}}
        
        if tickType == 8:
            self.option_data[reqId]['data']['volume'] = size
    
    
    def tickOptionComputation(
        self, 
        reqId: TickerId, 
        tickType: int,
        tickAttrib: int,
        impliedVol: float,
        delta: float, 
        optPrice: float, 
        pvDividend: float,
        gamma: float, 
        vega: float, 
        theta: float, 
        undPrice: float
    ):
        """
        接收期权计算数据（Greeks 和 IV）
        """
        if reqId not in self.option_data:
            self.option_data[reqId] = {'data': {}}
        
        data = self.option_data[reqId]['data']
        
        if impliedVol and impliedVol != -1:
            data['iv'] = impliedVol
        if delta and delta != -2:
            data['delta'] = delta
        if gamma and gamma != -2:
            data['gamma'] = gamma
        if vega and vega != -2:
            data['vega'] = vega
        if theta and theta != -2:
            data['theta'] = theta
    
    
    def tickGeneric(self, reqId: TickerId, tickType: int, value: float):
        """
        接收通用数据
        
        tickType:
        27 = Open Interest
        """
        if reqId not in self.option_data:
            self.option_data[reqId] = {'data': {}}
        
        if tickType == 27:
            self.option_data[reqId]['data']['open_interest'] = int(value)
    
    
    def tickString(self, reqId: TickerId, tickType: int, value: str):
        """接收字符串数据"""
        pass


class InteractiveOptionsFundamentalsFetcher:
    """
    期权基本面数据获取器
    """
    
    def __init__(self, config_path: str = "config/data_sources.yaml"):
        """
        初始化获取器
        
        Args:
            config_path: 配置文件路径
        """
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        
        self.options_config = self.config['data_sources']['options_fundamentals']
        self.cache_dir = Path(self.options_config['cache_dir'])
        self.cooldown = self.options_config['cooldowns']['latest']
        
        # 盈透连接配置（硬编码）
        self.ib_host = "127.0.0.1"
        self.ib_port = 7496  # TWS Paper Trading
        self.ib_client_id = 2  # 避免与其他脚本冲突
        
        logger.info("期权基本面数据获取器初始化完成")
    
    
    def get_fundamentals(
        self, 
        symbol: str, 
        force_refresh: bool = False,
        sample_strikes: int = 10,
        max_expirations: int = 8
    ) -> Dict[str, Any]:
        """
        获取期权基本面数据（优先使用缓存）
        
        Args:
            symbol: 股票代码
            force_refresh: 是否强制刷新
            sample_strikes: 每个到期日采样的执行价数量
            max_expirations: 最多获取多少个到期日
            
        Returns:
            {
                'data': {...},  # 期权基本面数据
                'cache_file': 'path/to/cache.json',
                'is_cached': True/False
            }
        """
        symbol = symbol.upper()
        
        # 检查缓存
        if not force_refresh:
            cached_data = self._load_from_cache(symbol)
            if cached_data:
                logger.info(f"✓ 使用缓存的 {symbol} 期权基本面数据")
                return cached_data
        
        # 缓存未命中，获取新数据
        logger.info(f"获取 {symbol} 最新期权基本面数据...")
        data = self._fetch_fundamentals(symbol, sample_strikes, max_expirations)
        
        # 保存到缓存
        cache_path = self._save_to_cache(symbol, data)
        
        return {
            'data': data,
            'cache_file': str(cache_path),
            'is_cached': False
        }
    
    
    def _load_from_cache(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        从缓存加载数据（如果未过期）
        
        Args:
            symbol: 股票代码
            
        Returns:
            缓存数据或 None
        """
        symbol_dir = self.cache_dir / symbol
        if not symbol_dir.exists():
            return None
        
        # 找到最新的缓存文件
        cache_files = list(symbol_dir.glob(f"{symbol}_*.json"))
        if not cache_files:
            return None
        
        latest_cache = max(cache_files, key=lambda p: p.stat().st_mtime)
        
        # 检查是否过期
        file_time = datetime.fromtimestamp(latest_cache.stat().st_mtime)
        if (datetime.now() - file_time).total_seconds() > self.cooldown:
            logger.info(f"缓存已过期（超过 {self.cooldown // 86400} 天）")
            return None
        
        # 读取缓存
        with open(latest_cache, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return {
            'data': data,
            'cache_file': str(latest_cache),
            'is_cached': True
        }
    
    
    def _fetch_fundamentals(
        self, 
        symbol: str,
        sample_strikes: int,
        max_expirations: int
    ) -> Dict[str, Any]:
        """
        从盈透获取期权基本面数据
        
        Args:
            symbol: 股票代码
            sample_strikes: 每个到期日采样的执行价数量
            max_expirations: 最多获取多少个到期日
            
        Returns:
            期权基本面数据字典
        """
        # 连接盈透
        app = IBOptionsFundamentalsApp()
        app.connect(self.ib_host, self.ib_port, self.ib_client_id)
        
        # 启动消息循环线程
        api_thread = threading.Thread(target=app.run, daemon=True)
        api_thread.start()
        
        time.sleep(1)  # 等待连接建立
        
        try:
            # ============ Step 1: 获取期权链结构 ============
            logger.info(f"请求 {symbol} 期权链结构...")
            
            # 构造股票合约
            stock_contract = Contract()
            stock_contract.symbol = symbol
            stock_contract.secType = "STK"
            stock_contract.currency = "USD"
            stock_contract.exchange = "SMART"
            
            # 请求期权链结构
            # 请求期权链结构（让 IB 自动查找 conId）
            app.reqSecDefOptParams(
                reqId=0,
                underlyingSymbol=symbol,
                futFopExchange="",
                underlyingSecType="STK",
                underlyingConId=0  # 0 = 让 IB 自动查找
            )
            
            # 等待数据返回
            if not app.structure_event.wait(timeout=10):
                raise TimeoutError("获取期权链结构超时")
            
            structure = app.option_chain_structure
            if not structure['received']:
                raise RuntimeError("未收到期权链结构数据")
            
            expirations = structure['expirations'][:max_expirations]
            all_strikes = structure['strikes']
            
            logger.info(f"收到 {len(expirations)} 个到期日（已限制到 {max_expirations} 个）")
            
            # ============ Step 2: 采样执行价 ============
            # 获取当前股价（用于确定 ATM 附近）
            current_price = self._get_current_price(app, symbol)
            logger.info(f"{symbol} 当前价格: ${current_price:.2f}")
            
            sampled_strikes = self._sample_strikes_around_atm(
                all_strikes, 
                current_price, 
                n=sample_strikes
            )
            
            logger.info(f"采样执行价: {sampled_strikes}")
            
            # ============ Step 3: 批量请求期权数据 ============
            logger.info(f"开始请求期权数据（{len(expirations)} 个到期日 × {len(sampled_strikes)} 个执行价 × 2）...")
            
            req_id = 1
            for expiration in expirations:
                for strike in sampled_strikes:
                    # 请求 Call
                    call_contract = self._create_option_contract(symbol, expiration, strike, "C")
                    app.reqMktData(req_id, call_contract, "233", False, False, [])  # 233 = IV + Greeks
                    app.option_data[req_id] = {
                        'contract': {
                            'symbol': symbol,
                            'expiration': expiration,
                            'strike': strike,
                            'right': 'C'
                        },
                        'data': {}
                    }
                    app.pending_requests.add(req_id)
                    req_id += 1
                    time.sleep(0.02)  # 限速：50 req/s
                    
                    # 请求 Put
                    put_contract = self._create_option_contract(symbol, expiration, strike, "P")
                    app.reqMktData(req_id, put_contract, "233", False, False, [])
                    app.option_data[req_id] = {
                        'contract': {
                            'symbol': symbol,
                            'expiration': expiration,
                            'strike': strike,
                            'right': 'P'
                        },
                        'data': {}
                    }
                    app.pending_requests.add(req_id)
                    req_id += 1
                    time.sleep(0.02)
            
            # 等待数据接收完成
            logger.info("等待数据接收完成...")
            timeout = 60
            start_time = time.time()
            while app.pending_requests and (time.time() - start_time) < timeout:
                time.sleep(0.5)
                # 检查是否有数据接收完成（简单判断：有 volume 或 iv）
                for req_id in list(app.pending_requests):
                    if req_id in app.option_data:
                        data = app.option_data[req_id]['data']
                        if 'volume' in data or 'iv' in data:
                            app.pending_requests.remove(req_id)
                            app.completed_requests.add(req_id)
            
            logger.info(f"接收完成：{len(app.completed_requests)} / {len(app.option_data)}")
            
            # ============ Step 4: 聚合成基本面数据 ============
            fundamentals = self._aggregate_fundamentals(
                symbol,
                current_price,
                expirations,
                app.option_data
            )
            
            return fundamentals
            
        finally:
            # 断开连接
            app.disconnect()
            api_thread.join(timeout=2)
    
    
    def _get_current_price(self, app: IBOptionsFundamentalsApp, symbol: str) -> float:
        """
        获取股票当前价格
        
        Args:
            app: IB 应用实例
            symbol: 股票代码
            
        Returns:
            当前价格
        """
        # 构造股票合约
        stock_contract = Contract()
        stock_contract.symbol = symbol
        stock_contract.secType = "STK"
        stock_contract.currency = "USD"
        stock_contract.exchange = "SMART"
        
        # 请求市场数据
        req_id = 9999
        app.reqMktData(req_id, stock_contract, "", False, False, [])
        
        # 等待价格数据
        time.sleep(2)
        
        # 获取价格
        if req_id in app.option_data and 'last' in app.option_data[req_id]['data']:
            price = app.option_data[req_id]['data']['last']
        else:
            # 如果没有 last，用 bid/ask 中点
            if req_id in app.option_data:
                data = app.option_data[req_id]['data']
                if 'bid' in data and 'ask' in data:
                    price = (data['bid'] + data['ask']) / 2
                else:
                    raise RuntimeError(f"无法获取 {symbol} 的价格数据")
            else:
                raise RuntimeError(f"未收到 {symbol} 的价格数据")
        
        app.cancelMktData(req_id)
        return price
    
    
    def _sample_strikes_around_atm(
        self, 
        all_strikes: List[float], 
        current_price: float,
        n: int = 10
    ) -> List[float]:
        """
        采样 ATM 附近的执行价
        
        策略：以当前价格为中心，上下各取 n/2 个执行价
        
        Args:
            all_strikes: 所有执行价
            current_price: 当前股价
            n: 采样数量
            
        Returns:
            采样的执行价列表
        """
        # 找到最接近 ATM 的执行价
        atm_idx = min(range(len(all_strikes)), key=lambda i: abs(all_strikes[i] - current_price))
        
        # 上下各取 n/2
        half = n // 2
        start_idx = max(0, atm_idx - half)
        end_idx = min(len(all_strikes), atm_idx + half + 1)
        
        return all_strikes[start_idx:end_idx]
    
    
    def _create_option_contract(
        self, 
        symbol: str, 
        expiration: str, 
        strike: float, 
        right: str
    ) -> Contract:
        """
        创建期权合约对象
        
        Args:
            symbol: 股票代码
            expiration: 到期日（格式：'20251121'）
            strike: 执行价
            right: 'C' (Call) 或 'P' (Put)
            
        Returns:
            Contract 对象
        """
        contract = Contract()
        contract.symbol = symbol
        contract.secType = "OPT"
        contract.exchange = "SMART"
        contract.currency = "USD"
        contract.lastTradeDateOrContractMonth = expiration
        contract.strike = strike
        contract.right = right
        contract.multiplier = "100"
        
        return contract
    
    
    def _aggregate_fundamentals(
        self,
        symbol: str,
        current_price: float,
        expirations: List[str],
        option_data: Dict[int, Dict]
    ) -> Dict[str, Any]:
        """
        聚合成基本面数据
        
        Args:
            symbol: 股票代码
            current_price: 当前股价
            expirations: 到期日列表
            option_data: 期权数据字典
            
        Returns:
            基本面数据字典
        """
        now = datetime.now()
        
        # 按到期日分组
        grouped = defaultdict(lambda: {'calls': [], 'puts': []})
        
        for req_id, item in option_data.items():
            if req_id == 9999:  # 跳过股票价格请求
                continue
            
            contract = item['contract']
            data = item['data']
            
            exp = contract['expiration']
            right = contract['right']
            
            if right == 'C':
                grouped[exp]['calls'].append(data)
            else:
                grouped[exp]['puts'].append(data)
        
        # 构建到期日数据
        expiration_list = []
        
        for exp in expirations:
            if exp not in grouped:
                continue
            
            calls = grouped[exp]['calls']
            puts = grouped[exp]['puts']
            
            # 计算到期天数
            exp_date = datetime.strptime(exp, '%Y%m%d')
            days_to_expiry = (exp_date - now).days
            
            # 判断类型
            exp_type = self._classify_expiration(exp_date)
            
            # 聚合统计
            total_call_volume = sum(d.get('volume', 0) for d in calls)
            total_put_volume = sum(d.get('volume', 0) for d in puts)
            total_call_oi = sum(d.get('open_interest', 0) for d in calls)
            total_put_oi = sum(d.get('open_interest', 0) for d in puts)
            
            # 平均 IV
            call_ivs = [d['iv'] for d in calls if 'iv' in d and d['iv'] > 0]
            put_ivs = [d['iv'] for d in puts if 'iv' in d and d['iv'] > 0]
            avg_call_iv = sum(call_ivs) / len(call_ivs) if call_ivs else None
            avg_put_iv = sum(put_ivs) / len(put_ivs) if put_ivs else None
            avg_iv = ((avg_call_iv or 0) + (avg_put_iv or 0)) / 2 if (avg_call_iv or avg_put_iv) else None
            
            # Put/Call Ratio
            put_call_ratio_vol = total_put_volume / total_call_volume if total_call_volume > 0 else None
            put_call_ratio_oi = total_put_oi / total_call_oi if total_call_oi > 0 else None
            
            expiration_list.append({
                'date': exp,
                'formatted_date': exp_date.strftime('%Y-%m-%d'),
                'days_to_expiry': days_to_expiry,
                'weeks_to_expiry': round(days_to_expiry / 7, 1),
                'type': exp_type,
                'is_monthly': self._is_monthly_expiration(exp_date),
                'statistics': {
                    'total_call_volume': total_call_volume,
                    'total_put_volume': total_put_volume,
                    'total_volume': total_call_volume + total_put_volume,
                    'total_call_oi': total_call_oi,
                    'total_put_oi': total_put_oi,
                    'total_oi': total_call_oi + total_put_oi,
                    'put_call_ratio_volume': round(put_call_ratio_vol, 2) if put_call_ratio_vol else None,
                    'put_call_ratio_oi': round(put_call_ratio_oi, 2) if put_call_ratio_oi else None,
                    'avg_iv': round(avg_iv, 4) if avg_iv else None,
                    'avg_call_iv': round(avg_call_iv, 4) if avg_call_iv else None,
                    'avg_put_iv': round(avg_put_iv, 4) if avg_put_iv else None
                }
            })
        
        # 构建摘要
        summary = self._build_summary(symbol, current_price, expiration_list)
        
        return {
            'symbol': symbol,
            'underlying_price': round(current_price, 2),
            'fetch_time': now.isoformat(),
            'expirations': expiration_list,
            'summary': summary
        }
    
    
    def _classify_expiration(self, exp_date: datetime) -> str:
        """
        分类到期日类型
        
        Args:
            exp_date: 到期日
            
        Returns:
            'weekly' / 'monthly' / 'quarterly'
        """
        # 月期权：每月第三个星期五
        if self._is_monthly_expiration(exp_date):
            # 进一步判断是否是季度期权
            if exp_date.month in [3, 6, 9, 12]:
                return 'quarterly'
            else:
                return 'monthly'
        else:
            return 'weekly'
    
    
    def _is_monthly_expiration(self, exp_date: datetime) -> bool:
        """
        判断是否是月期权到期日（每月第三个星期五）
        
        Args:
            exp_date: 到期日
            
        Returns:
            True/False
        """
        # 检查是否是星期五
        if exp_date.weekday() != 4:
            return False
        
        # 检查是否是第三周
        day = exp_date.day
        return 15 <= day <= 21
    
    
    def _build_summary(
        self,
        symbol: str,
        current_price: float,
        expiration_list: List[Dict]
    ) -> Dict[str, Any]:
        """
        构建摘要信息
        
        Args:
            symbol: 股票代码
            current_price: 当前股价
            expiration_list: 到期日列表
            
        Returns:
            摘要字典
        """
        if not expiration_list:
            return {}
        
        # 最近/最远到期日
        nearest = min(expiration_list, key=lambda x: x['days_to_expiry'])
        farthest = max(expiration_list, key=lambda x: x['days_to_expiry'])
        
        # 下一个月期权
        monthly_exps = [e for e in expiration_list if e['is_monthly']]
        next_monthly = monthly_exps[0] if monthly_exps else None
        
        # 平均 Put/Call Ratio
        pc_ratios = [e['statistics']['put_call_ratio_volume'] for e in expiration_list 
                     if e['statistics']['put_call_ratio_volume']]
        avg_pc_ratio = sum(pc_ratios) / len(pc_ratios) if pc_ratios else None
        
        # 高 IV 到期日
        high_iv_exps = sorted(
            [e for e in expiration_list if e['statistics']['avg_iv']],
            key=lambda x: x['statistics']['avg_iv'],
            reverse=True
        )[:3]
        
        # 按时间范围分组推荐
        short_term = [e for e in expiration_list if e['days_to_expiry'] <= 14]
        medium_term = [e for e in expiration_list if 14 < e['days_to_expiry'] <= 60]
        long_term = [e for e in expiration_list if e['days_to_expiry'] > 60]
        
        return {
            'total_expirations': len(expiration_list),
            'nearest_expiry': {
                'date': nearest['formatted_date'],
                'days': nearest['days_to_expiry']
            },
            'farthest_expiry': {
                'date': farthest['formatted_date'],
                'days': farthest['days_to_expiry']
            },
            'next_monthly_expiry': {
                'date': next_monthly['formatted_date'],
                'days': next_monthly['days_to_expiry']
            } if next_monthly else None,
            'avg_put_call_ratio': round(avg_pc_ratio, 2) if avg_pc_ratio else None,
            'high_iv_expirations': [
                {
                    'date': e['formatted_date'],
                    'iv': e['statistics']['avg_iv']
                }
                for e in high_iv_exps
            ],
            'recommended_horizons': {
                'short_term': [e['formatted_date'] for e in short_term[:2]],
                'medium_term': [e['formatted_date'] for e in medium_term[:2]],
                'long_term': [e['formatted_date'] for e in long_term[:2]]
            }
        }
    
    
    def _save_to_cache(self, symbol: str, data: Dict[str, Any]) -> Path:
        """
        保存数据到缓存
        
        Args:
            symbol: 股票代码
            data: 数据字典
            
        Returns:
            缓存文件路径
        """
        # 创建股票文件夹
        symbol_dir = self.cache_dir / symbol
        symbol_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成文件名
        timestamp = int(datetime.now().timestamp())
        filename = f"{symbol}_{timestamp}.json"
        filepath = symbol_dir / filename
        
        # 保存 JSON
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"✓ 期权基本面数据已缓存: {filepath}")
        
        return filepath


# ============================================
# 测试代码
# ============================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    fetcher = InteractiveOptionsFundamentalsFetcher()
    
    result = fetcher.get_fundamentals(
        symbol="AAPL",
        force_refresh=True,
        sample_strikes=10,
        max_expirations=5
    )
    
    print("\n" + "="*60)
    print("期权基本面数据获取完成！")
    print("="*60)
    print(json.dumps(result['data'], indent=2, ensure_ascii=False))