"""Главный сервис поиска."""
import logging
import time
from typing import Dict, Any, List, Optional
from app.services.search_service.config import config
from app.services.search_service.query_parser import parse_query
from app.services.search_service.search_router import choose_strategy
from app.services.qdrant_service import QdrantService
from app.services.graph_service.graph_db import GraphDB
from app.services.timeweb_ai import get_ai_answer

logger = logging.getLogger(__name__)


class SearchService:
    """Главный сервис поиска."""
    
    def __init__(self, qdrant_service: QdrantService, graph_db: GraphDB):
        self.qdrant_service = qdrant_service
        self.graph_db = graph_db
    
    async def search(self, query: str) -> Dict[str, Any]:
        """Выполняет поиск по запросу."""
        start_time = time.time()
        debug_info = {} if config.RETURN_DEBUG_INFO else None
        
        # ШАГ 0: SEMANTIC ANCHOR
        anchor = None
        if config.ENABLE_SEMANTIC_ANCHOR:
            anchor_start = time.time()
            anchor = await self._find_semantic_anchor(query)
            if anchor:
                logger.info(f"🎯 Найден якорь: score={anchor['score']:.3f}")
                if config.LOG_TIMING and debug_info is not None:
                    debug_info["anchor_search_time"] = time.time() - anchor_start
        
        # ШАГ 1: PARSE QUERY
        parse_start = time.time()
        anchor_entities = anchor["entities"] if anchor else None
        parsed_query = await parse_query(query, anchor_entities=anchor_entities)
        
        if config.LOG_TIMING and debug_info is not None:
            debug_info["parse_time"] = time.time() - parse_start
        
        # ШАГ 2: CHOOSE STRATEGY
        strategy = choose_strategy(parsed_query, anchor)
        
        # ШАГ 3: EXECUTE SEARCH
        search_start = time.time()
        search_results = await self._execute_search(
            strategy=strategy,
            query=query,
            parsed_query=parsed_query,
            anchor=anchor,
        )
        
        if config.LOG_TIMING and debug_info is not None:
            debug_info["search_time"] = time.time() - search_start
        
        # ШАГ 4: GENERATE ANSWER
        answer_start = time.time()
        answer = await self._generate_answer(
            query=query,
            search_results=search_results,
            anchor=anchor,
        )
        
        if config.LOG_TIMING and debug_info is not None:
            debug_info["answer_generation_time"] = time.time() - answer_start
        
        total_time = time.time() - start_time
        
        result = {
            "answer": answer["text"],
            "sources": answer["sources"],
            "strategy": strategy,
        }
        
        if config.RETURN_DEBUG_INFO and debug_info is not None:
            debug_info["total_time"] = total_time
            result["debug"] = debug_info
        
        logger.info(f"✅ Поиск завершён: стратегия={strategy}, время={total_time:.2f}с")
        return result
    
    async def _find_semantic_anchor(self, query: str) -> Optional[Dict[str, Any]]:
        """Ищет якорный чанк."""
        # ✅ УБРАН await — метод синхронный
        results = self.qdrant_service.hybrid_search(
            query=query,
            limit=config.ANCHOR_TOP_K,
        )
        
        confident_results = [
            r for r in results 
            if r.get("score", 0) >= config.ANCHOR_THRESHOLD
        ]
        
        if not confident_results:
            return None
        
        best = confident_results[0]
        payload = best["payload"]
        
        return {
            "chunk_id": best["id"],
            "text": payload.get("text", ""),
            "score": best["score"],
            "doc_id": payload.get("doc_id"),
            "entities": {
                "materials": payload.get("materials", []),
                "processes": payload.get("processes", []),
                "parameters": payload.get("parameters", []),
            },
            "authors": payload.get("authors", []),
            "title": payload.get("title", ""),
        }
    
    async def _execute_search(
        self,
        strategy: str,
        query: str,
        parsed_query: Dict[str, Any],
        anchor: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Выполняет поиск."""
        entities = parsed_query.get("entities", {})
        
        if strategy == "qdrant_only":
            # ✅ УБРАН await
            return self.qdrant_service.hybrid_search(
                query=query,
                limit=config.LLM_MAX_CONTEXT_CHUNKS,
            )
        
        elif strategy == "neo4j_then_qdrant":
            doc_ids = await self._find_docs_in_neo4j(entities)
            
            if doc_ids:
                # ✅ УБРАН await
                return self.qdrant_service.hybrid_search(
                    query=query,
                    limit=config.LLM_MAX_CONTEXT_CHUNKS,
                    doc_id_filter=doc_ids[0] if len(doc_ids) == 1 else None,
                    materials_filter=entities.get("materials", []),
                    processes_filter=entities.get("processes", []),
                )
            else:
                # ✅ УБРАН await
                return self.qdrant_service.hybrid_search(
                    query=query,
                    limit=config.LLM_MAX_CONTEXT_CHUNKS,
                )
        
        elif strategy == "graph_rag":
            logger.warning("Стратегия graph_rag пока не реализована")
            return await self._execute_search(
                strategy="neo4j_then_qdrant",
                query=query,
                parsed_query=parsed_query,
                anchor=anchor,
            )
        
        elif strategy == "param_search":
            logger.warning("Стратегия param_search пока не реализована")
            # ✅ УБРАН await
            return self.qdrant_service.hybrid_search(
                query=query,
                limit=config.LLM_MAX_CONTEXT_CHUNKS,
            )
        
        else:
            # ✅ УБРАН await
            return self.qdrant_service.hybrid_search(
                query=query,
                limit=config.LLM_MAX_CONTEXT_CHUNKS,
            )
    
    async def _find_docs_in_neo4j(self, entities: Dict[str, Any]) -> List[str]:
        """Ищет документы в Neo4j."""
        # TODO: реализовать
        return []
    
    async def _generate_answer(
        self,
        query: str,
        search_results: List[Dict[str, Any]],
        anchor: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Генерирует ответ."""
        context_chunks = []
        
        if anchor:
            context_chunks.append(
                f"🎯 НАИБОЛЕЕ РЕЛЕВАНТНЫЙ ЧАНК (score={anchor['score']:.3f}):\n"
                f"{anchor['text']}\n"
                f"Источник: {anchor.get('title', 'Unknown')}\n"
            )
        
        for i, result in enumerate(search_results[:config.LLM_MAX_CONTEXT_CHUNKS]):
            payload = result["payload"]
            context_chunks.append(
                f"ЧАНК {i+1} (score={result.get('score', 0):.3f}):\n"
                f"{payload.get('text', '')}\n"
                f"Источник: {payload.get('title', 'Unknown')}\n"
            )
        
        context = "\n".join(context_chunks)
        
        prompt = f"""
Ты — эксперт в области горно-металлургии.

ВОПРОС:
{query}

КОНТЕКСТ:
{context}

ИНСТРУКЦИИ:
1. Ответь используя ТОЛЬКО контекст.
2. Если нет ответа — скажи "Недостаточно данных".
3. Цитируй источники [Источник: название].
4. Выдели ключевые выводы.

ОТВЕТ:
"""
        
        raw_answer = await get_ai_answer(
            question=prompt,
            max_retries=2,
            json_mode=False,
            temperature=config.LLM_TEMPERATURE,
        )
        
        sources = []
        for result in search_results[:config.LLM_MAX_CONTEXT_CHUNKS]:
            payload = result["payload"]
            sources.append({
                "doc_id": payload.get("doc_id"),
                "title": payload.get("title", "Unknown"),
                "chunk_index": payload.get("chunk_index"),
                "score": result.get("score", 0),
            })
        
        return {
            "text": raw_answer,
            "sources": sources,
        }