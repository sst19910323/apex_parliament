"""
期权数据采集器 - 测试版
测试能否从免费 API 获取期权数据
"""

import requests
import pandas as pd
from typing import Dict, List, Optional
from datetime import datetime


class OptionCollector:
    """期权数据采集器"""
    
    def __init__(self, api_key: str):
        """
        初始化期权采集器
        
        Args:
            api_key: Alpha Vantage API Key
        """
        self.api_key = api_key
        self.base_url = "https://www.alphavantage.co/query"
    
    def get_option_chain(self, symbol: str) -> Dict:
        """
        获取期权链数据
        
        Args:
            symbol: 股票代码（如 'AAPL'）
            
        Returns:
            期权链数据字典
        """
        print(f"\n{'='*60}")
        print(f"正在获取 {symbol} 的期权数据...")
        print(f"{'='*60}\n")
        
        # Alpha Vantage 期权 API
        # 文档: https://www.alphavantage.co/documentation/#options
        
        params = {
            'function': 'HISTORICAL_OPTIONS',
            'symbol': symbol,
            'apikey': self.api_key
        }
        
        try:
            print(f"请求 URL: {self.base_url}")
            print(f"参数: {params}\n")
            
            response = requests.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            # 检查是否有错误
            if 'Error Message' in data:
                print(f"❌ API 错误: {data['Error Message']}")
                return {}
            
            if 'Note' in data:
                print(f"⚠️  API 限制: {data['Note']}")
                return {}
            
            print(f"✓ 成功获取数据！")
            print(f"返回的键: {list(data.keys())}\n")
            
            return data
            
        except requests.exceptions.RequestException as e:
            print(f"❌ 请求失败: {e}")
            return {}
        except Exception as e:
            print(f"❌ 解析失败: {e}")
            return {}
    
    def parse_option_data(self, data: Dict) -> List[Dict]:
        """
        解析期权数据
        
        Args:
            data: API 返回的原始数据
            
        Returns:
            解析后的期权列表
        """
        if not data:
            return []
        
        options = []
        
        # Alpha Vantage 的期权数据格式可能因 API 版本而异
        # 需要根据实际返回调整解析逻辑
        
        print("解析期权数据...")
        print(f"数据结构: {type(data)}")
        
        # 尝试不同的数据结构
        if isinstance(data, dict):
            for key, value in data.items():
                print(f"\n键: {key}")
                print(f"值类型: {type(value)}")
                if isinstance(value, list):
                    print(f"列表长度: {len(value)}")
                    if len(value) > 0:
                        print(f"第一项: {value[0]}")
        
        return options
    
    def format_for_display(self, options: List[Dict]) -> str:
        """
        格式化期权数据用于展示
        
        Args:
            options: 期权列表
            
        Returns:
            格式化的文本
        """
        if not options:
            return "暂无期权数据"
        
        output = []
        output.append("\n" + "="*60)
        output.append("期权数据摘要")
        output.append("="*60 + "\n")
        
        for i, opt in enumerate(options[:5], 1):  # 只显示前5个
            output.append(f"期权 #{i}:")
            for key, value in opt.items():
                output.append(f"  {key}: {value}")
            output.append("")
        
        return "\n".join(output)


# ===== 备选方案：Yahoo Finance (免费，无需 API Key) =====

class YahooOptionCollector:
    """使用 Yahoo Finance 获取期权数据（免费）"""
    
    def __init__(self):
        """初始化 Yahoo Finance 采集器"""
        self.base_url = "https://query2.finance.yahoo.com/v7/finance/options"
    
    def get_option_chain(self, symbol: str) -> Dict:
        """
        从 Yahoo Finance 获取期权链
        
        Args:
            symbol: 股票代码
            
        Returns:
            期权数据
        """
        print(f"\n{'='*60}")
        print(f"正在从 Yahoo Finance 获取 {symbol} 的期权数据...")
        print(f"{'='*60}\n")
        
        try:
            url = f"{self.base_url}/{symbol}"
            print(f"请求 URL: {url}\n")
            
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if 'optionChain' not in data:
                print("❌ 未找到期权数据")
                return {}
            
            print("✓ 成功获取数据！\n")
            
            return data['optionChain']['result'][0]
            
        except requests.exceptions.RequestException as e:
            print(f"❌ 请求失败: {e}")
            return {}
        except Exception as e:
            print(f"❌ 解析失败: {e}")
            import traceback
            traceback.print_exc()
            return {}
    
    def parse_option_chain(self, data: Dict) -> Dict:
        """
        解析 Yahoo Finance 期权数据
        
        Args:
            data: 原始期权数据
            
        Returns:
            格式化的期权数据
        """
        if not data:
            return {}
        
        try:
            # 获取到期日列表
            expirations = data.get('expirationDates', [])
            print(f"可用的到期日: {len(expirations)} 个")
            
            if expirations:
                print(f"最近到期日: {datetime.fromtimestamp(expirations[0]).date()}")
            
            # 获取期权数据
            options = data.get('options', [])
            if not options:
                print("未找到期权合约")
                return {}
            
            calls = options[0].get('calls', [])
            puts = options[0].get('puts', [])
            
            print(f"\n看涨期权 (Calls): {len(calls)} 个")
            print(f"看跌期权 (Puts): {len(puts)} 个\n")
            
            # 获取标的股价
            quote = data.get('quote', {})
            stock_price = quote.get('regularMarketPrice', 0)
            
            print(f"当前股价: ${stock_price:.2f}\n")
            
            result = {
                'symbol': data.get('underlyingSymbol', ''),
                'stock_price': stock_price,
                'expirations': expirations,
                'calls': calls[:10],  # 只取前10个
                'puts': puts[:10]
            }
            
            return result
            
        except Exception as e:
            print(f"❌ 解析失败: {e}")
            import traceback
            traceback.print_exc()
            return {}
    
    def format_option_display(self, option_data: Dict) -> str:
        """
        格式化期权数据为可读文本
        
        Args:
            option_data: 解析后的期权数据
            
        Returns:
            格式化文本
        """
        if not option_data:
            return "无期权数据"
        
        output = []
        output.append("\n" + "="*70)
        output.append(f"{option_data['symbol']} 期权链分析")
        output.append("="*70 + "\n")
        
        output.append(f"标的股价: ${option_data['stock_price']:.2f}\n")
        
        # 看涨期权
        output.append("-"*70)
        output.append("看涨期权 (CALL) - 前5个平价期权")
        output.append("-"*70)
        output.append(f"{'行权价':<10} {'最新价':<10} {'买价':<10} {'卖价':<10} {'成交量':<12} {'未平仓':<12} {'隐含波动率'}")
        output.append("-"*70)
        
        for call in option_data['calls'][:5]:
            strike = call.get('strike', 0)
            last = call.get('lastPrice', 0)
            bid = call.get('bid', 0)
            ask = call.get('ask', 0)
            volume = call.get('volume', 0)
            oi = call.get('openInterest', 0)
            iv = call.get('impliedVolatility', 0) * 100  # 转为百分比
            
            output.append(
                f"${strike:<9.2f} ${last:<9.2f} ${bid:<9.2f} ${ask:<9.2f} "
                f"{volume:<12,} {oi:<12,} {iv:.1f}%"
            )
        
        output.append("")
        
        # 看跌期权
        output.append("-"*70)
        output.append("看跌期权 (PUT) - 前5个平价期权")
        output.append("-"*70)
        output.append(f"{'行权价':<10} {'最新价':<10} {'买价':<10} {'卖价':<10} {'成交量':<12} {'未平仓':<12} {'隐含波动率'}")
        output.append("-"*70)
        
        for put in option_data['puts'][:5]:
            strike = put.get('strike', 0)
            last = put.get('lastPrice', 0)
            bid = put.get('bid', 0)
            ask = put.get('ask', 0)
            volume = put.get('volume', 0)
            oi = put.get('openInterest', 0)
            iv = put.get('impliedVolatility', 0) * 100
            
            output.append(
                f"${strike:<9.2f} ${last:<9.2f} ${bid:<9.2f} ${ask:<9.2f} "
                f"{volume:<12,} {oi:<12,} {iv:.1f}%"
            )
        
        output.append("\n" + "="*70)
        
        return "\n".join(output)


# ===== 测试代码 =====

def test_alpha_vantage_options():
    """测试 Alpha Vantage 期权 API"""
    
    api_key = input("请输入 Alpha Vantage API Key (或按回车跳过): ").strip()
    
    if not api_key:
        print("⏭️  跳过 Alpha Vantage 测试\n")
        return
    
    collector = OptionCollector(api_key)
    
    # 获取 AAPL 期权数据
    data = collector.get_option_chain('AAPL')
    
    if data:
        print("\n完整返回数据:")
        print("-"*60)
        import json
        print(json.dumps(data, indent=2)[:1000])  # 只显示前1000字符
        print("...\n")
        
        # 解析数据
        options = collector.parse_option_data(data)
        print(collector.format_for_display(options))


def test_yahoo_options():
    """测试 Yahoo Finance 期权（免费，推荐）"""
    
    collector = YahooOptionCollector()
    
    # 获取 AAPL 期权链
    data = collector.get_option_chain('AAPL')
    
    if data:
        # 解析数据
        parsed = collector.parse_option_chain(data)
        
        # 显示格式化结果
        print(collector.format_option_display(parsed))
        
        # 保存详细数据用于分析
        if parsed and parsed.get('calls'):
            print("\n详细的第一个看涨期权数据:")
            print("-"*60)
            import json
            print(json.dumps(parsed['calls'][0], indent=2))


if __name__ == "__main__":
    print("期权数据采集测试")
    print("="*70)
    print("\n有两个数据源可选:")
    print("1. Yahoo Finance (免费，推荐)")
    print("2. Alpha Vantage (需要 API Key)")
    print()
    
    # 优先测试 Yahoo Finance（免费）
    print("\n【测试 Yahoo Finance】")
    test_yahoo_options()
    
    # 可选：测试 Alpha Vantage
    print("\n" + "="*70)
    print("\n【测试 Alpha Vantage (可选)】")
    test_alpha_vantage_options()