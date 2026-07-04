import logging

from app.services.qdrant_service import QdrantService
from app.services.graph_service.config import get_driver
from app.services.graph_service.graph_db import GraphDB
from app.services.search_service.search_service import SearchService
from app.socketio_app import chat_rooms, sio

logger = logging.getLogger(__name__)


async def handle_search(sid, data):
    """
    Главный обработчик — умный поиск по базе знаний.
    Возвращает ответ в формате, который ждёт фронтенд:
    - ai_thinking (в начале)
    - ai_answer (с результатом)
    """
    question = data.get('question') or data.get('text') or data.get('message')
    chat_id = data.get('chat_id') or data.get('room') or data.get('roomId') or 'default'

    logger.info(f"🔍 [search] Запрос от {sid}: {question}")

    if not question:
        await sio.emit('error', {'error': 'Нет текста вопроса'}, to=sid)
        return

    # Автоматическое подключение к комнате
    if sid not in chat_rooms.get(chat_id, set()):
        await sio.enter_room(sid, chat_id)
        chat_rooms[chat_id].add(sid)
        logger.info(f"👤 {sid} в комнате {chat_id}")

    # ✅ СТАРОЕ СОБЫТИЕ: ai_thinking
    await sio.emit('ai_thinking', {'sid': sid}, room=chat_id)

    try:
        # Инициализация сервисов
        qdrant_service = QdrantService()
        driver = get_driver()
        graph_db = GraphDB(driver)
        search_service = SearchService(qdrant_service, graph_db)

        # Выполнение поиска
        result = await search_service.search(question)

        # ✅ СТАРОЕ СОБЫТИЕ: ai_answer
        # Формат совместим с предыдущим фронтендом
        await sio.emit('ai_answer', {
            'question': question,
            'answer': result['answer'],
            'from_sid': sid,
            # Дополнительные поля (фронтенд может их игнорировать)
            'sources': result.get('sources', []),
            'strategy': result.get('strategy', 'qdrant_only'),
            'debug': result.get('debug'),
        }, room=chat_id)

        driver.close()

        logger.info(
            f"✅ Поиск завершён: стратегия={result['strategy']}, "
            f"источников={len(result['sources'])}"
        )

    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Ошибка поиска: {error_msg}", exc_info=True)
        await sio.emit('error', {'error': error_msg}, to=sid)


# ВСЕ события ведут к поиску
for alias in ['user_message', 'message', 'chat', 'ask', 'ask_ai', 'search', 'ask_search']:
    sio.on(alias, handle_search)