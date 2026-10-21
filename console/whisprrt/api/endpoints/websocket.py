"""
WebSocket相关的API端点
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from console.whisprrt.services.transcription import transcription_service
from console.whisprrt.services.whisper import whisper_service
from console.whisprrt.core.logging import logger

router = APIRouter()

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    处理WebSocket连接
    
    Args:
        websocket: WebSocket连接对象
    """
    await websocket.accept()
    transcription_service.connected_websockets.add(websocket)
    # 记录主事件循环，供音频线程安全推送
    transcription_service.bind_event_loop()

    try:
        await websocket.send_json({
            "event": "status",
            "data": {
                'status': 'connected',
                'model': whisper_service.model_name,
                'language': transcription_service.current_language
            }
        })
        # 保持连接；浏览器刷新会触发 disconnect，不应拖垮进程
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info("客户端已断开连接")
    except Exception as e:
        logger.warning("WebSocket 异常断开: %s", e)
    finally:
        transcription_service.connected_websockets.discard(websocket)
