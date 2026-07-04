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
        import json
        from pathlib import Path
        from app.services.parser import DocumentParser
        from app.services.graph_service.config import get_driver
        from app.services.graph_service.graph_db import GraphDB
        from app.services.timeweb_ai import get_ai_answer
        
        file_id = str(uuid.uuid4())
        safe_filename = f"{file_id}_{file.filename or 'unknown'}"
        file_path = UPLOAD_DIR / safe_filename
        
        # 1. Сохраняем оригинальный файл
        async with aiofiles.open(file_path, 'wb') as f:
            while chunk := await file.read(1024 * 1024):
                await f.write(chunk)
        
        logger.info(f"✅ Файл сохранен: {safe_filename}")
        
        # 2. Извлекаем текст
        text_content = None
        metadata = None
        
        try:
            parsed = parse_file(str(file_path))
            text_content = parsed['text']
            metadata = parsed.get('metadata', {})
            logger.info(f"✅ Текст извлечен: {len(text_content or '')} символов")
        except Exception as parse_error:
            logger.warning(f"⚠️ Не удалось извлечь текст: {parse_error}")
            raise HTTPException(status_code=400, detail=f"Ошибка парсинга файла: {parse_error}")
        
        if not text_content or len(text_content.strip()) < 100:
            raise HTTPException(status_code=400, detail="Файл слишком короткий или пустой")
        
        # 3. Формируем метаданные
        doc_metadata = {
            "doc_id": file_id,
            "title": metadata.get('title', file.filename or 'Unknown'),
            "year": metadata.get('year'),
            "authors": metadata.get('authors', []),
            "file_path": str(file_path),
        }
        
        # 4. Запускаем парсер
        parse_result = None
        try:
            driver = get_driver()
            db = GraphDB(driver)
            
            async def llm_client(prompt: str) -> str:
                return await get_ai_answer(
                    question=prompt,
                    max_retries=3,
                    json_mode=True
                )
            
            parser = DocumentParser(db, llm_client, max_concurrent=3)
            
            logger.info(f"🔍 Запуск парсинга документа {file_id}...")
            parse_result = await parser.parse_document(text_content, doc_metadata)
            
            logger.info(f"✅ Документ обработан: {parse_result['chunks_successful']}/{parse_result['chunks_processed']} чанков успешно")
            
            db.close()
            
        except Exception as parse_error:
            logger.error(f"❌ Критическая ошибка парсинга: {parse_error}", exc_info=True)
            # ✅ НЕ ПАДАЕМ, а сохраняем то, что есть
            parse_result = {
                "doc_id": file_id,
                "chunks_processed": 0,
                "chunks_successful": 0,
                "chunks_failed": 0,
                "nodes_created": 0,
                "edges_created": 0,
                "chunks_data": [],
                "errors": [{"error": f"Критическая ошибка: {parse_error}"}],
            }
        
        # 5. ✅ СОХРАНЯЕМ JSON ВСЕГДА, даже если были ошибки
        json_filename = f"{file_id}_parsed.json"
        json_file_path = UPLOAD_DIR / json_filename
        
        output_json = {
            "doc_id": file_id,
            "filename": safe_filename,
            "metadata": metadata,
            "statistics": {
                "chunks_processed": parse_result["chunks_processed"],
                "chunks_successful": parse_result["chunks_successful"],
                "chunks_failed": parse_result["chunks_failed"],
                "nodes_created": parse_result["nodes_created"],
                "edges_created": parse_result["edges_created"],
            },
            "errors": parse_result.get("errors", []),
            "chunks": parse_result["chunks_data"],
        }
        
        async with aiofiles.open(json_file_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(output_json, ensure_ascii=False, indent=2))
        
        logger.info(f"💾 Результат парсинга сохранен: {json_filename}")
        
        # 6. Формируем ответ
        response = {
            "status": "ok" if parse_result["chunks_failed"] == 0 else "partial",
            "file_id": file_id,
            "filename": safe_filename,
            "chunks_processed": parse_result['chunks_processed'],
            "chunks_successful": parse_result['chunks_successful'],
            "chunks_failed": parse_result['chunks_failed'],
            "nodes_created": parse_result.get('nodes_created', 0),
            "edges_created": parse_result.get('edges_created', 0),
            "parsed_json_file": json_filename,
        }
        
        if metadata:
            response["metadata"] = metadata
        
        if parse_result["chunks_failed"] > 0:
            response["errors"] = parse_result["errors"]
        
        logger.info(f"✅ Документ полностью обработан: {response}")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка сохранения: {str(e)}")