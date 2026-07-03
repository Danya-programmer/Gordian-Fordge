import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta

import socketio

logger = logging.getLogger(__name__)

sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins='*',
    logger=True,
    engineio_logger=True,
    ping_timeout=120,
    ping_interval=25,
)
chat_rooms = defaultdict(set)
client_activity = {}


@sio.event
async def connect(sid, environ):
    logger.info(f"🔌 Подключен: {sid}")
    client_activity[sid] = datetime.now()
    await sio.emit('connected', {'sid': sid}, to=sid)


@sio.event
async def disconnect(sid):
    logger.info(f"🔌 Отключен: {sid}")
    client_activity.pop(sid, None)
    for room, members in list(chat_rooms.items()):
        members.discard(sid)
        if not members:
            del chat_rooms[room]


@sio.event
async def join_chat(sid, data):
    chat_id = data.get('chat_id')
    if not chat_id:
        return await sio.emit('error', {'error': 'chat_id обязателен'}, to=sid)
    await sio.enter_room(sid, chat_id)
    chat_rooms[chat_id].add(sid)
    logger.info(f"👤 {sid} в комнате {chat_id}")
    await sio.emit('user_joined', {'sid': sid}, room=chat_id, skip_sid=sid)


@sio.event
async def leave_chat(sid, data):
    chat_id = data.get('chat_id')
    if chat_id in chat_rooms:
        await sio.leave_room(sid, chat_id)
        chat_rooms[chat_id].discard(sid)
        await sio.emit('user_left', {'sid': sid}, room=chat_id, skip_sid=sid)


async def cleanup_zombie_connections():
    """Каждые 5 минут удаляем неактивных клиентов."""
    while True:
        await asyncio.sleep(300)
        now = datetime.now()
        inactive_threshold = timedelta(minutes=10)

        inactive_sids = [
            sid for sid, last_activity in client_activity.items()
            if now - last_activity > inactive_threshold
        ]

        for sid in inactive_sids:
            logger.info(f"🧹 Удаляю неактивного клиента: {sid}")
            client_activity.pop(sid, None)
            for room, members in list(chat_rooms.items()):
                members.discard(sid)
                if not members:
                    del chat_rooms[room]
            try:
                await sio.disconnect(sid)
            except Exception:
                pass

        if inactive_sids:
            logger.info(f"🧹 Очищено {len(inactive_sids)} неактивных соединений")
