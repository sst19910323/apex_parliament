# -----------------------------------------------------------------
# 文件路径: workflows/state.py
# (V9.3 - 有状态多轮对话：每个 agent 维护独立 messages 线程)
# -----------------------------------------------------------------
import operator
from typing import TypedDict, List, Dict, Any, Annotated, Optional

class RawData(TypedDict, total=False):
    """原始数据结构"""
    general_news_data: Any
    macro_data: Any
    fear_greed_data: Any
    spx_data: Any
    ndx_data: Any
    symbol: str
    profile_data: Any
    tech_data: Any
    fundamentals_data: Any
    news_data: Any

class DebateState(TypedDict):
    """
    LangGraph 核心状态对象 (V9.2).
    """
    
    # --- 1. 基础上下文 (Infrastructure) ---
    context_type: str  # 'general', 'etf', 'stock'
    raw_data: RawData
    symbol: str

    # [修复] 找回 data_files
    data_files: Dict[str, Any]
    
    # 用于生成一致文件名的 ISO 时间戳
    data_timestamp_for_report: Optional[str]
    
    # --- 2. 流程控制 (Flow Control) ---
    current_phase: str        # "init" / "debate" / "finalize" / "signoff"
    turn_count: int
    max_turns: int
    debate_status: str        # "CONTINUE" / "TERMINATE"

    # --- 3. 纯净辩论历史 (Clean Debate History) ---
    # [保持不变] List[Dict] 结构，使用 operator.add 自动追加
    debate_history: Annotated[List[Dict[str, Any]], operator.add]

    # --- 4. 各方最新发言 (Latest Arguments) ---
    # 存储上一轮各方的完整JSON输出（字符串形式）
    zealot_latest: str
    reaper_latest: str
    fulcrum_latest: str
    
    # 各方最新action（用于包络线检查等）
    zealot_last_action: int
    reaper_last_action: int
    fulcrum_last_action: int

    # --- 5. 产出物 (Outputs) ---
    final_report: Optional[Dict[str, Any]]
    
    # --- 6. 签章结果 (Sign-off Results) ---
    zealot_signoff: Optional[Dict[str, Any]]
    reaper_signoff: Optional[Dict[str, Any]]

    # --- 7. 有状态对话线程 (Stateful Conversation Threads) ---
    # 每个 agent 持有自己完整的 messages 列表，跨轮次累积，不使用 operator.add（整体替换）
    zealot_messages:  List[Dict[str, str]]
    reaper_messages:  List[Dict[str, str]]
    fulcrum_messages: List[Dict[str, str]]


def create_initial_state(
    context_type: str,
    symbol: str,
    raw_data: RawData,
    data_files: Dict[str, Any],  # [修复] 增加参数
    max_turns: int = 10
) -> DebateState:
    """创建初始状态"""
    return DebateState(
        # 基础上下文
        context_type=context_type,
        raw_data=raw_data,
        symbol=symbol,
        data_files=data_files,  # [修复] 初始化赋值
        data_timestamp_for_report=None,
        
        # 流程控制
        current_phase="init",
        turn_count=0,
        max_turns=max_turns,
        debate_status="CONTINUE",
        
        # [保持不变] 初始化为空列表
        debate_history=[],
        
        # 各方最新发言
        zealot_latest="",
        reaper_latest="",
        fulcrum_latest="",
        zealot_last_action=50,
        reaper_last_action=50,
        fulcrum_last_action=50,
        
        # 产出物
        final_report=None,
        
        # 签章结果
        zealot_signoff=None,
        reaper_signoff=None,

        # 有状态对话线程（初始为空，init 节点负责建立）
        zealot_messages=[],
        reaper_messages=[],
        fulcrum_messages=[],
    )