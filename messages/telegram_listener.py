# coding=utf-8
"""
Telegram群消息监听器
使用telethon库监听指定Telegram群组的消息
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError
from telethon.tl.types import Channel, Chat, User

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('messages/telegram_listener.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Telegram API配置
API_ID = 31823718
API_HASH = 'e3afd5534b4746148416175edf6847a6'

# 会话文件路径
SESSION_FILE = Path(__file__).parent / 'telegram_session.session'

# 消息存储文件
MESSAGES_LOG_FILE = Path(__file__).parent / 'messages_log.txt'


class TelegramListener:
    """Telegram群消息监听器"""
    
    def __init__(self, api_id: int, api_hash: str, session_file: str):
        """
        初始化监听器
        
        Args:
            api_id: Telegram API ID
            api_hash: Telegram API Hash
            session_file: 会话文件路径
        """
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_file = session_file
        self.client: Optional[TelegramClient] = None
        self.monitored_groups: List[str] = []  # 要监听的群组用户名或ID列表
        
    async def initialize(self):
        """初始化Telegram客户端"""
        try:
            self.client = TelegramClient(
                str(self.session_file),
                self.api_id,
                self.api_hash
            )
            await self.client.start()
            logger.info("Telegram客户端初始化成功")
            
            # 获取当前用户信息
            me = await self.client.get_me()
            logger.info(f"已登录为: {me.first_name} {me.last_name or ''} (@{me.username or 'N/A'})")
            
        except SessionPasswordNeededError:
            logger.error("需要两步验证密码，请在代码中处理")
            raise
        except Exception as e:
            logger.error(f"初始化客户端失败: {e}")
            raise
    
    def add_group(self, group_identifier: str):
        """
        添加要监听的群组
        
        Args:
            group_identifier: 群组用户名（如 @groupname）或群组ID
        """
        if group_identifier not in self.monitored_groups:
            self.monitored_groups.append(group_identifier)
            logger.info(f"已添加监听群组: {group_identifier}")
    
    def remove_group(self, group_identifier: str):
        """
        移除监听的群组
        
        Args:
            group_identifier: 群组用户名或ID
        """
        if group_identifier in self.monitored_groups:
            self.monitored_groups.remove(group_identifier)
            logger.info(f"已移除监听群组: {group_identifier}")
    
    def save_message(self, message_text: str, sender: str, group_name: str, message_id: int):
        """
        保存消息到日志文件
        
        Args:
            message_text: 消息内容
            sender: 发送者信息
            group_name: 群组名称
            message_id: 消息ID
        """
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{timestamp}] [{group_name}] {sender}: {message_text}\n"
        
        try:
            with open(MESSAGES_LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(log_entry)
        except Exception as e:
            logger.error(f"保存消息失败: {e}")
    
    async def get_group_info(self, group_identifier: str):
        """
        获取群组信息
        
        Args:
            group_identifier: 群组用户名或ID
            
        Returns:
            群组实体对象
        """
        try:
            entity = await self.client.get_entity(group_identifier)
            return entity
        except Exception as e:
            logger.error(f"获取群组信息失败 {group_identifier}: {e}")
            return None
    
    async def list_joined_groups(self):
        """列出当前用户加入的所有群组"""
        try:
            dialogs = await self.client.get_dialogs()
            groups = []
            
            for dialog in dialogs:
                if isinstance(dialog.entity, (Channel, Chat)):
                    groups.append({
                        'id': dialog.entity.id,
                        'title': dialog.entity.title,
                        'username': getattr(dialog.entity, 'username', None),
                        'type': 'Channel' if isinstance(dialog.entity, Channel) else 'Chat'
                    })
            
            logger.info(f"找到 {len(groups)} 个群组/频道")
            return groups
        except Exception as e:
            logger.error(f"获取群组列表失败: {e}")
            return []
    
    def setup_event_handlers(self):
        """设置事件处理器"""
        if not self.client:
            logger.error("客户端未初始化")
            return
        
        @self.client.on(events.NewMessage)
        async def handle_new_message(event):
            """处理新消息事件"""
            try:
                # 获取消息信息
                message = event.message
                chat = await event.get_chat()
                
                # 检查是否是群组消息
                if not isinstance(chat, (Channel, Chat)):
                    return
                
                # 获取群组标识符
                group_id = chat.id
                group_username = getattr(chat, 'username', None)
                group_title = getattr(chat, 'title', 'Unknown')
                
                # 检查是否在监听列表中
                should_monitor = False
                if self.monitored_groups:
                    # 如果指定了监听列表，只监听列表中的群组
                    for identifier in self.monitored_groups:
                        if (str(group_id) == str(identifier) or 
                            (group_username and group_username == identifier.replace('@', ''))):
                            should_monitor = True
                            break
                else:
                    # 如果没有指定监听列表，监听所有群组
                    should_monitor = True
                
                if not should_monitor:
                    return
                
                # 获取发送者信息
                sender = await event.get_sender()
                if isinstance(sender, User):
                    sender_name = f"{sender.first_name} {sender.last_name or ''}".strip()
                    sender_username = f"@{sender.username}" if sender.username else "N/A"
                    sender_info = f"{sender_name} ({sender_username})"
                else:
                    sender_info = "Unknown"
                
                # 获取消息文本
                message_text = message.message or "[媒体消息]"
                
                # 记录消息
                logger.info(f"收到消息 - 群组: {group_title}, 发送者: {sender_info}, 内容: {message_text[:100]}")
                
                # 保存消息
                self.save_message(
                    message_text=message_text,
                    sender=sender_info,
                    group_name=group_title,
                    message_id=message.id
                )
                
            except Exception as e:
                logger.error(f"处理消息时出错: {e}")
        
        logger.info("事件处理器已设置")
    
    async def start_listening(self):
        """开始监听消息"""
        if not self.client:
            await self.initialize()
        
        self.setup_event_handlers()
        logger.info("开始监听Telegram消息...")
        logger.info(f"监听模式: {'指定群组' if self.monitored_groups else '所有群组'}")
        if self.monitored_groups:
            logger.info(f"监听群组列表: {self.monitored_groups}")
        
        # 保持运行
        await self.client.run_until_disconnected()
    
    async def stop(self):
        """停止监听"""
        if self.client:
            await self.client.disconnect()
            logger.info("已断开Telegram连接")


async def main():
    """主函数"""
    listener = TelegramListener(
        api_id=API_ID,
        api_hash=API_HASH,
        session_file=SESSION_FILE
    )
    
    try:
        # 可选：添加要监听的特定群组
        # 例如：listener.add_group('@groupname') 或 listener.add_group('-1001234567890')
        # 如果不添加任何群组，将监听所有群组消息
        
        # 示例：列出所有已加入的群组（可选）
        # await listener.initialize()
        # groups = await listener.list_joined_groups()
        # for group in groups[:10]:  # 只显示前10个
        #     logger.info(f"群组: {group['title']} (@{group['username'] or 'N/A'}) ID: {group['id']}")
        
        # 开始监听
        await listener.start_listening()
        
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在停止...")
        await listener.stop()
    except Exception as e:
        logger.error(f"运行出错: {e}")
        await listener.stop()
        raise


if __name__ == "__main__":
    asyncio.run(main())












