from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import socketio
import logging
import asyncio

from app.routes import router
from app.socketio_app import sio, cleanup_zombie_connections
from app.socket_handlers import *  # noqa: F401,F403

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title="Hackathon Backend")
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    app.include_router(router)

    @app.on_event("startup")
    async def startup_event():
        # ✅ 1. ПРЕДЗАГРУЗКА МОДЕЛЕЙ ЭМБЕДДИНГОВ
        logger.info("=" * 60)
        logger.info("🚀 STARTUP: Предзагрузка моделей эмбеддингов")
        logger.info("=" * 60)
        
        try:
            # Dense модель (multilingual-e5-large)
            logger.info("📦 [1/2] Загрузка модели dense: intfloat/multilingual-e5-large...")
            from app.services.embeddings import get_dense_model
            dense_model = get_dense_model()
            # ✅ СТАЛО:
            try:
                dim = dense_model.get_embedding_dimension()
            except AttributeError:
                dim = dense_model.get_sentence_embedding_dimension()
            logger.info(f"✅ Модель dense загружена (размер вектора: {dim})")
            
            # Sparse модель (SPLADE)
            logger.info("📦 [2/2] Загрузка модели sparse: prithivida/SpladePPEn_v1...")
            from app.services.embeddings import get_sparse_model
            get_sparse_model()
            logger.info("✅ Модель sparse загружена")
            
            logger.info("=" * 60)
            logger.info("✅ ВСЕ МОДЕЛИ ЗАГРУЖЕНЫ И ГОТОВЫ К РАБОТЕ")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"❌ Ошибка предзагрузки моделей: {e}", exc_info=True)
            logger.warning("⚠️ Приложение продолжит работу. Модели загрузятся при первом запросе.")
        
        # ✅ 2. ЗАПУСК ФОНОВОЙ ЗАДАЧИ ОЧИСТКИ ZOMBIE-СОЕДИНЕНИЙ
        logger.info("🔌 Запуск задачи очистки zombie-соединений...")
        asyncio.create_task(cleanup_zombie_connections())
        
        logger.info("✅ Приложение полностью запущено")

    return app


app = create_app()
ASGIApp = socketio.ASGIApp(sio, other_asgi_app=app, socketio_path='socket.io')