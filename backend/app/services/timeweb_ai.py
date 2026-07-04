import httpx
import asyncio
import json
import re
from typing import Optional
from app.config import TIMEWEB_API_KEY, TIMEWEB_BASE_URL
from app.services.rate_limiter import RateLimiter

import logging

logger = logging.getLogger(__name__)
# Rate limiter для Qwen (чуть больше лимит чем у Yandex)
qwen_rate_limiter = RateLimiter(max_requests=30, time_window=60)

async def get_ai_answer(
    question: str, 
    max_retries: int = 3,
    json_mode: bool = False,
    temperature: Optional[float] = None
) -> str:
    """Запрос к Qwen-3.5 Plus через TimeWeb с rate limiting и retry логикой."""
    
    if temperature is None:
        temperature = 0.05 if json_mode else 0.6
    
    if not qwen_rate_limiter.can_make_request():
        wait_time = qwen_rate_limiter.get_wait_time()
        raise Exception(f"Превышен лимит запросов к Qwen. Подождите {wait_time:.1f} секунд.")
    
    url = f"{TIMEWEB_BASE_URL}/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {TIMEWEB_API_KEY}",
        "Content-Type": "application/json",
    }
    
    messages = []
    if json_mode:
        messages.append({
            "role": "system",
            "content": "Ты — профессиональный парсер JSON. Возвращай ТОЛЬКО валидный JSON без пояснений и markdown-оберток."
        })
    messages.append({"role": "user", "content": question})
    
    payload = {
        "model": "qwen-3.5-plus",
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 4000,
    }
    
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    
    timeout = httpx.Timeout(
        connect=10.0,
        read=120.0,
        write=10.0,
        pool=10.0,
    )
    
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            qwen_rate_limiter.record_request()
            logger.info(f"🤖 Запрос к Qwen-3.5 Plus (попытка {attempt + 1}/{max_retries + 1})")
            
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, headers=headers, json=payload)
                
                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", 60))
                    logger.warning(f"⚠️ Qwen rate limit (429). Retry-After: {retry_after}с")
                    raise Exception(f"Превышен лимит запросов к Qwen. Подождите {retry_after} секунд.")
                
                if resp.status_code == 401:
                    raise Exception("Ошибка авторизации Qwen. Проверьте TIMEWEB_API_KEY")
                
                if resp.status_code >= 400:
                    logger.error(f"⚠️ Qwen API error: {resp.status_code} - {resp.text[:200]}")
                
                resp.raise_for_status()
                
                data = resp.json()
                result = data["choices"][0]["message"]["content"]
                
                # ✅ ИСПРАВЛЕНИЕ: убрали вызов _clean_and_validate_json
                # Очистка JSON делается в parser.py методом _clean_llm_json
                return result
                
        except (
            httpx.ConnectTimeout,
            httpx.ConnectError,
            httpx.ReadTimeout,
            httpx.TimeoutException,
        ) as e:
            last_error = e
            logger.warning(
                f"⚠️ Qwen: попытка {attempt + 1}/{max_retries + 1}: "
                f"{type(e).__name__} - {str(e)}"
            )
            if attempt < max_retries:
                wait_time = 2 ** attempt
                logger.info(f"   ⏳ Ждём {wait_time}с перед повторной попыткой...")
                await asyncio.sleep(wait_time)
                continue
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                retry_after = int(e.response.headers.get("Retry-After", 60))
                raise Exception(f"Превышен лимит запросов к Qwen. Подождите {retry_after} секунд.")
            raise Exception(f"Ошибка Qwen API: {e.response.status_code}") from e
            
        except json.JSONDecodeError as e:
            last_error = e
            logger.warning(f"⚠️ Qwen вернул невалидный JSON: {e}")
            if attempt < max_retries:
                await asyncio.sleep(2 ** attempt)
                continue
    
    raise Exception(f"Не удалось получить ответ от Qwen после {max_retries + 1} попыток: {last_error}") from last_error
    """Запрос к Qwen-3.5 Plus через TimeWeb с rate limiting и retry логикой."""
    
    if temperature is None:
        temperature = 0.05 if json_mode else 0.6
    
    if not qwen_rate_limiter.can_make_request():
        wait_time = qwen_rate_limiter.get_wait_time()
        raise Exception(f"Превышен лимит запросов к Qwen. Подождите {wait_time:.1f} секунд.")
    
    url = f"{TIMEWEB_BASE_URL}/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {TIMEWEB_API_KEY}",
        "Content-Type": "application/json",
    }
    
    messages = []
    if json_mode:
        messages.append({
            "role": "system",
            "content": "Ты — профессиональный парсер JSON. Возвращай ТОЛЬКО валидный JSON без пояснений и markdown-оберток."
        })
    messages.append({"role": "user", "content": question})
    
    payload = {
        "model": "qwen-3.5-plus",
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 4000,
    }
    
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    
    # ✅ УВЕЛИЧИВАЕМ TIMEOUT (было 60, стало 120)
    timeout = httpx.Timeout(
        connect=10.0,
        read=120.0,  # ← увеличено с 60 до 120 секунд
        write=10.0,
        pool=10.0,
    )
    
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            qwen_rate_limiter.record_request()
            logger.info(f"🤖 Запрос к Qwen-3.5 Plus (попытка {attempt + 1}/{max_retries + 1})")
            
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, headers=headers, json=payload)
                
                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", 60))
                    logger.warning(f"⚠️ Qwen rate limit (429). Retry-After: {retry_after}с")
                    raise Exception(f"Превышен лимит запросов к Qwen. Подождите {retry_after} секунд.")
                
                if resp.status_code == 401:
                    raise Exception("Ошибка авторизации Qwen. Проверьте TIMEWEB_API_KEY")
                
                if resp.status_code >= 400:
                    logger.error(f"⚠️ Qwen API error: {resp.status_code} - {resp.text[:200]}")
                
                resp.raise_for_status()
                
                data = resp.json()
                result = data["choices"][0]["message"]["content"]
                
                if json_mode:
                    result = _clean_and_validate_json(result)
                
                return result
                
        # ✅ ИСПРАВЛЕНИЕ: все эти исключения теперь делают retry
        except (httpx.ConnectTimeout, httpx.ConnectError, httpx.ReadTimeout) as e:
            last_error = e
            logger.warning(f"⚠️ Qwen: попытка {attempt + 1}/{max_retries + 1}: {type(e).__name__} - {str(e)}")
            if attempt < max_retries:
                wait_time = 2 ** attempt  # Экспоненциальная задержка: 1с, 2с, 4с
                logger.info(f"   ⏳ Ждём {wait_time}с перед повторной попыткой...")
                await asyncio.sleep(wait_time)
                continue
                
        except httpx.TimeoutException as e:
            # ✅ ИСПРАВЛЕНИЕ: TimeoutException тоже делает retry
            last_error = e
            logger.warning(f"⚠️ Qwen: попытка {attempt + 1}/{max_retries + 1}: TimeoutException - {str(e)}")
            if attempt < max_retries:
                wait_time = 2 ** attempt
                logger.info(f"   ⏳ Ждём {wait_time}с перед повторной попыткой...")
                await asyncio.sleep(wait_time)
                continue
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                retry_after = int(e.response.headers.get("Retry-After", 60))
                raise Exception(f"Превышен лимит запросов к Qwen. Подождите {retry_after} секунд.")
            raise Exception(f"Ошибка Qwen API: {e.response.status_code}") from e
            
        except json.JSONDecodeError as e:
            last_error = e
            logger.warning(f"⚠️ Qwen вернул невалидный JSON: {e}")
            if attempt < max_retries:
                await asyncio.sleep(2 ** attempt)
                continue
    
    # Если все попытки провалились
    raise Exception(f"Не удалось получить ответ от Qwen после {max_retries + 1} попыток: {last_error}") from last_error