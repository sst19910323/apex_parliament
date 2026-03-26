# data/api_key_manager.py

"""
API Key 负载均衡管理器（单例模式）
- 集中管理所有 API keys
- 追踪每个 key 的请求次数和时间
- 自动选择最空闲的 key
- 避免触发 rate limit
- 智能处理历史记录（保留今天的，清理昨天的）
- (V2.0) 使用 UTC 时区（与 Alpha Vantage 一致）
"""

import time
from datetime import datetime
from typing import Optional, Dict
import json
from pathlib import Path
import pytz  # 🔥 新增


class APIKeyManager:
    """
    Alpha Vantage API Key 管理器（单例）
    限制：每个key 5次/分钟，25次/天
    重置时间：UTC 00:00（北京时间 08:00）
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    
    def __init__(self):
        # 避免重复初始化
        if self._initialized:
            return
        
        # ===== API Keys 集中管理 =====
        self.keys = [
            'your_alpha_vantage_api_key_1',
            'your_alpha_vantage_api_key_2',
            'your_alpha_vantage_api_key_3',
            'your_alpha_vantage_api_key_4',
        ]
        # ============================
        
        # 🔥 新增：使用 UTC 时区（与 Alpha Vantage 保持一致）
        self.TIMEZONE = pytz.UTC
        
        # 限制
        self.MINUTE_LIMIT = 5   # 每分钟5次
        self.DAILY_LIMIT = 25   # 每天25次
        
        self.storage_path = Path('data/storage/api_usage.json')
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 加载并智能处理使用记录
        self.usage = self._load_and_merge_usage()
        
        self._initialized = True
    
    
    def _get_today_str(self) -> str:
        """🔥 获取当前 UTC 日期字符串"""
        return datetime.now(self.TIMEZONE).date().isoformat()
    
    
    def _load_and_merge_usage(self) -> Dict:
        """
        智能加载使用记录：
        1. 如果文件不存在 → 初始化所有 keys
        2. 如果文件存在 → 合并历史记录
        3. 自动清理过期数据（昨天的记录）
        """
        today = self._get_today_str()  # 🔥 改用 UTC 时间
        usage = {}
        
        # 1. 尝试加载现有记录
        if self.storage_path.exists():
            try:
                with open(self.storage_path, 'r') as f:
                    old_usage = json.load(f)
                
                print(f"  ✓ Loaded existing usage data from {self.storage_path}")
                
                # 2. 处理每个已有的 key
                for key, data in old_usage.items():
                    if key not in self.keys:
                        print(f"  ⚠ Ignoring removed key ...{key[-4:]}")
                        continue
                    
                    # 检查日期
                    last_reset = data.get('last_reset', '')
                    
                    if last_reset == today:
                        # 今天的数据，保留但清理过期的分钟级记录
                        now = time.time()
                        data['minute'] = [
                            ts for ts in data.get('minute', [])
                            if now - ts < 60
                        ]
                        usage[key] = data
                        print(f"  ✓ Kept today's data for key ...{key[-4:]} "
                              f"(daily: {data['daily']}/{self.DAILY_LIMIT})")
                    else:
                        # 昨天或更早的数据，重置为今天
                        usage[key] = {
                            'minute': [],
                            'daily': 0,
                            'last_reset': today
                        }
                        print(f"  ✓ Reset old data for key ...{key[-4:]} (was {last_reset}, now {today} UTC)")
            
            except Exception as e:
                print(f"  ⚠ Error loading usage file: {e}")
                print(f"  → Will create new usage data")
        
        # 3. 为新增的 key 初始化
        for key in self.keys:
            if key not in usage:
                usage[key] = {
                    'minute': [],
                    'daily': 0,
                    'last_reset': today
                }
                print(f"  ✓ Initialized new key ...{key[-4:]}")
        
        # 4. 保存合并后的数据
        self._save_usage_internal(usage)
        
        return usage
    
    
    def _save_usage_internal(self, usage: Dict):
        """内部保存方法（不使用 self.usage）"""
        with open(self.storage_path, 'w') as f:
            json.dump(usage, f, indent=2)
    
    
    def _save_usage(self):
        """保存使用记录"""
        self._save_usage_internal(self.usage)
    
    
    def _reset_daily_if_needed(self, key: str):
        """检查并重置每日计数"""
        today = self._get_today_str()  # 🔥 改用 UTC 时间
        
        if self.usage[key]['last_reset'] != today:
            old_date = self.usage[key]['last_reset']
            old_count = self.usage[key]['daily']
            
            self.usage[key]['daily'] = 0
            self.usage[key]['last_reset'] = today
            self.usage[key]['minute'] = []  # 也清空分钟级记录
            
            print(f"  ✓ Auto-reset key ...{key[-4:]} "
                  f"(was {old_date} with {old_count} requests, now {today} UTC)")
            
            self._save_usage()
    
    
    def get_key(self, source_name: Optional[str] = None) -> Optional[str]:
        """
        获取最空闲的 API key
        
        Args:
            source_name: (可选) 数据源名称，保留以兼容调用方 (目前未使用)

        Returns:
            最空闲的 key，如果都达到限制则返回 None
        """
        now = time.time()
        best_key = None
        min_usage = float('inf')
        
        for key in self.keys:
            # 自动重置过期的每日计数
            self._reset_daily_if_needed(key)
            
            # 清理过期的分钟级记录（超过60秒）
            self.usage[key]['minute'] = [
                ts for ts in self.usage[key]['minute']
                if now - ts < 60
            ]
            
            minute_count = len(self.usage[key]['minute'])
            daily_count = self.usage[key]['daily']
            
            # 检查限制
            if minute_count >= self.MINUTE_LIMIT:
                continue  # 这个key这分钟用满了
            if daily_count >= self.DAILY_LIMIT:
                continue  # 这个key今天用满了
            
            # 计算负载（分钟级权重更高）
            load = minute_count * 10 + daily_count
            
            if load < min_usage:
                min_usage = load
                best_key = key
        
        if best_key:
            print(f"  → Using API key ...{best_key[-4:]} "
                  f"(minute: {len(self.usage[best_key]['minute'])}/{self.MINUTE_LIMIT}, "
                  f"daily: {self.usage[best_key]['daily']}/{self.DAILY_LIMIT})")
        else:
            print("  ⚠ All API keys exhausted!")
        
        return best_key
    
    
    def record_usage(self, key: str):
        """
        记录一次 API 请求
        
        Args:
            key: 使用的 API key
        """
        if key not in self.usage:
            print(f"Warning: Key {key} not in usage tracker!")
            return
        
        # 再次检查是否需要重置（防止跨天问题）
        self._reset_daily_if_needed(key)
        
        now = time.time()
        self.usage[key]['minute'].append(now)
        self.usage[key]['daily'] += 1
        self._save_usage()
        
        # 🔥 新增：记录完后打印状态
        print(f"  ✓ Recorded usage for key ...{key[-4:]} "
              f"(minute: {len(self.usage[key]['minute'])}/{self.MINUTE_LIMIT}, "
              f"daily: {self.usage[key]['daily']}/{self.DAILY_LIMIT})")
    
    
    def wait_if_needed(self, key: str) -> float:
        """
        如果需要等待，返回等待时间（秒）
        
        Args:
            key: 要检查的 API key
        
        Returns:
            需要等待的秒数，0表示无需等待
        """
        now = time.time()
        
        # 清理过期记录
        self.usage[key]['minute'] = [
            ts for ts in self.usage[key]['minute']
            if now - ts < 60
        ]
        
        if len(self.usage[key]['minute']) >= self.MINUTE_LIMIT:
            # 找到最老的请求
            oldest = min(self.usage[key]['minute'])
            wait_time = 60 - (now - oldest) + 1  # +1秒安全边际
            return max(0, wait_time)
        
        return 0
    
    
    def get_stats(self) -> Dict:
        """获取所有key的统计信息"""
        stats = {}
        now = time.time()
        today = self._get_today_str()  # 🔥 改用 UTC 时间
        
        for key in self.keys:
            # 自动重置
            self._reset_daily_if_needed(key)
            
            # 清理过期记录
            self.usage[key]['minute'] = [
                ts for ts in self.usage[key]['minute']
                if now - ts < 60
            ]
            
            minute_count = len(self.usage[key]['minute'])
            daily_count = self.usage[key]['daily']
            
            stats[f"...{key[-4:]}"] = {
                'minute_usage': f"{minute_count}/{self.MINUTE_LIMIT}",
                'daily_usage': f"{daily_count}/{self.DAILY_LIMIT}",
                'available': minute_count < self.MINUTE_LIMIT and daily_count < self.DAILY_LIMIT,
                'last_reset': self.usage[key]['last_reset']
            }
        
        return stats
    
    
    def reset_all(self):
        """手动重置所有 keys（调试用）"""
        today = self._get_today_str()  # 🔥 改用 UTC 时间
        
        for key in self.keys:
            self.usage[key] = {
                'minute': [],
                'daily': 0,
                'last_reset': today
            }
        
        self._save_usage()
        print(f"✓ Reset all keys to {today} UTC")


# ============================================================
# 全局单例实例
# ============================================================

key_manager = APIKeyManager()


# ============================================================
# 测试代码
# ============================================================

if __name__ == '__main__':
    import json
    
    print("=" * 60)
    print("Testing API Key Manager (UTC Timezone)")
    print("=" * 60)
    
    # 🔥 显示当前 UTC 时间
    now_utc = datetime.now(pytz.UTC)
    now_beijing = now_utc.astimezone(pytz.timezone('Asia/Shanghai'))
    print(f"\nCurrent UTC time: {now_utc.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"Current Beijing time: {now_beijing.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"Next reset at: UTC 00:00 (Beijing 08:00)")
    
    # 测试单例
    manager1 = APIKeyManager()
    manager2 = APIKeyManager()
    print(f"\n[0] Singleton Test: {manager1 is manager2}")
    
    # 查看初始状态
    print("\n[1] Initial Stats:")
    print(json.dumps(key_manager.get_stats(), indent=2))
    
    # 模拟10次连续请求
    print("\n[2] Simulating 10 requests...")
    for i in range(10):
        key = key_manager.get_key()
        if key:
            print(f"  Request {i+1}: Got key ...{key[-4:]}")
            key_manager.record_usage(key)
            time.sleep(0.5)
        else:
            print(f"  Request {i+1}: No available key!")
    
    # 查看使用后的状态
    print("\n[3] Stats after 10 requests:")
    print(json.dumps(key_manager.get_stats(), indent=2))
    
    # 查看存储文件
    print(f"\n[4] Storage file location:")
    print(f"    {key_manager.storage_path}")