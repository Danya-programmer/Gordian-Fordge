import logging
import uuid
import json
from pathlib import Path
from fastapi import APIRouter, File, HTTPException, UploadFile
import aiofiles

from app.config import UPLOAD_DIR
from app.services.file_parser import parse_file
from app.services.qdrant_service import QdrantService
import uuid
from app.services.document_service import document_service
from app.services.document_repository import DocumentModel

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        import uuid as uuid_module
        import json
        from pathlib import Path
        from app.services.parser import DocumentParser
        from app.services.graph_service.config import get_driver
        from app.services.graph_service.graph_db import GraphDB
        from app.services.timeweb_ai import get_ai_answer
        from app.services.qdrant_service import QdrantService
        from app.services.s3_service import s3_service
        from app.services.document_repository import DocumentRepository, DocumentModel
        
        file_id = uuid_module.uuid4()
        safe_filename = f"{file_id}_{file.filename or 'unknown'}"
        file_path = UPLOAD_DIR / safe_filename
        
        # 1. Сохраняем оригинальный файл временно
        async with aiofiles.open(file_path, 'wb') as f:
            while chunk := await file.read(1024 * 1024):
                await f.write(chunk)
        
        logger.info(f"✅ Файл сохранен: {safe_filename}")
        
        # 2. Извлекаем текст
        text_content = None
        metadata = None
        
        try:
            from app.services.file_parser import parse_file
            parsed = parse_file(str(file_path))
            text_content = parsed['text']
            metadata = parsed.get('metadata', {})
            logger.info(f"✅ Текст извлечен: {len(text_content or '')} символов")
        except Exception as parse_error:
            logger.warning(f"⚠️ Не удалось извлечь текст: {parse_error}")
            raise HTTPException(status_code=400, detail=f"Ошибка парсинга файла: {parse_error}")
        
        if not text_content or len(text_content.strip()) < 100:
            raise HTTPException(status_code=400, detail="Файл слишком короткий или пустой")
        
        # 3. Создаём запись в БД (status=uploading)
        s3_key = f"documents/{file_id}/{file.filename or 'unknown'}"
        document = DocumentModel(
            id=file_id,
            original_name=file.filename or 'unknown',
            s3_key=s3_key,
            file_size=file.size or 0,
            mime_type=file.content_type,
            status="uploading",
            metadata=metadata or {},
        )
        await DocumentRepository.create(document)
        
        # 4. Загружаем файл в S3
        try:
            await s3_service.upload_file(str(file_path), s3_key, content_type=file.content_type)
            logger.info(f"✅ Файл загружен в S3: {s3_key}")
        except Exception as s3_error:
            logger.error(f" Ошибка загрузки в S3: {s3_error}")
            await DocumentRepository.update_status(file_id, "failed", str(s3_error))
            raise HTTPException(status_code=500, detail="Ошибка загрузки файла в хранилище")
        
        # 5. Обновляем статус на processing
        await DocumentRepository.update_status(file_id, "processing")
        
        # 6. Формируем метаданные для парсера
        doc_metadata = {
            "doc_id": str(file_id),
            "title": metadata.get('title', file.filename or 'Unknown'),
            "year": metadata.get('year'),
            "authors": metadata.get('authors', []),
            "file_path": str(file_path),
            "s3_key": s3_key,
            "file_url": await s3_service.get_presigned_url(s3_key),  # Получаем URL
        }
        
        # 7. Запускаем парсер
        parse_result = None
        try:
            driver = get_driver()
            db = GraphDB(driver)
            qdrant_service = QdrantService()
            
            async def llm_client(prompt: str) -> str:
                return await get_ai_answer(question=prompt, max_retries=3, json_mode=True)
            
            parser = DocumentParser(db, llm_client, qdrant_service=qdrant_service, max_concurrent=3)
            
            logger.info(f"🔍 Запуск парсинга документа {file_id}...")
            parse_result = await parser.parse_document(text_content, doc_metadata)
            
            logger.info(f"✅ Документ обработан: {parse_result['chunks_successful']}/{parse_result['chunks_processed']} чанков")
            
            # 8. Обновляем статистику в БД
            await DocumentRepository.update_stats(
                file_id,
                parse_result['chunks_successful'],
                parse_result['nodes_created'],
                parse_result['edges_created'],
            )
            
            # 9. Отмечаем как готовый
            await DocumentRepository.update_status(file_id, "ready")
            
            db.close()
            
        except Exception as parse_error:
            logger.error(f"❌ Критическая ошибка парсинга: {parse_error}", exc_info=True)
            await DocumentRepository.update_status(file_id, "failed", str(parse_error))
            parse_result = {
                "doc_id": str(file_id),
                "chunks_processed": 0,
                "chunks_successful": 0,
                "chunks_failed": 0,
                "nodes_created": 0,
                "edges_created": 0,
                "chunks_data": [],
                "errors": [{"error": f"Критическая ошибка: {parse_error}"}],
            }
        
        # 10. Сохраняем JSON-отчёт
        json_filename = f"{file_id}_parsed.json"
        json_file_path = UPLOAD_DIR / json_filename
        
        output_json = {
            "doc_id": str(file_id),
            "filename": file.filename,
            "s3_key": s3_key,
            "file_url": doc_metadata["file_url"],
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
        
        # 11. Уведомляем клиентов через WebSocket
        from app.socketio_app import sio
        await sio.emit('document_status_update', {
            'doc_id': str(file_id),
            'status': 'ready',
            'original_name': file.filename,
            'chunks_count': parse_result['chunks_successful'],
            'nodes_count': parse_result['nodes_created'],
            'edges_count': parse_result['edges_created'],
        })
        
        # 12. Формируем ответ
        response = {
            "status": "ok" if parse_result["chunks_failed"] == 0 else "partial",
            "file_id": str(file_id),
            "filename": file.filename,
            "s3_key": s3_key,
            "file_url": doc_metadata["file_url"],
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

# ============================================================
# ДОКУМЕНТЫ API
# ============================================================

@router.get("/documents")
async def list_documents():
    """Получить список всех документов."""
    try:
        from app.services.document_repository import DocumentRepository
        
        documents = await DocumentRepository.list_all()
        
        result = []
        for doc in documents:
            # Получаем presigned URL
            try:
                from app.services.s3_service import s3_service
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
        
        return {"documents": result}
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения списка документов: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Ошибка получения списка документов")



