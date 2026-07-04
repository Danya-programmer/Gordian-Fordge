"""
Бизнес-логика для работы с документами.
Координирует загрузку, обработку и удаление.
"""
import logging
import uuid
from pathlib import Path
from typing import Optional

from app.services.s3_service import s3_service
from app.services.document_repository import DocumentRepository, DocumentModel
from app.config import UPLOAD_DIR

logger = logging.getLogger(__name__)


class DocumentService:
    """Сервис для управления документами."""
    
    def __init__(self):
        self.s3 = s3_service
        self.repo = DocumentRepository()
    
    async def create_document(
        self,
        file_path: Path,
        original_name: str,
        mime_type: Optional[str] = None,
        file_size: int = 0,
    ) -> uuid.UUID:
        """
        Создать запись о документе и загрузить файл в S3.
        
        Returns:
            doc_id (UUID)
        """
        doc_id = uuid.uuid4()
        s3_key = f"documents/{doc_id}/{original_name}"
        
        # 1. Создать запись в БД
        document = DocumentModel(
            id=doc_id,
            original_name=original_name,
            s3_key=s3_key,
            file_size=file_size,
            mime_type=mime_type,
            status="uploading",
        )
        await self.repo.create(document)
        
        # 2. Загрузить файл в S3
        await self.s3.upload_file(
            str(file_path),
            s3_key,
            content_type=mime_type,
        )
        
        # 3. Обновить статус
        await self.repo.update_status(doc_id, "processing")
        
        logger.info(f"✅ Документ создан: {doc_id}, файл загружен в S3")
        return doc_id
    
    async def replace_document(
        self,
        doc_id: uuid.UUID,
        new_file_path: Path,
        new_original_name: str,
        mime_type: Optional[str] = None,
        file_size: int = 0,
    ) -> bool:
        """
        Заменить файл документа.
        Удаляет старый файл из S3, загружает новый.
        doc_id остаётся тем же.
        """
        # 1. Получить текущий документ
        document = await self.repo.get_by_id(doc_id)
        if not document:
            raise ValueError(f"Документ {doc_id} не найден")
        
        old_s3_key = document.s3_key
        new_s3_key = f"documents/{doc_id}/{new_original_name}"
        
        # 2. Обновить статус
        await self.repo.update_status(doc_id, "processing")
        
        # 3. Удалить старый файл из S3
        await self.s3.delete_file(old_s3_key)
        
        # 4. Загрузить новый файл
        await self.s3.upload_file(
            str(new_file_path),
            new_s3_key,
            content_type=mime_type,
        )
        
        # 5. Обновить метаданные в БД
        async with self.repo.session_maker() as session:
            from sqlalchemy import update
            from datetime import datetime
            await session.execute(
                update(DocumentModel)
                .where(DocumentModel.id == doc_id)
                .values(
                    original_name=new_original_name,
                    s3_key=new_s3_key,
                    file_size=file_size,
                    mime_type=mime_type,
                    status="processing",
                    error_message=None,
                    chunks_count=0,
                    nodes_count=0,
                    edges_count=0,
                    processed_at=None,
                    updated_at=datetime.utcnow(),
                )
            )
            await session.commit()
        
        logger.info(f"✅ Документ {doc_id} заменён")
        return True
    
    async def get_document(self, doc_id: uuid.UUID) -> Optional[DocumentModel]:
        """Получить документ по ID."""
        return await self.repo.get_by_id(doc_id)
    
    async def list_documents(self) -> list:
        """Получить список всех документов."""
        return await self.repo.list_all()
    
    async def update_document_stats(
        self,
        doc_id: uuid.UUID,
        chunks_count: int,
        nodes_count: int,
        edges_count: int,
    ):
        """Обновить статистику после обработки."""
        await self.repo.update_stats(doc_id, chunks_count, nodes_count, edges_count)
    
    async def mark_as_ready(self, doc_id: uuid.UUID):
        """Отметить документ как готовый."""
        await self.repo.update_status(doc_id, "ready")
    
    async def mark_as_failed(self, doc_id: uuid.UUID, error_message: str):
        """Отметить документ как ошибочный."""
        await self.repo.update_status(doc_id, "failed", error_message)
    
    async def get_presigned_url(self, doc_id: uuid.UUID, expiration: int = 3600) -> Optional[str]:
        """Получить временную ссылку для скачивания."""
        document = await self.repo.get_by_id(doc_id)
        if not document:
            return None
        return await self.s3.get_presigned_url(document.s3_key, expiration)


# Глобальный экземпляр
document_service = DocumentService()