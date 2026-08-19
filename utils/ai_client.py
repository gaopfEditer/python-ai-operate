# coding=utf-8
"""
AI模型客户端
支持调用通义千问（Qwen）等AI模型
"""

import json
import requests
import yaml
from pathlib import Path
from typing import Optional, Dict, Any, List
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class QwenClient:
    """通义千问API客户端"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化千问客户端
        
        Args:
            config_path: 配置文件路径，默认使用项目根目录下的config/config.yaml
        """
        if config_path is None:
            project_root = Path(__file__).parent.parent
            config_path = project_root / "config" / "config.yaml"
        
        self.config_path = Path(config_path)
        self._load_config()
    
    def _load_config(self):
        """加载配置文件"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            ai_config = config.get('ai', {}).get('qwen', {})
            
            self.api_key = ai_config.get('api_key', '')
            self.api_endpoint = ai_config.get('api_endpoint', 
                'https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation')
            self.model = ai_config.get('model', 'qwen-turbo')
            self.temperature = ai_config.get('temperature', 0.7)
            self.max_tokens = ai_config.get('max_tokens', 2000)
            self.timeout = ai_config.get('timeout', 60)  # 增加默认超时时间，长文章需要更长时间
            self.enable = ai_config.get('enable', True)
            
            if not self.api_key:
                logger.warning("千问API Key未配置，AI功能将不可用")
                self.enable = False
                
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            self.enable = False
    
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        调用千问模型生成文本
        
        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词（可选）
            temperature: 温度参数，覆盖配置中的值
            max_tokens: 最大token数，覆盖配置中的值
            **kwargs: 其他参数
            
        Returns:
            包含生成结果的字典，格式：
            {
                'success': bool,
                'content': str,  # 生成的文本内容
                'error': str,    # 错误信息（如果失败）
                'usage': dict    # token使用情况（如果成功）
            }
        """
        if not self.enable:
            return {
                'success': False,
                'content': '',
                'error': '千问模型未启用或API Key未配置',
                'usage': {}
            }
        
        try:
            # 构建请求数据
            messages = []
            if system_prompt:
                messages.append({
                    'role': 'system',
                    'content': system_prompt
                })
            messages.append({
                'role': 'user',
                'content': prompt
            })
            
            data = {
                'model': self.model,
                'input': {
                    'messages': messages
                },
                'parameters': {
                    'temperature': temperature if temperature is not None else self.temperature,
                    'max_tokens': max_tokens if max_tokens is not None else self.max_tokens,
                    **kwargs
                }
            }
            
            # 发送请求
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            
            response = requests.post(
                self.api_endpoint,
                headers=headers,
                json=data,
                timeout=self.timeout
            )
            
            response.raise_for_status()
            result = response.json()
            
            # 调试：打印响应结构（仅在前几次调用时）
            logger.debug(f"API响应: {json.dumps(result, ensure_ascii=False, indent=2)}")
            
            # 解析响应 - 支持多种可能的响应格式
            content = None
            usage = result.get('usage', {})
            
            # 格式1: output.choices[0].message.content
            if result.get('output', {}).get('choices'):
                choices = result['output']['choices']
                if choices and len(choices) > 0:
                    content = choices[0].get('message', {}).get('content', '')
            
            # 格式2: output.text (某些API版本)
            if not content and result.get('output', {}).get('text'):
                content = result['output']['text']
            
            # 格式3: 直接包含content
            if not content and result.get('content'):
                content = result['content']
            
            # 格式4: output.result.text
            if not content and result.get('output', {}).get('result', {}).get('text'):
                content = result['output']['result']['text']
            
            if content:
                return {
                    'success': True,
                    'content': content,
                    'error': '',
                    'usage': usage
                }
            else:
                # 返回详细错误信息
                error_msg = f'API响应格式异常，响应内容: {json.dumps(result, ensure_ascii=False)[:500]}'
                logger.error(error_msg)
                return {
                    'success': False,
                    'content': '',
                    'error': error_msg,
                    'usage': usage
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"千问API请求失败: {e}")
            return {
                'success': False,
                'content': '',
                'error': f'API请求失败: {str(e)}',
                'usage': {}
            }
        except Exception as e:
            logger.error(f"调用千问模型失败: {e}")
            return {
                'success': False,
                'content': '',
                'error': f'调用失败: {str(e)}',
                'usage': {}
            }
    
    def generate_with_prompt_file(
        self,
        prompt_file: str,
        user_input: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        使用提示词文件生成内容
        
        Args:
            prompt_file: 提示词文件路径（相对于项目根目录）
            user_input: 用户输入内容
            **kwargs: 传递给generate的其他参数
            
        Returns:
            生成结果字典
        """
        try:
            project_root = Path(__file__).parent.parent
            prompt_path = project_root / prompt_file
            
            if not prompt_path.exists():
                return {
                    'success': False,
                    'content': '',
                    'error': f'提示词文件不存在: {prompt_file}',
                    'usage': {}
                }
            
            with open(prompt_path, 'r', encoding='utf-8') as f:
                system_prompt = f.read()
            
            # 将用户输入插入到提示词中
            full_prompt = f"{user_input}\n\n请根据以上信息生成内容。"
            
            return self.generate(
                prompt=full_prompt,
                system_prompt=system_prompt,
                **kwargs
            )
            
        except Exception as e:
            logger.error(f"读取提示词文件失败: {e}")
            return {
                'success': False,
                'content': '',
                'error': f'读取提示词文件失败: {str(e)}',
                'usage': {}
            }


# 全局客户端实例
_qwen_client: Optional[QwenClient] = None
_ollama_client: Optional["OllamaClient"] = None
_deepseek_client: Optional["DeepSeekClient"] = None


def get_qwen_client() -> QwenClient:
    """获取全局千问客户端实例（单例模式）"""
    global _qwen_client
    if _qwen_client is None:
        _qwen_client = QwenClient()
    return _qwen_client


class DeepSeekClient:
    """DeepSeek API 客户端（OpenAI 兼容 chat/completions）"""

    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            project_root = Path(__file__).parent.parent
            config_path = project_root / "config" / "config.yaml"
        self.config_path = Path(config_path)
        self._load_config()

    def _load_config(self):
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
            ds = (config.get("ai") or {}).get("deepseek") or {}
            self.api_key = str(ds.get("api_key") or "").strip()
            self.api_endpoint = str(
                ds.get("api_endpoint")
                or "https://api.deepseek.com/chat/completions"
            ).strip()
            self.model = str(ds.get("model") or "deepseek-chat").strip()
            self.temperature = float(ds.get("temperature", 0.7))
            self.max_tokens = int(ds.get("max_tokens", 2000))
            self.timeout = int(ds.get("timeout", 90))
            self.enable = bool(ds.get("enable", True)) and bool(self.api_key)
            if not self.api_key:
                logger.warning("DeepSeek API Key 未配置，DeepSeek 功能将不可用")
                self.enable = False
        except Exception as e:
            logger.error(f"加载 DeepSeek 配置失败: {e}")
            self.enable = False
            self.api_key = ""
            self.api_endpoint = "https://api.deepseek.com/chat/completions"
            self.model = "deepseek-chat"
            self.temperature = 0.7
            self.max_tokens = 2000
            self.timeout = 90

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        if not self.enable:
            return {
                "success": False,
                "content": "",
                "error": "DeepSeek 未启用或 API Key 未配置",
                "usage": {},
                "provider": "deepseek",
                "model": getattr(self, "model", "deepseek-chat"),
            }
        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        data = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
        }
        for k, v in kwargs.items():
            if k not in data:
                data[k] = v
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            session = requests.Session()
            session.trust_env = False
            resp = session.post(
                self.api_endpoint,
                headers=headers,
                json=data,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            result = resp.json() if resp.content else {}
            content = ""
            choices = result.get("choices") if isinstance(result, dict) else None
            if isinstance(choices, list) and choices:
                msg = choices[0].get("message") if isinstance(choices[0], dict) else {}
                if isinstance(msg, dict):
                    content = str(msg.get("content") or "")
            usage = result.get("usage") if isinstance(result, dict) else {}
            if content and content.strip():
                return {
                    "success": True,
                    "content": content.strip(),
                    "error": "",
                    "usage": usage if isinstance(usage, dict) else {},
                    "provider": "deepseek",
                    "model": self.model,
                }
            return {
                "success": False,
                "content": "",
                "error": f"DeepSeek 空响应: {json.dumps(result, ensure_ascii=False)[:400]}",
                "usage": {},
                "provider": "deepseek",
                "model": self.model,
            }
        except requests.exceptions.RequestException as e:
            err_body = ""
            try:
                if getattr(e, "response", None) is not None:
                    err_body = (e.response.text or "")[:300]
            except Exception:
                pass
            logger.error(f"DeepSeek API 请求失败: {e} {err_body}")
            return {
                "success": False,
                "content": "",
                "error": f"DeepSeek 请求失败: {e}" + (f" | {err_body}" if err_body else ""),
                "usage": {},
                "provider": "deepseek",
                "model": self.model,
            }
        except Exception as e:
            logger.error(f"调用 DeepSeek 失败: {e}")
            return {
                "success": False,
                "content": "",
                "error": f"DeepSeek 调用失败: {e}",
                "usage": {},
                "provider": "deepseek",
                "model": self.model,
            }


def get_deepseek_client() -> DeepSeekClient:
    global _deepseek_client
    if _deepseek_client is None:
        _deepseek_client = DeepSeekClient()
    return _deepseek_client


class OllamaClient:
    """本地 Ollama 客户端（POST {base}/api/generate，对齐 polish.py）。"""

    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            project_root = Path(__file__).parent.parent
            config_path = project_root / "config" / "config.yaml"
        self.config_path = Path(config_path)
        self._load_config()

    def _load_config(self) -> None:
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
            ai = config.get("ai") or {}
            o = ai.get("ollama") or {}
            self.base_url = str(o.get("base_url") or "http://127.0.0.1:11434").rstrip("/")
            self.model = str(o.get("model") or "gemma-uncensored").strip()
            self.timeout = int(o.get("timeout") or 120)
            self.enable = bool(o.get("enable", True))
            if not self.base_url or not self.model:
                self.enable = False
        except Exception as e:
            logger.error(f"加载 Ollama 配置失败: {e}")
            self.enable = False
            self.base_url = "http://127.0.0.1:11434"
            self.model = ""
            self.timeout = 120

    def reachable(self, timeout: float = 1.5) -> bool:
        if not self.enable or not self.base_url:
            return False
        try:
            from urllib.parse import urlparse
            import socket

            parsed = urlparse(self.base_url if "://" in self.base_url else f"http://{self.base_url}")
            host = (parsed.hostname or "").strip().lower()
            port = parsed.port or 11434
            if host in {"127.0.0.1", "localhost"}:
                with socket.create_connection((host, int(port)), timeout=timeout):
                    return True
            r = requests.get(f"{self.base_url}/api/tags", timeout=timeout)
            return r.status_code < 500
        except Exception:
            return False

    def has_model(self, timeout: float = 3.0) -> bool:
        """本机是否已拉取配置中的 model（名称或 name:tag 前缀匹配）。"""
        if not self.reachable(timeout=min(1.5, timeout)):
            return False
        want = (self.model or "").strip().lower()
        if not want:
            return False
        try:
            session = requests.Session()
            session.trust_env = False
            r = session.get(f"{self.base_url}/api/tags", timeout=timeout)
            r.raise_for_status()
            data = r.json() if r.content else {}
            models = data.get("models") if isinstance(data, dict) else None
            if not isinstance(models, list):
                return True  # 探测失败时不阻断，交给 generate 再试
            names = []
            for m in models:
                if not isinstance(m, dict):
                    continue
                name = str(m.get("name") or m.get("model") or "").strip().lower()
                if name:
                    names.append(name)
            if not names:
                return False
            if want in names:
                return True
            # gemma-uncensored 可匹配 gemma-uncensored:latest
            return any(n == want or n.startswith(want + ":") for n in names)
        except Exception:
            return True

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        if not self.enable:
            return {
                "success": False,
                "content": "",
                "error": "Ollama 未启用或配置不完整",
                "usage": {},
                "provider": "ollama",
            }
        if not self.reachable():
            return {
                "success": False,
                "content": "",
                "error": f"Ollama 不可达: {self.base_url}",
                "usage": {},
                "provider": "ollama",
            }
        if not self.has_model():
            return {
                "success": False,
                "content": "",
                "error": f"Ollama 未找到模型: {self.model}",
                "usage": {},
                "provider": "ollama",
                "model": self.model,
            }

        full_prompt = prompt or ""
        if system_prompt:
            full_prompt = f"{system_prompt.strip()}\n\n{full_prompt}"

        payload: Dict[str, Any] = {
            "model": self.model,
            "prompt": full_prompt,
            "stream": False,
        }
        options: Dict[str, Any] = {}
        if temperature is not None:
            options["temperature"] = temperature
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        if options:
            payload["options"] = options
        payload.update(kwargs)

        url = f"{self.base_url}/api/generate"
        try:
            session = requests.Session()
            session.trust_env = False
            r = session.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=self.timeout,
            )
            r.raise_for_status()
            raw = r.json() if r.content else {}
            text = raw.get("response") if isinstance(raw, dict) else ""
            if not isinstance(text, str) or not text.strip():
                return {
                    "success": False,
                    "content": "",
                    "error": "Ollama 空响应",
                    "usage": {},
                    "provider": "ollama",
                    "model": self.model,
                }
            return {
                "success": True,
                "content": text.strip(),
                "error": "",
                "usage": {},
                "provider": "ollama",
                "model": self.model,
            }
        except Exception as e:
            logger.error(f"Ollama 请求失败: {e}")
            return {
                "success": False,
                "content": "",
                "error": f"Ollama 请求失败: {e}",
                "usage": {},
                "provider": "ollama",
            }


def get_ollama_client() -> OllamaClient:
    global _ollama_client
    if _ollama_client is None:
        _ollama_client = OllamaClient()
    return _ollama_client


class PreferAIClient:
    """
    统一 AI 客户端：按 config.ai.prefer 路由。
    支持 deepseek / ollama / qwen 及 *_first 级联。
    """

    @property
    def enable(self) -> bool:
        d = get_deepseek_client()
        if d.enable:
            return True
        o = get_ollama_client()
        if o.enable and o.reachable():
            return True
        q = get_qwen_client()
        return bool(q.enable)

    @property
    def provider_hint(self) -> str:
        prefer = "deepseek_first"
        try:
            project_root = Path(__file__).parent.parent
            with open(project_root / "config" / "config.yaml", "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            prefer = str((cfg.get("ai") or {}).get("prefer") or prefer).strip().lower()
        except Exception:
            pass
        d = get_deepseek_client()
        o = get_ollama_client()
        q = get_qwen_client()
        if prefer in ("deepseek", "deepseek_first") and d.enable:
            return f"deepseek:{d.model}"
        if prefer in ("ollama", "ollama_first") and o.enable and o.reachable() and o.has_model():
            return f"ollama:{o.model}"
        if d.enable:
            return f"deepseek:{d.model}"
        if o.enable and o.reachable() and o.has_model():
            return f"ollama:{o.model}"
        if q.enable:
            return f"qwen:{q.model}"
        return "none"

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        return generate_text(
            prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )


_prefer_client: Optional[PreferAIClient] = None


def get_ai_client() -> PreferAIClient:
    """获取统一 AI 客户端。"""
    global _prefer_client
    if _prefer_client is None:
        _prefer_client = PreferAIClient()
    return _prefer_client


def generate_text(
    prompt: str,
    system_prompt: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    按 config.ai.prefer 路由：
    - deepseek_first：DeepSeek → Ollama → 千问
    - ollama_first：Ollama → DeepSeek → 千问
    - deepseek / ollama / qwen：仅该通道
    """
    prefer = "deepseek_first"
    try:
        project_root = Path(__file__).parent.parent
        with open(project_root / "config" / "config.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        prefer = str((cfg.get("ai") or {}).get("prefer") or "deepseek_first").strip().lower()
    except Exception:
        pass

    def _ollama():
        return get_ollama_client().generate(prompt, system_prompt=system_prompt, **kwargs)

    def _deepseek():
        return get_deepseek_client().generate(prompt, system_prompt=system_prompt, **kwargs)

    def _qwen():
        r = get_qwen_client().generate(prompt, system_prompt=system_prompt, **kwargs)
        if isinstance(r, dict):
            r.setdefault("provider", "qwen")
        return r

    if prefer == "deepseek":
        return _deepseek()
    if prefer == "qwen":
        return _qwen()
    if prefer == "ollama":
        return _ollama()

    if prefer == "ollama_first":
        r = _ollama()
        if r.get("success"):
            return r
        logger.warning(f"Ollama 不可用，回退 DeepSeek: {r.get('error')}")
        r2 = _deepseek()
        if r2.get("success"):
            return r2
        logger.warning(f"DeepSeek 不可用，回退千问: {r2.get('error')}")
        return _qwen()

    # deepseek_first（默认）
    r = _deepseek()
    if r.get("success"):
        return r
    logger.warning(f"DeepSeek 不可用，回退 Ollama: {r.get('error')}")
    r2 = _ollama()
    if r2.get("success"):
        return r2
    logger.warning(f"Ollama 不可用，回退千问: {r2.get('error')}")
    return _qwen()

