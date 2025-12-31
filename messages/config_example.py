# coding=utf-8
"""
Telegram监听器配置示例文件
复制此文件为 config.py 并修改配置
"""

# Telegram API配置
API_ID = 31823718
API_HASH = 'e3afd5534b4746148416175edf6847a6'

# 要监听的群组列表
# 可以是群组用户名（如 '@groupname'）或群组ID（如 '-1001234567890'）
# 如果列表为空，将监听所有群组消息
MONITORED_GROUPS = [
    # '@example_group',
    # '-1001234567890',
]

# 会话文件路径（相对于此文件）
SESSION_FILE = 'telegram_session.session'

# 消息日志文件路径（相对于此文件）
MESSAGES_LOG_FILE = 'messages_log.txt'

# 运行日志文件路径（相对于此文件）
LOG_FILE = 'telegram_listener.log'



