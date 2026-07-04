import logging

from app.services.qdrant_service import QdrantService
from app.services.graph_service.config import get_driver
from app.services.graph_service.graph_db import GraphDB
from app.services.search_service.search_service import SearchService
from app.socketio_app import chat_rooms, sio


from app.services.document_service import document_service
from app.services.document_repository import DocumentModel

import uuid

from app.services.document_repository import DocumentRepository
from app.services.s3_service import s3_service


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



# ============================================================
# ОБРАБОТЧИКИ ДОКУМЕНТОВ
# ============================================================

@sio.on('get_documents')
async def handle_get_documents(sid, data=None):
    """Получить список документов через WebSocket."""
    try:
        from app.services.document_repository import DocumentRepository
        from app.services.s3_service import s3_service

        documents = await DocumentRepository.list_all()

        result = []
        for doc in documents:
            try:
                file_url = await s3_service.get_presigned_url(doc.s3_key)
            except Exception:
                file_url = None

            result.append({
                "id": str(doc.id),
                "original_name": doc.original_name,
                "file_size": doc.file_size,
                "mime_type": doc.mime_type,
                "status": doc.status,
                "error_message": doc.error_message,
                "chunks_count": doc.chunks_count,
                "nodes_count": doc.nodes_count,
                "edges_count": doc.edges_count,
                "file_url": file_url,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                "processed_at": doc.processed_at.isoformat() if doc.processed_at else None,
            })

        await sio.emit('documents_list', {"documents": result}, to=sid)

    except Exception as e:
        logger.error(f"❌ Ошибка получения списка документов: {e}", exc_info=True)
        await sio.emit('error', {'error': str(e)}, to=sid)