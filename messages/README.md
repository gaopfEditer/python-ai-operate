# Telegram群消息监听器

使用Telethon库监听Telegram群组消息的功能模块。

## 功能特性

- ✅ 监听指定Telegram群组的消息
- ✅ 支持监听所有群组消息（可选）
- ✅ 自动保存消息到日志文件
- ✅ 支持列出已加入的群组
- ✅ 详细的日志记录

## 安装依赖

```bash
pip install telethon
```

或者使用项目的requirements.txt（已包含telethon依赖）。

## 使用方法

### 1. 基本使用

直接运行脚本开始监听所有群组消息：

```bash
python messages/telegram_listener.py
```

首次运行时会要求输入手机号码和验证码进行登录。

### 2. 监听指定群组

编辑 `telegram_listener.py` 的 `main()` 函数，添加要监听的群组：

```python
# 方式1：使用群组用户名（@groupname）
listener.add_group('@groupname')

# 方式2：使用群组ID（数字ID，通常是负数）
listener.add_group('-1001234567890')
```

### 3. 列出已加入的群组

在代码中取消注释以下部分，可以查看所有已加入的群组：

```python
await listener.initialize()
groups = await listener.list_joined_groups()
for group in groups:
    logger.info(f"群组: {group['title']} (@{group['username'] or 'N/A'}) ID: {group['id']}")
```

### 4. 作为模块使用

```python
import asyncio
from messages.telegram_listener import TelegramListener

async def my_listener():
    listener = TelegramListener(
        api_id=31823718,
        api_hash='e3afd5534b4746148416175edf6847a6',
        session_file='messages/telegram_session.session'
    )
    
    # 添加要监听的群组
    listener.add_group('@your_group')
    
    # 开始监听
    await listener.start_listening()

asyncio.run(my_listener())
```

## 文件说明

- `telegram_listener.py`: 主监听器脚本
- `telegram_session.session`: Telegram会话文件（自动生成，用于保持登录状态）
- `messages_log.txt`: 消息日志文件（自动生成，记录所有监听到的消息）
- `telegram_listener.log`: 运行日志文件（自动生成）

## 配置说明

### API凭证

当前使用的API凭证：
- API ID: `31823718`
- API Hash: `e3afd5534b4746148416175edf6847a6`

如需修改，请编辑 `telegram_listener.py` 中的 `API_ID` 和 `API_HASH` 变量。

### 监听模式

- **指定群组模式**：添加了 `monitored_groups` 列表后，只监听列表中的群组
- **所有群组模式**：如果 `monitored_groups` 为空，将监听所有群组消息

## 注意事项

1. **首次登录**：首次运行需要输入手机号码和Telegram发送的验证码
2. **两步验证**：如果账号启用了两步验证，需要在代码中处理密码输入
3. **会话文件**：`telegram_session.session` 文件保存了登录状态，请妥善保管
4. **消息存储**：所有消息都会保存到 `messages_log.txt` 文件中
5. **权限**：确保账号有权限访问要监听的群组

## 故障排除

### 问题：无法登录

- 检查API ID和Hash是否正确
- 确认网络连接正常
- 检查手机号码格式是否正确

### 问题：收不到消息

- 确认账号已加入目标群组
- 检查群组标识符（用户名或ID）是否正确
- 查看日志文件了解详细错误信息

### 问题：权限错误

- 确保账号在群组中有读取消息的权限
- 某些私有群组可能需要特殊权限

## 日志格式

消息日志格式：
```
[2025-01-15 10:30:45] [群组名称] 发送者姓名 (@username): 消息内容
```

## 开发说明

- 使用 `asyncio` 进行异步处理
- 使用 `telethon` 库与Telegram API交互
- 支持事件驱动的消息处理
- 自动重连机制（由telethon库提供）

















