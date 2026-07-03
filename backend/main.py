import os
import json
import uuid
import logging
import time
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timedelta

import httpx
import socketio
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import aiofiles

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")
UPLOAD_DIR = Path("./uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# --- FastAPI (HTTP) ---
fastapi_app = FastAPI(title="Hackathon Backend")
fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Socket.IO ---
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins='*',
    logger=True,
    engineio_logger=True,
    ping_timeout=120,
    ping_interval=25
)
chat_rooms = defaultdict(set)

# ✅ Более мягкий rate limiter
class RateLimiter:
    def __init__(self, max_requests: int = 20, time_window: int = 60):
        self.max_requests = max_requests  # ✅ 20 вместо 5
        self.time_window = time_window
        self.requests = []
    
    def can_make_request(self) -> bool:
        now = datetime.now()
        self.requests = [t for t in self.requests if now - t < timedelta(seconds=self.time_window)]
        return len(self.requests) < self.max_requests
    
    def record_request(self):
        self.requests.append(datetime.now())
    
    def get_wait_time(self) -> int:
        if not self.requests:
            return 0
        now = datetime.now()
        oldest = min(self.requests)
        wait_time = self.time_window - (now - oldest).seconds
        return max(0, wait_time)

rate_limiter = RateLimiter(max_requests=20, time_window=60)  # ✅ 20 запросов в минуту

import asyncio
from datetime import datetime, timedelta

# Храним время последней активности каждого клиента
client_activity = {}

@sio.event
async def connect(sid, environ):
    logger.info(f"🔌 Подключен: {sid}")
    client_activity[sid] = datetime.now()  # ✅ Записываем время
    await sio.emit('connected', {'sid': sid}, to=sid)

@sio.event
async def disconnect(sid):
    logger.info(f"🔌 Отключен: {sid}")
    client_activity.pop(sid, None)  # ✅ Удаляем из активности
    for room, members in list(chat_rooms.items()):
        members.discard(sid)
        if not members:
            del chat_rooms[room]

# ✅ Обновляем активность при каждом сообщении
@sio.on('*')
async def catch_all(event, sid, data):
    client_activity[sid] = datetime.now()
    logger.info(f"📥 [catch_all] '{event}' от {sid}: {data}")

# ✅ Фоновая задача очистки
async def cleanup_zombie_connections():
    """Каждые 5 минут удаляем неактивных клиентов"""
    while True:
        await asyncio.sleep(300)  # 5 минут
        now = datetime.now()
        inactive_threshold = timedelta(minutes=10)  # 10 минут неактивности
        
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
            # Принудительно закрываем соединение
            try:
                await sio.disconnect(sid)
            except:
                pass
        
        if inactive_sids:
            logger.info(f"🧹 Очищено {len(inactive_sids)} неактивных соединений")

# Запускаем фоновую задачу при старте
@fastapi_app.on_event("startup")
async def startup_event():
    asyncio.create_task(cleanup_zombie_connections())


# --- HTTP: Upload ---
@fastapi_app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        file_id = str(uuid.uuid4())
        safe_filename = f"{file_id}_{file.filename or 'unknown'}"
        async with aiofiles.open(UPLOAD_DIR / safe_filename, 'wb') as f:
            while chunk := await file.read(1024 * 1024):
                await f.write(chunk)
        logger.info(f"✅ Файл сохранен: {safe_filename}")
        return {"status": "ok", "filename": safe_filename, "file_id": file_id}
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки: {e}")
        raise HTTPException(status_code=500, detail="Ошибка сохранения")

# --- AI: Yandex с Rate Limiting ---
async def get_ai_answer(question: str, max_retries: int = 2) -> str:
    """
    Запрос к Yandex AI с rate limiting и retry логикой.
    """
    # ✅ Проверяем rate limit ПЕРЕД запросом
    if not rate_limiter.can_make_request():
        wait_time = rate_limiter.get_wait_time()
        raise Exception(f"Превышен лимит запросов. Подождите {wait_time} секунд.")
    
    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}",
        "x-folder-id": YANDEX_FOLDER_ID,
        "Content-Type": "application/json"
    }
    payload = {
        "modelUri": f"gpt://{YANDEX_FOLDER_ID}/yandexgpt-lite/latest",
        "completionOptions": {
            "stream": False,
            "temperature": 0.6,
            "maxTokens": 800
        },
        "messages": [{"role": "user", "text": question}]
    }
    
    # ✅ Раздельные таймауты
    timeout = httpx.Timeout(
        connect=10.0,
        read=30.0,
        write=10.0,
        pool=10.0
    )
    
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            rate_limiter.record_request()
            logger.info(f"🌐 Запрос к Yandex AI (попытка {attempt + 1}/{max_retries + 1})")
            
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, headers=headers, json=payload)
                
                # ✅ Специальная обработка 429
                if resp.status_code == 429:
                    retry_after = int(resp.headers.get('Retry-After', 60))
                    logger.warning(f"⚠️ Rate limit (429). Retry-After: {retry_after}с")
                    raise Exception(f"Превышен лимит запросов к AI. Подождите {retry_after} секунд.")
                
                resp.raise_for_status()
                return resp.json()["result"]["alternatives"][0]["message"]["text"]
                
        except (httpx.ConnectTimeout, httpx.ConnectError) as e:
            last_error = e
            logger.warning(f"⚠️ Попытка {attempt + 1}/{max_retries + 1}: ошибка соединения - {type(e).__name__}")
            if attempt < max_retries:
                import asyncio
                await asyncio.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s, 4s
                continue
        except httpx.TimeoutException as e:
            raise Exception("Превышено время ожидания ответа от AI")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                retry_after = int(e.response.headers.get('Retry-After', 60))
                raise Exception(f"Превышен лимит запросов к AI. Подождите {retry_after} секунд.")
            raise Exception(f"Ошибка Yandex API: {e.response.status_code}")
    
    raise Exception(f"Не удалось подключиться к Yandex AI после {max_retries + 1} попыток")

# --- Socket.IO Events ---
@sio.on('*')
async def catch_all(event, sid, data):
    logger.info(f"📥 [catch_all] '{event}' от {sid}: {data}")

@sio.event
async def connect(sid, environ):
    logger.info(f"🔌 Подключен: {sid}")
    await sio.emit('connected', {'sid': sid}, to=sid)

@sio.event
async def disconnect(sid):
    logger.info(f"🔌 Отключен: {sid}")
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

# --- AI обработчик ---
async def ask_ai(sid, data):
    """Вопрос к AI — ответ придёт всем в комнате"""
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
            'from_sid': sid
        }, room=chat_id)
        logger.info(f"✅ Ответ AI отправлен в комнату {chat_id}")
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Ошибка AI: {error_msg}", exc_info=True)
        await sio.emit('error', {'error': error_msg}, to=sid)

for alias in ['user_message', 'message', 'chat', 'ask', 'ask_ai']:
    sio.on(alias, ask_ai)

# --- ASGI App ---
app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app, socketio_path='socket.io')

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)