import asyncio
import json
from typing import Optional

import httpx

from app.config import YANDEX_API_KEY, YANDEX_FOLDER_ID
from app.services.rate_limiter import RateLimiter

import logging

logger = logging.getLogger(__name__)
rate_limiter = RateLimiter(max_requests=20, time_window=60)


async def get_ai_answer(question: str, max_retries: int = 2) -> str:
    """Запрос к Yandex AI с rate limiting и retry логикой."""
    if not rate_limiter.can_make_request():
        wait_time = rate_limiter.get_wait_time()
        raise Exception(f"Превышен лимит запросов. Подождите {wait_time} секунд.")

    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}",
        "x-folder-id": YANDEX_FOLDER_ID,
        "Content-Type": "application/json",
    }
    payload = {
        "modelUri": f"gpt://{YANDEX_FOLDER_ID}/yandexgpt-lite/latest",
        "completionOptions": {
            "stream": False,
            "temperature": 0.6,
            "maxTokens": 8000,
        },
        "messages": [{"role": "user", "text": question}],
    }

    timeout = httpx.Timeout(
        connect=10.0,
        read=30.0,
        write=10.0,
        pool=10.0,
    )

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            rate_limiter.record_request()
            logger.info(f"🌐 Запрос к Yandex AI (попытка {attempt + 1}/{max_retries + 1})")

            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, headers=headers, json=payload)

                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", 60))
                    logger.warning(f"⚠️ Rate limit (429). Retry-After: {retry_after}с")
                    raise Exception(f"Превышен лимит запросов к AI. Подождите {retry_after} секунд.")

                resp.raise_for_status()
                return resp.json()["result"]["alternatives"][0]["message"]["text"]

        except (httpx.ConnectTimeout, httpx.ConnectError) as e:
            last_error = e
            logger.warning(f"⚠️ Попытка {attempt + 1}/{max_retries + 1}: ошибка соединения - {type(e).__name__}")
            if attempt < max_retries:
                await asyncio.sleep(2 ** attempt)
                continue
        except httpx.TimeoutException as e:
            raise Exception("Превышено время ожидания ответа от AI") from e
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                retry_after = int(e.response.headers.get("Retry-After", 60))
                raise Exception(f"Превышен лимит запросов к AI. Подождите {retry_after} секунд.")
            raise Exception(f"Ошибка Yandex API: {e.response.status_code}") from e

    raise Exception(f"Не удалось подключиться к Yandex AI после {max_retries + 1} попыток") from last_error
