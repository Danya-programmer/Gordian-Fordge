"""Парсер запросов пользователя."""
import json
import logging
from typing import Dict, Any, List, Optional
from app.services.timeweb_ai import get_ai_answer
from app.services.search_service.config import config

logger = logging.getLogger(__name__)

PARSER_PROMPT = """
Ты — парсер запросов к научной базе данных в области горно-металлургии.

Извлеки из запроса:
1. **intent** (один из): general, find_methods, find_experts, find_materials, find_equipment, compare, find_by_params
2. **entities**: {{materials: [], processes: [], equipment: [], experts: []}}
3. **conditions**: [{{name, op, value, unit}}]
4. **year_range**: {{min, max}} или null

{ANCHOR_HINT}

Запрос: {QUERY}

Верни ТОЛЬКО JSON:
{{
    "intent": "general",
    "entities": {{
        "materials": [],
        "processes": [],
        "equipment": [],
        "experts": []
    }},
    "conditions": [],
    "year_range": null
}}
"""


async def parse_query(
    query: str,
    anchor_entities: Optional[Dict[str, List[str]]] = None
) -> Dict[str, Any]:
    """Парсит запрос с помощью LLM."""
    
    anchor_hint = ""
    if anchor_entities and config.ALWAYS_USE_LLM_PARSER:
        materials = anchor_entities.get("materials", [])
        processes = anchor_entities.get("processes", [])
        authors = anchor_entities.get("authors", [])
        
        anchor_hint = f"""
 ПОДСКАЗКА: Найден документ с высоким сходством.
Сущности из него:
- Материалы: {materials if materials else "не указаны"}
- Процессы: {processes if processes else "не указаны"}
- Авторы: {authors if authors else "не указаны"}
"""
    
    prompt = PARSER_PROMPT.format(
        ANCHOR_HINT=anchor_hint,
        QUERY=query
    )
    
    try:
        raw_response = await get_ai_answer(
            question=prompt,
            max_retries=config.PARSER_MAX_RETRIES,
            json_mode=True
        )
        
        parsed = json.loads(raw_response)
        
        result = {
            "intent": parsed.get("intent", "general"),
            "entities": {
                "materials": parsed.get("entities", {}).get("materials", []),
                "processes": parsed.get("entities", {}).get("processes", []),
                "equipment": parsed.get("entities", {}).get("equipment", []),
                "experts": parsed.get("entities", {}).get("experts", []),
            },
            "conditions": parsed.get("conditions", []),
            "year_range": parsed.get("year_range"),
            "raw_llm_response": raw_response,
        }
        
        logger.info(f"🔍 Распаршен запрос: intent={result['intent']}")
        return result
        
    except Exception as e:
        logger.error(f"❌ Ошибка парсинга: {e}")
        return {
            "intent": "general",
            "entities": {"materials": [], "processes": [], "equipment": [], "experts": []},
            "conditions": [],
            "year_range": None,
            "raw_llm_response": None,
            "error": str(e),
        }