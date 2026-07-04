"""
QdrantService — фабрика для работы с Qdrant.
- Создание коллекции
- Загрузка чанков
- Гибридный поиск (dense + sparse + RRF)
"""
import logging
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    SparseVectorParams,
    SparseIndexParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    MatchAny,
    Range,
    SearchRequest,
    SparseVector,
)

from app.config import QDRANT_URL, QDRANT_COLLECTION_NAME
from app.services.embeddings import get_dense_embedding, get_sparse_embedding

logger = logging.getLogger(__name__)


class QdrantService:
    """Фабрика для работы с Qdrant."""

    def __init__(self, url: str = None, collection_name: str = None):
        self.url = url or QDRANT_URL or "http://localhost:6333"
        self.collection_name = collection_name or QDRANT_COLLECTION_NAME or "scientific_chunks"
        self.client = QdrantClient(url=self.url)
        self._ensure_collection()

    def _ensure_collection(self):
        """Создаёт коллекцию, если её нет."""
        collections = self.client.get_collections().collections
        collection_names = [c.name for c in collections]
        
        if self.collection_name not in collection_names:
            logger.info(f"📦 Создание коллекции Qdrant: {self.collection_name}")
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config={
                    "dense": VectorParams(
                        size=1024,  # ✅ multilingual-e5-large = 1024
                        distance=Distance.COSINE,
                    ),
                },
                sparse_vectors_config={
                    "sparse": SparseVectorParams(
                        index=SparseIndexParams(on_disk=False),
                    ),
                },
            )
            logger.info(f"✅ Коллекция {self.collection_name} создана")
        else:
            logger.info(f"✅ Коллекция {self.collection_name} уже существует")

    def upsert_chunk(self, chunk_data: Dict[str, Any]) -> str:
        """
        Загружает один чанк в Qdrant.
        
        Args:
            chunk_data: результат _build_qdrant_payload из парсера
            
        Returns:
            point_id (UUID)
        """
        point_id = chunk_data["id"]
        text = chunk_data["payload"]["text"]
        
        # Генерация эмбеддингов
        dense = get_dense_embedding(text, is_query=False)
        sparse = get_sparse_embedding(text)
        
        # Формирование точки
        point = PointStruct(
            id=point_id,
            vector={
                "dense": dense,
                "sparse": SparseVector(
                    indices=sparse["indices"],
                    values=sparse["values"],
                ),
            },
            payload=chunk_data["payload"],
        )
        
        # Загрузка в Qdrant
        self.client.upsert(
            collection_name=self.collection_name,
            points=[point],
        )
        
        return point_id

    def upsert_chunks_batch(self, chunks_data: List[Dict[str, Any]]) -> List[str]:
        """
        Batch-загрузка чанков (быстрее для больших объёмов).
        """
        if not chunks_data:
            return []
        
        # Генерация эмбеддингов батчем
        texts = [c["payload"]["text"] for c in chunks_data]
        
        from app.services.embeddings import get_dense_embeddings_batch, get_sparse_embeddings_batch
        dense_batch = get_dense_embeddings_batch(texts, is_query=False)
        sparse_batch = get_sparse_embeddings_batch(texts)
        
        # Формирование точек
        points = []
        point_ids = []
        for i, chunk_data in enumerate(chunks_data):
            point_id = chunk_data["id"]
            point_ids.append(point_id)
            
            point = PointStruct(
                id=point_id,
                vector={
                    "dense": dense_batch[i],
                    "sparse": SparseVector(
                        indices=sparse_batch[i]["indices"],
                        values=sparse_batch[i]["values"],
                    ),
                },
                payload=chunk_data["payload"],
            )
            points.append(point)
        
        # Batch upsert
        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
        )
        
        logger.info(f"✅ Загружено {len(points)} чанков в Qdrant")
        return point_ids

    def hybrid_search(
        self,
        query: str,
        limit: int = 10,
        doc_id_filter: Optional[str] = None,
        materials_filter: Optional[List[str]] = None,
        processes_filter: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Гибридный поиск: dense + sparse + RRF.
        
        Args:
            query: текст запроса
            limit: количество результатов
            doc_id_filter: фильтр по doc_id (если есть точные сущности из Neo4j)
            materials_filter: фильтр по материалам
            processes_filter: фильтр по процессам
            
        Returns:
            список результатов с payload и score
        """
        # Генерация эмбеддингов запроса
        dense_query = get_dense_embedding(query, is_query=True)
        sparse_query = get_sparse_embedding(query)
        
        # Формирование фильтра
        filter_conditions = []
        if doc_id_filter:
            filter_conditions.append(
                FieldCondition(key="doc_id", match=MatchValue(value=doc_id_filter))
            )
        if materials_filter:
            filter_conditions.append(
                FieldCondition(key="materials", match=MatchAny(any=materials_filter))
            )
        if processes_filter:
            filter_conditions.append(
                FieldCondition(key="processes", match=MatchAny(any=processes_filter))
            )
        
        search_filter = Filter(must=filter_conditions) if filter_conditions else None
        
        # Поиск по dense
        dense_results = self.client.search(
            collection_name=self.collection_name,
            query_vector=("dense", dense_query),
            limit=limit * 2,  # Берём с запасом для RRF
            query_filter=search_filter,
        )
        
        # Поиск по sparse
        sparse_results = self.client.search(
            collection_name=self.collection_name,
            query_vector=("sparse", SparseVector(
                indices=sparse_query["indices"],
                values=sparse_query["values"],
            )),
            limit=limit * 2,
            query_filter=search_filter,
        )
        
        # RRF (Reciprocal Rank Fusion)
        return self._rrf_fusion(dense_results, sparse_results, limit)

    def _rrf_fusion(self, dense_results, sparse_results, limit: int) -> List[Dict[str, Any]]:
        """
        Reciprocal Rank Fusion — объединение результатов dense и sparse поиска.
        """
        from collections import defaultdict
        
        scores = defaultdict(float)
        results_map = {}
        
        # RRF формула: score = sum(1 / (k + rank))
        # k обычно = 60
        k = 60
        
        for rank, result in enumerate(dense_results, start=1):
            point_id = result.id
            scores[point_id] += 1.0 / (k + rank)
            results_map[point_id] = result
        
        for rank, result in enumerate(sparse_results, start=1):
            point_id = result.id
            scores[point_id] += 1.0 / (k + rank)
            results_map[point_id] = result
        
        # Сортировка по итоговому score
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        
        # Формирование результатов
        final_results = []
        for point_id in sorted_ids[:limit]:
            result = results_map[point_id]
            final_results.append({
                "id": point_id,
                "score": scores[point_id],
                "payload": result.payload,
            })
        
        return final_results

    def get_collection_stats(self) -> Dict[str, Any]:
        """Статистика коллекции."""
        info = self.client.get_collection(self.collection_name)
        return {
            "points_count": info.points_count,
            "vectors_count": info.vectors_count,
            "status": info.status,
        }