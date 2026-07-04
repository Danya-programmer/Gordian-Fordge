import json
import logging
import re
import uuid
import asyncio
from typing import List, Dict, Any, Callable, Awaitable
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.services.graph_service.graph_db import GraphDB
from app.services.graph_service.schema import VALID_NODE_TYPES, VALID_EDGE_TYPES

logger = logging.getLogger(__name__)

# ============================================================
# ПРОМПТ ДЛЯ LLM
# ============================================================
PROMPT_TEMPLATE = """
Ты — парсер научно-технических текстов. Твоя задача — извлечь сущности и связи из фрагмента текста и вернуть СТРОГИЙ JSON.

ВХОДНЫЕ ДАННЫЕ:
Текст фрагмента:
---
{chunk_text}
---

ПРАВИЛА:
1. Используй ТОЛЬКО эти типы узлов (nodes.type): {valid_node_types}
2. Используй ТОЛЬКО эти типы связей (edges.type): {valid_edge_types}
3. Атомарность: "электроэкстракция никеля" -> process: "Электроэкстракция", material: "Никель".
4. Единицы измерения: ОСТАВЛЯЙ КАК В ТЕКСТЕ. Не переводи в СИ сам (например, "50 °C" -> value: 50, unit: "°C"). Python переведет их позже.
5. ID узлов: используй простые целые числа (1, 2, 3...) в рамках этого фрагмента.
6. Параметры: если параметр имеет числовое значение (например, "температура 50 °C"), НЕ создавай для него узел parameter. Укажи его в поле params у ребра. Узел parameter создавай ТОЛЬКО если параметр упомянут абстрактно, без числа.
7. Страницы: если в тексте нет явных указаний страниц, оставь pages пустым списком [].

ФОРМАТ ОТВЕТА:
Верни ТОЛЬКО валидный JSON-объект. Без markdown-оберток (без ```json), без комментариев.
{{
  "nodes": [
    {{
      "id": 1,
      "type": "process",
      "name": "Электроэкстракция",
      "props": {{"technology": "Outokumpu"}}
    }}
  ],
  "edges": [
    {{
      "from": 1,
      "to": 2,
      "type": "uses_material",
      "pages": [],
      "params": {{
        "temperature": {{"value": 50, "unit": "°C"}}
      }}
    }}
  ]
}}
"""


class DocumentParser:
    def __init__(
        self,
        db: GraphDB,
        ai_client: Callable[[str], Awaitable[str]],
        qdrant_service: "QdrantService" = None,
        max_concurrent: int = 3,
        chunk_size: int = 1500,
        chunk_overlap: int = 150,
    ):
        self.db = db
        self.ai_client = ai_client
        self.qdrant_service = qdrant_service
        self.max_concurrent = max_concurrent

        # ✅ СПЛИТТЕР
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " "],
        )

        # ✅ ФОРМИРОВАНИЕ ПРОМПТА (через replace, чтобы не трогать {chunk_text})
        self.prompt_template = PROMPT_TEMPLATE.replace(
            "{valid_node_types}",
            ", ".join([f'"{t}"' for t in VALID_NODE_TYPES]),
        ).replace(
            "{valid_edge_types}",
            ", ".join([f'"{t}"' for t in VALID_EDGE_TYPES]),
        )

    # ------------------------------------------------------------------ #
    #  ОЧИСТКА JSON ОТ LLM
    # ------------------------------------------------------------------ #
    def _clean_llm_json(self, raw_text: str) -> dict:
        """Очистка ответа LLM от мусора, markdown и лишних запятых."""
        clean_text = re.sub(r"^```json\s*|\s*```$", "", raw_text.strip(), flags=re.MULTILINE)
        clean_text = re.sub(r"^```\s*|\s*```$", "", clean_text.strip(), flags=re.MULTILINE)
        clean_text = re.sub(r",\s*([\]}])", r"\1", clean_text)

        try:
            return json.loads(clean_text)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", clean_text)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
            return {"nodes": [], "edges": []}

    # ------------------------------------------------------------------ #
    #  ПОСТРОЕНИЕ PAYLOAD ДЛЯ QDRANT
    # ------------------------------------------------------------------ #
    def _build_qdrant_payload(
        self,
        chunk_text: str,
        doc_metadata: dict,
        chunk_index: int,
        graph_json: dict,
    ) -> dict:
        """Собирает payload для Qdrant с извлечёнными сущностями."""
        materials = list({
            n["name"] for n in graph_json.get("nodes", []) if n["type"] == "material"
        })
        processes = list({
            n["name"] for n in graph_json.get("nodes", []) if n["type"] == "process"
        })

        parameters = []
        for edge in graph_json.get("edges", []):
            for p_name, p_data in edge.get("params", {}).items():
                if isinstance(p_data, dict) and "value" in p_data:
                    parameters.append({
                        "name": p_name,
                        "value": p_data["value"],
                        "unit": p_data.get("unit", ""),
                    })

        return {
            "id": str(uuid.uuid4()),
            "vector": {
                "dense": [],  # заполнится в QdrantService
                "sparse": {"indices": [], "values": []},
            },
            "payload": {
                "text": chunk_text,
                "doc_id": doc_metadata["doc_id"],
                "title": doc_metadata.get("title", ""),
                "year": doc_metadata.get("year"),
                "authors": doc_metadata.get("authors", []),
                "chunk_index": chunk_index,
                "page": doc_metadata.get("start_page", 0),
                "file_path": doc_metadata.get("file_path", ""),
                "materials": materials,
                "processes": processes,
                "parameters": parameters,
                "global_entities": {
                    "materials": materials,
                    "processes": processes,
                },
                "created_at": "2026-07-04T12:00:00Z",
            },
        }

    # ------------------------------------------------------------------ #
    #  ОБРАБОТКА ОДНОГО ЧАНКА (с параллелизмом через semaphore)
    # ------------------------------------------------------------------ #
    async def _process_chunk(
        self,
        chunk_index: int,
        chunk_text: str,
        doc_metadata: dict,
        semaphore: asyncio.Semaphore,
    ) -> Dict[str, Any]:
        """
        Обрабатывает один чанк: вызывает LLM, пишет в Neo4j, загружает в Qdrant.
        Все ошибки ловятся внутри — функция НИКОГДА не кидает исключение наружу.
        """
        async with semaphore:
            logger.info(f"📄 Начало обработки чанка {chunk_index + 1}...")

            result = {
                "chunk_index": chunk_index,
                "chunk_text": chunk_text,
                "raw_llm_response": None,
                "parsed_graph": None,
                "nodes_created": 0,
                "edges_created": 0,
                "qdrant_loaded": False,
                "error": None,
            }

            try:
                # 1. Вызов LLM
                prompt = self.prompt_template.format(chunk_text=chunk_text)
                raw_response = await self.ai_client(prompt)
                result["raw_llm_response"] = raw_response

                # 2. Парсинг JSON
                graph_json = self._clean_llm_json(raw_response)
                result["parsed_graph"] = graph_json

                # 3. Запись в Neo4j
                if graph_json.get("nodes"):
                    stats = self.db.add(graph_json)
                    result["nodes_created"] = stats.get("nodes_created", 0)
                    result["edges_created"] = stats.get("edges_created", 0)

                # 4. Загрузка в Qdrant
                if self.qdrant_service:
                    try:
                        qdrant_payload = self._build_qdrant_payload(
                            chunk_text=chunk_text,
                            doc_metadata=doc_metadata,
                            chunk_index=chunk_index,
                            graph_json=graph_json,
                        )
                        self.qdrant_service.upsert_chunk(qdrant_payload)
                        result["qdrant_loaded"] = True
                        logger.info(f"   💾 Чанк {chunk_index + 1} загружен в Qdrant")
                    except Exception as qdrant_err:
                        logger.warning(
                            f"   ⚠️ Ошибка загрузки в Qdrant (чанк {chunk_index + 1}): {qdrant_err}"
                        )
                        # Не падаем — Qdrant опционален

                logger.info(
                    f"  ✅ Чанк {chunk_index + 1}: "
                    f"+{result['nodes_created']} узлов, "
                    f"+{result['edges_created']} ребер"
                )

            except Exception as e:
                error_msg = f"{type(e).__name__}: {str(e)}"
                logger.error(f"  ❌ Ошибка чанка {chunk_index + 1}: {error_msg}")
                result["error"] = error_msg

            return result

    # ------------------------------------------------------------------ #
    #  ГЛАВНЫЙ МЕТОД: параллельная обработка всех чанков
    # ------------------------------------------------------------------ #
    async def parse_document(self, raw_text: str, doc_metadata: dict) -> Dict[str, Any]:
        """
        Разбивает текст на чанки и обрабатывает их ПАРАЛЛЕЛЬНО.
        Никогда не падает целиком — ошибки отдельных чанков собираются в список.
        """
        chunks = self.text_splitter.split_text(raw_text)
        total_chunks = len(chunks)
        logger.info(
            f"🔍 Текст разбит на {total_chunks} чанков. "
            f"Параллелизм: {self.max_concurrent}"
        )

        semaphore = asyncio.Semaphore(self.max_concurrent)

        # Создаём задачи для всех чанков
        tasks = [
            self._process_chunk(i, chunk_text, doc_metadata, semaphore)
            for i, chunk_text in enumerate(chunks)
        ]

        # Запускаем параллельно
        results: List[Dict[str, Any]] = await asyncio.gather(*tasks)

        # Агрегация
        chunks_data = []
        errors = []
        total_nodes = 0
        total_edges = 0
        qdrant_loaded_count = 0

        for r in results:
            chunks_data.append({
                "chunk_index": r["chunk_index"],
                "chunk_text": r["chunk_text"],
                "raw_llm_response": r["raw_llm_response"],
                "parsed_graph": r["parsed_graph"],
            })

            total_nodes += r["nodes_created"]
            total_edges += r["edges_created"]
            if r["qdrant_loaded"]:
                qdrant_loaded_count += 1

            if r["error"]:
                errors.append({
                    "chunk_index": r["chunk_index"],
                    "error": r["error"],
                })

        # Сортируем по chunk_index
        chunks_data.sort(key=lambda x: x["chunk_index"])

        chunks_successful = total_chunks - len(errors)
        chunks_failed = len(errors)

        logger.info(
            f"✅ Парсинг завершён: "
            f"{chunks_successful}/{total_chunks} чанков успешно, "
            f"{qdrant_loaded_count} загружено в Qdrant. "
            f"Всего: +{total_nodes} узлов, +{total_edges} ребер"
        )

        return {
            "doc_id": doc_metadata["doc_id"],
            "chunks_processed": total_chunks,
            "chunks_successful": chunks_successful,
            "chunks_failed": chunks_failed,
            "nodes_created": total_nodes,
            "edges_created": total_edges,
            "qdrant_loaded": qdrant_loaded_count,
            "chunks_data": chunks_data,
            "errors": errors,
        }