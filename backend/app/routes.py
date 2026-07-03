import logging
from fastapi import APIRouter, File, HTTPException, UploadFile
import aiofiles

from app.config import UPLOAD_DIR
from app.services.file_parser import parse_file

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        import uuid
        from pathlib import Path
        
        file_id = str(uuid.uuid4())
        safe_filename = f"{file_id}_{file.filename or 'unknown'}"
        file_path = UPLOAD_DIR / safe_filename
        
        # 1. Сохраняем оригинальный файл
        async with aiofiles.open(file_path, 'wb') as f:
            while chunk := await file.read(1024 * 1024):
                await f.write(chunk)
        
        logger.info(f"✅ Файл сохранен: {safe_filename}")
        
        # 2. Пытаемся извлечь текст и сохранить рядом
        text_content = None
        metadata = None
        text_file_path = None
        
        try:
            # Парсим файл
            parsed = parse_file(str(file_path))
            text_content = parsed['text']
            metadata = parsed['metadata']
            
            # Сохраняем текст в отдельный файл рядом
            # Имя: abc123_document.pdf → abc123_document.txt
            text_filename = Path(safe_filename).stem + '.txt'
            text_file_path = UPLOAD_DIR / text_filename
            
            async with aiofiles.open(text_file_path, 'w', encoding='utf-8') as f:
                await f.write(text_content or '')
            
            logger.info(f"✅ Текст сохранен: {text_filename} ({len(text_content or '')} символов)")
            
        except Exception as parse_error:
            # Если парсинг не удался — не падаем, просто логируем
            logger.warning(f"⚠️ Не удалось извлечь текст: {parse_error}")
        
        # 3. Формируем ответ
        response = {
            "status": "ok",
            "filename": safe_filename,
            "file_id": file_id,
        }
        
        # Добавляем текст и метаданные, если они есть
        if text_content is not None:
            response["text"] = text_content
            response["text_filename"] = text_file_path.name if text_file_path else None
        
        if metadata is not None:
            response["metadata"] = metadata
        
        return response
        
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Ошибка сохранения")