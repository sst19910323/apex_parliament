# -----------------------------------------------------------------
# 文件路径: run_debate.py
# (V10.0 - 四方架构：Z/R/F三辩论者 + Chronicler史官)
# -----------------------------------------------------------------
import logging
import sys
import json
import re
from pathlib import Path
from typing import Dict, Any, Optional, Literal, Union

# --- 1. 环境设置 ---
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# --- 2. 导入组件 ---
try:
    from langgraph.graph import StateGraph, START, END
    
    from workflows.state import DebateState, create_initial_state
    from workflows.nodes import ParliamentNodes
    from workflows.prompt_manager import PromptManager
    from workflows.llm_client import LLMClient

except ImportError as e:
    print("="*60)
    print(f"CRITICAL IMPORT ERROR: {e}")
    print(f"Detected Root: {PROJECT_ROOT}")
    print("请检查 workflows 目录下是否存在 __init__.py")
    sys.exit(1)

# 配置日志
logger = logging.getLogger("DebateEngine")
if not logging.getLogger().hasHandlers():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%H:%M:%S'
    )


class DebateEngine:
    def __init__(self, config_rel_path: str = "config/models.yaml"):
        logger.info("🔧 Initializing DebateEngine (V10.0 - Z/R/F + Chronicler)...")
        
        # 1. 绝对路径解析
        self.models_config_path = str(PROJECT_ROOT / config_rel_path)
        self.data_config_path = str(PROJECT_ROOT / "config/data_sources.yaml")
        self.prompts_dir = str(PROJECT_ROOT / "prompts")
        
        # 2. 初始化组件
        self.pm = PromptManager(base_dir=self.prompts_dir)
        self.llm_client = LLMClient(config_path=self.models_config_path)
        
        # 3. 初始化节点，传入 llm_client 以获取模型名称
        self.nodes = ParliamentNodes(
            prompt_manager=self.pm, 
            llm_caller=self.llm_client.query_chat,
            config_path=self.data_config_path,
            llm_client=self.llm_client  # 传入 llm_client
        )
        
        # 4. 构建图
        self.app = self._build_graph()

    def _build_graph(self):
        """
        构建辩论流程图 (V10.0)

        流程：
        1. Init：Z/R/F 顺序独立立场 → Chronicler moderation
        2. Debate Loop：Z/R/F 顺序辩论 → Chronicler moderation → 路由CONTINUE/TERMINATE
        3. Finalize：Chronicler 写最终报告
        4. Signoff：Z/R/F 三方并行签章
        5. Save
        """
        workflow = StateGraph(DebateState)

        # ==========================================
        # 1. 注册节点
        # ==========================================

        # Init 三辩论者
        workflow.add_node("zealot_init",  self.nodes.zealot_init_node)
        workflow.add_node("reaper_init",  self.nodes.reaper_init_node)
        workflow.add_node("fulcrum_init", self.nodes.fulcrum_init_node)

        # Debate 三辩论者
        workflow.add_node("zealot_debate",  self.nodes.zealot_debate_node)
        workflow.add_node("reaper_debate",  self.nodes.reaper_debate_node)
        workflow.add_node("fulcrum_debate", self.nodes.fulcrum_debate_node)

        # Chronicler
        workflow.add_node("chronicler_moderation", self.nodes.chronicler_moderation_node)
        workflow.add_node("chronicler_finalize",   self.nodes.chronicler_finalize_node)

        # Signoff 三方
        workflow.add_node("zealot_signoff",  self.nodes.zealot_signoff_node)
        workflow.add_node("reaper_signoff",  self.nodes.reaper_signoff_node)
        workflow.add_node("fulcrum_signoff", self.nodes.fulcrum_signoff_node)

        # Save
        workflow.add_node("data_saver", self.nodes.data_saver_node)

        # ==========================================
        # 2. 连线
        # ==========================================

        # Init → Chronicler moderation
        workflow.add_edge(START, "zealot_init")
        workflow.add_edge("zealot_init",  "reaper_init")
        workflow.add_edge("reaper_init",  "fulcrum_init")
        workflow.add_edge("fulcrum_init", "chronicler_moderation")

        # Chronicler moderation → 路由
        workflow.add_conditional_edges(
            "chronicler_moderation",
            self._route_after_moderation,
            {
                "debate":   "zealot_debate",
                "finalize": "chronicler_finalize"
            }
        )

        # Debate 三方 → Chronicler moderation
        workflow.add_edge("zealot_debate",  "reaper_debate")
        workflow.add_edge("reaper_debate",  "fulcrum_debate")
        workflow.add_edge("fulcrum_debate", "chronicler_moderation")

        # Chronicler finalize → 三方并行签章
        workflow.add_edge("chronicler_finalize", "zealot_signoff")
        workflow.add_edge("chronicler_finalize", "reaper_signoff")
        workflow.add_edge("chronicler_finalize", "fulcrum_signoff")

        # 签章汇聚 → Save
        workflow.add_edge("zealot_signoff",  "data_saver")
        workflow.add_edge("reaper_signoff",  "data_saver")
        workflow.add_edge("fulcrum_signoff", "data_saver")

        workflow.add_edge("data_saver", END)

        return workflow.compile()

    # ==========================================
    # 3. 路由逻辑 (Routing Logic)
    # ==========================================

    def _route_after_moderation(self, state: DebateState) -> Literal["debate", "finalize"]:
        """
        Chronicler 裁定后的路由：
        - TERMINATE 或 达到最大轮次 -> finalize
        - CONTINUE -> debate
        """
        decision = state.get("debate_status", "CONTINUE").upper()
        turn = state.get("turn_count", 1)
        max_turns = state.get("max_turns", 25)

        if decision == "TERMINATE":
            logger.info(f"🛑 Chronicler decided to TERMINATE at round {turn}")
            return "finalize"

        if turn >= max_turns:
            logger.info(f"⏰ Max turns ({max_turns}) reached, forcing finalize")
            return "finalize"

        logger.info(f"🔄 Continuing debate, entering round {turn}")
        return "debate"

    def _extract_data_timestamp(self, raw_data: Dict, paths: Dict) -> Optional[str]:
        """
        提取数据时间戳
        [修复] 增加对 paths 的非空检查，防止 ETF/General 场景缺少 key 报错
        """
        try:
            file_path_str = ""
            # 安全检查 paths 是否存在
            if paths:
                if 'symbol' in paths and 'technical' in paths['symbol']:
                    file_path_str = paths['symbol']['technical']
                elif 'indices' in paths and 'SPX' in paths['indices']: 
                    file_path_str = paths['indices']['SPX']
            
            if file_path_str:
                match = re.search(r"(\d{8}T\d{6}Z)", str(file_path_str))
                if match:
                    return match.group(1)
        except Exception as e:
            logger.error(f"Filename extraction failed: {e}")

        # 备用方案：从 JSON 内容里找
        tech_data_str = raw_data.get('tech_data') or raw_data.get('spx_data')
        if tech_data_str:
            try:
                # 假设是 json string
                if isinstance(tech_data_str, str):
                    tech_json = json.loads(tech_data_str)
                    ts = tech_json.get('market_data_timestamp_utc')
                    if ts:
                        return ts
            except:
                pass
        return None

    def run(self, symbol: str, context_type: str, raw_data: dict, paths: dict = None, max_turns: int = 25):
        """
        运行辩论引擎
        
        Args:
            symbol: 标的代码（股票/ETF）或 "MARKET" (宏观)
            context_type: "stock" / "etf" / "general"
            raw_data: 原始数据字典
            paths: 数据文件路径（可选）
            max_turns: 最大辩论轮次
        
        Returns:
            最终状态字典，包含 final_report
        """
        logger.info(f"🚀 Engine Start: {symbol} (Context: {context_type})")
        
        paths = paths or {}
        data_ts = self._extract_data_timestamp(raw_data, paths)

        # [修复点] 创建初始状态时，正确传入 data_files=paths
        initial_state = create_initial_state(
            context_type=context_type,
            symbol=symbol,
            raw_data=raw_data,
            data_files=paths,    # <--- 新增传参
            max_turns=max_turns
        )
        
        # 补充时间戳
        initial_state['data_timestamp_for_report'] = data_ts
        # initial_state['data_file_paths'] 不需要手动赋了，因为 create_initial_state 已经处理了 data_files

        try:
            final_state = self.app.invoke(initial_state, config={"recursion_limit": 100})
            logger.info(f"🏁 Engine Finish: {symbol}")
            return final_state
        except Exception as e:
            logger.error(f"❌ Engine Execution Error: {e}", exc_info=True)
            return None


if __name__ == "__main__":
    print(f"Testing DebateEngine from: {PROJECT_ROOT}")
    try:
        eng = DebateEngine()
        print("✅ DebateEngine initialized successfully (V9.2).")
        
        # 简单测试
        test_raw_data = {
            "general_news_data": "测试新闻数据",
            "macro_data": "测试宏观数据",
            "fear_greed_data": "测试情绪数据",
            "spx_data": "测试SPX数据",
            "ndx_data": "测试NDX数据"
        }
        
        print("\n📋 Graph structure:")
        print(f"   Nodes: {list(eng.app.nodes.keys()) if hasattr(eng.app, 'nodes') else 'N/A'}")
        
    except Exception as e:
        print(f"❌ Init failed: {e}")
        import traceback
        traceback.print_exc()