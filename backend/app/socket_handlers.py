import logging

from app.services.yandex_ai import get_ai_answer
from app.socketio_app import chat_rooms, sio

logger = logging.getLogger(__name__)


async def handle_ai_request(sid, data):
    question = data.get('question') or data.get('text') or data.get('message')
    chat_id = data.get('chat_id') or data.get('room') or data.get('roomId') or 'default'

    logger.info(f"🤖 [ask_ai] Вызван для {sid}. Данные: {data}")

    if not question:
        await sio.emit('error', {'error': 'Нет текста вопроса'}, to=sid)
        return

    if sid not in chat_rooms.get(chat_id, set()):
        await sio.enter_room(sid, chat_id)
        chat_rooms[chat_id].add(sid)
        logger.info(f"👤 {sid} автоматически в комнате {chat_id}")

    await sio.emit('ai_thinking', {'sid': sid}, room=chat_id)

    try:
        answer = await get_ai_answer(question)
        await sio.emit('ai_answer', {
            'question': question,
            'answer': answer,
            'from_sid': sid,
        }, room=chat_id)
        logger.info(f"✅ Ответ AI отправлен в комнату {chat_id}")
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Ошибка AI: {error_msg}", exc_info=True)
        await sio.emit('error', {'error': error_msg}, to=sid)


for alias in ['user_message', 'message', 'chat', 'ask', 'ask_ai']:
    sio.on(alias, handle_ai_request)
