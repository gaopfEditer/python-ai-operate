"""
Pydantic 模型定义
"""
from typing import Union
from pydantic import BaseModel, field_validator

class ModelRequest(BaseModel):
    """模型选择请求"""
    model: str

class LanguageRequest(BaseModel):
    """语言选择请求"""
    language: str

class TimestampRequest(BaseModel):
    """时间戳显示设置请求"""
    show_timestamp: bool

class DeviceRequest(BaseModel):
    """音频设备选择请求"""
    device_id: str

    @field_validator("device_id", mode="before")
    @classmethod
    def coerce_device_id(cls, v: Union[str, int, None]) -> str:
        if v is None:
            return "default"
        return str(v)
