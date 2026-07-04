"""
Repository для работы с таблицей documents.
SQLAlchemy 2.0+ стиль с аннотациями типов.
"""
import logging
import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

from app.config import DATABASE_URL

logger = logging.getLogger(__name__)

# Движок БД
engine = create_async_engine(DATABASE_URL, echo=False)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession)


# ✅ SQLAlchemy 2.0+ стиль — DeclarativeBase БЕЗ аргументов
class Base(DeclarativeBase):
    pass


class DocumentModel(Base):
    """Модель документа."""
    __tablename__ = "documents"
    
    # ✅ Все поля имеют аннотации Mapped[type]
    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    original_name: Mapped[str] = mapped_column(nullable=False)
    s3_key: Mapped[str] = mapped_column(unique=True, nullable=False)
    file_size: Mapped[int] = mapped_column(default=0)
    mime_type: Mapped[Optional[str]] = mapped_column(nullable=True)
    
    status: Mapped[str] = mapped_column(default="uploading")
    error_message: Mapped[Optional[str]] = mapped_column(nullable=True)
    
    chunks_count: Mapped[int] = mapped_column(default=0)
    nodes_count: Mapped[int] = mapped_column(default=0)
    edges_count: Mapped[int] = mapped_column(default=0)
    
    file_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
    
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, 
        onupdate=datetime.utcnow
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)


class DocumentRepository:
    """CRUD операции для документов."""
    
    @staticmethod
    async def create(document: DocumentModel) -> DocumentModel:
        """Создать документ."""
        async with async_session_maker() as session:
            session.add(document)
            await session.commit()
            await session.refresh(document)
            return document
    
    @staticmethod
    async def get_by_id(doc_id: uuid.UUID) -> Optional[DocumentModel]:
        """Получить документ по ID."""
        async with async_session_maker() as session:
            result = await session.execute(
                select(DocumentModel).where(DocumentModel.id == doc_id)
            )
            return result.scalar_one_or_none()
    
    @staticmethod
    async def list_all() -> List[DocumentModel]:
        """Получить все документы."""
        async with async_session_maker() as session:
            result = await session.execute(
                select(DocumentModel).order_by(DocumentModel.created_at.desc())
            )
            return result.scalars().all()
    
    @staticmethod
    async def update_status(
        doc_id: uuid.UUID,
        status: str,
        error_message: Optional[str] = None,
    ) -> Optional[DocumentModel]:
        """Обновить статус."""
        async with async_session_maker() as session:
            update_data = {"status": status, "updated_at": datetime.utcnow()}
            if error_message is not None:
                update_data["error_message"] = error_message
            if status == "ready":
                update_data["processed_at"] = datetime.utcnow()
            
            await session.execute(
                update(DocumentModel).where(DocumentModel.id == doc_id).values(**update_data)
            )
            await session.commit()
            return await DocumentRepository.get_by_id(doc_id)
    
    @staticmethod
    async def update_stats(
        doc_id: uuid.UUID,
        chunks_count: int,
        nodes_count: int,
        edges_count: int,
    ) -> Optional[DocumentModel]:
        """Обновить статистику."""
        async with async_session_maker() as session:
            await session.execute(
                update(DocumentModel)
                .where(DocumentModel.id == doc_id)
                .values(
                    chunks_count=chunks_count,
                    nodes_count=nodes_count,
                    edges_count=edges_count,
                    updated_at=datetime.utcnow(),
                )
            )
            await session.commit()
            return await DocumentRepository.get_by_id(doc_id)


# Глобальный экземпляр
document_repository = DocumentRepository()