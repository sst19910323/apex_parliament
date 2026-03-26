# -----------------------------------------------------------------
# 文件路径: utils/llm_client.py
# (V3.3 - Custom Temperature & Correct Model Mapping)
# 职责: 统一封装 LLM 调用。
# 修正:
# 1. role_mapping 适配实际的 models.yaml 键名 (qwen3-max, qwen-plus)。
# 2. 温度逻辑: 参数传入 > 角色预设 > 配置文件。
# -----------------------------------------------------------------
import requests
import yaml
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class LLMClient:
    def __init__(self, config_path: str = "config/models.yaml"):
        self.config_path = Path(config_path)
        if not self.config_path.exists():
            self.config_path = Path(__file__).resolve().parents[1] / "config/models.yaml"
            
        self.full_config = self._load_full_config()
        self.models_cfg = self.full_config.get("models", {})
        self.default_model_key = self.full_config.get("default_model", "qwen3-max")
        
        # 2. 定义角色到模型 Key 的映射 (根据您的 models.yaml)
        self.role_mapping = {
            "zealot": "deepseek",
            "reaper": "deepseek",
            "fulcrum": "qwen3-max",
            "general": self.default_model_key
        }

    def _load_full_config(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            logger.error(f"❌ 找不到配置文件: {self.config_path}")
            return {}
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"❌ 读取 models.yaml 失败: {e}")
            return {}

    def query_chat(self, messages: List[Dict], role: str = "general", temperature: Optional[float] = None) -> str:
        """
        [关键适配] 适配 nodes.py 的统一调用接口。
        :param temperature: 如果传入非 None 值，将覆盖角色默认设置。
        """
        # 1. 确定模型
        model_key = self.role_mapping.get(role, self.default_model_key)
        
        # 2. 确定温度 (Priority: Args > Role Default > Config)
        final_temp = temperature
        
        if final_temp is None:
            # 如果未指定温度，使用角色预设
            if role == 'zealot': final_temp = 0.9
            elif role == 'reaper': final_temp = 0.8
            elif role == 'fulcrum': final_temp = 0.3
            # 否则保持 None，在 _chat_completion 中读取 yaml 配置
            
        return self._chat_completion(messages, model_key, final_temp)

    def _chat_completion(self, messages: List[Dict], model_key: str, temperature: Optional[float]) -> str:
        cfg = self.models_cfg.get(model_key)
        if not cfg:
            logger.warning(f"⚠️ 模型配置 '{model_key}' 未找到，尝试使用默认 '{self.default_model_key}'")
            cfg = self.models_cfg.get(self.default_model_key)
            if not cfg:
                return "[System Error: No valid model config found in models.yaml]"

        # 提取参数
        api_key = cfg.get("api_key")
        base_url = cfg.get("base_url", "").rstrip('/')
        model_id = cfg.get("model_id")
        timeout = cfg.get("timeout", 120)
        
        # 如果 temperature 仍为 None，使用 yaml 中的默认值，或者 0.7
        if temperature is None:
            temperature = cfg.get("temperature", 0.7)

        try:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            # 移除可能导致 403 的特殊 Header
            
            payload = {
                "model": model_id,
                "messages": messages,
                "temperature": temperature,
                "stream": False
            }
            
            resp = requests.post(
                f"{base_url}/chat/completions", 
                headers=headers, 
                json=payload, 
                timeout=timeout
            )
            
            if resp.status_code != 200:
                logger.error(f"API Error {resp.status_code}: {resp.text}")
                return f"[Error: API returned {resp.status_code}]"
            
            data = resp.json()
            if "choices" in data and len(data["choices"]) > 0:
                return data["choices"][0]["message"]["content"]
            else:
                logger.error(f"Unexpected API response format: {data}")
                return "[Error: Invalid API response]"

        except Exception as e:
            logger.error(f"❌ LLM API Error ({model_key}): {e}")
            return f"[Error: AI response failed - {str(e)}]"