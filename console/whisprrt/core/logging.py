"""
日志配置模块
"""
import logging

_TRANSCRIPT_LOGGER = "whisper_live.transcript"
_AUDIO_LOGGER = "whisper_live.audio"


def setup_logging():
    """
    配置应用日志
    
    Returns:
        logging.Logger: 配置好的日志记录器
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logging.getLogger(_AUDIO_LOGGER).setLevel(logging.WARNING)
    return logging.getLogger(_TRANSCRIPT_LOGGER)


def configure_whisprrt_log_levels() -> None:
    """音频设备/流相关仅 WARNING+；文字稿转写保持 INFO。"""
    logging.getLogger(_AUDIO_LOGGER).setLevel(logging.WARNING)
    logging.getLogger(_TRANSCRIPT_LOGGER).setLevel(logging.INFO)
    logging.getLogger("whisper_live").setLevel(logging.INFO)


# 默认：转写服务日志
logger = setup_logging()