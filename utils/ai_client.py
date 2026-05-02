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


def get_qwen_client() -> QwenClient:
    """获取全局千问客户端实例（单例模式）"""
    global _qwen_client
    if _qwen_client is None:
        _qwen_client = QwenClient()
    return _qwen_client

