import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")
UPLOAD_DIR = Path("./uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# TimeWeb AI конфигурация
TIMEWEB_ACCESS_ID = os.getenv("TIMEWEB_ACCESS_ID")
TIMEWEB_BASE_URL = os.getenv("TIMEWEB_BASE_URL")
TIMEWEB_API_KEY = os.getenv("TIMEWEB_API_KEY")  # добавь в .env

# API ключ (должен быть в личном кабинете TimeWeb)
TIMEWEB_API_KEY = os.getenv("TIMEWEB_API_KEY")  # или укажи напрямую

# Модели (как они называются в TimeWeb)
QWEN_MODEL = "qwen-3.5"  # или "qwen-plus" - проверь в панели TimeWeb

# Neo4j
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

# Qdrant
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")  # для Docker
QDRANT_COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_NAME", "scientific_chunks")


if not YANDEX_API_KEY or not YANDEX_FOLDER_ID:
    logger.warning("YANDEX_API_KEY или YANDEX_FOLDER_ID не найдены в .env файле!")

