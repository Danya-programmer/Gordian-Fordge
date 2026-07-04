"""Роутер стратегий поиска."""
import logging
from typing import Dict, Any, Optional
from app.services.search_service.config import config

logger = logging.getLogger(__name__)


def choose_strategy(
    parsed_query: Dict[str, Any],
    anchor: Optional[Dict[str, Any]] = None
) -> str:
    """Выбирает стратегию поиска."""
    
    intent = parsed_query.get("intent", "general")
    entities = parsed_query.get("entities", {})
    conditions = parsed_query.get("conditions", [])
    
    has_confident_anchor = (
        anchor is not None and 
        anchor.get("score", 0) > config.ANCHOR_CONFIDENCE_THRESHOLD
    )
    
    # Обогащаем сущности из якоря
    if anchor and "entities" in anchor:
        for key in entities:
            if key in anchor["entities"]:
                entities[key] = list(set(entities[key] + anchor["entities"][key]))
    
    has_materials = len(entities.get("materials", [])) > 0
    has_processes = len(entities.get("processes", [])) > 0
    has_experts = len(entities.get("experts", [])) > 0
    has_equipment = len(entities.get("equipment", [])) > 0
    has_any_entity = has_materials or has_processes or has_experts or has_equipment
    has_conditions = len(conditions) > 0
    
    if has_conditions:
        logger.info("🎯 Стратегия: param_search")
        return "param_search"
    
    if intent == "compare":
        logger.info("🎯 Стратегия: graph_rag")
        return "graph_rag"
    
    if has_any_entity:
        logger.info(f"🎯 Стратегия: neo4j_then_qdrant")
        return "neo4j_then_qdrant"
    
    if has_confident_anchor:
        logger.info(f"🎯 Стратегия: neo4j_then_qdrant (якорь score={anchor['score']:.2f})")
        return "neo4j_then_qdrant"
    
    logger.info("🎯 Стратегия: qdrant_only")
    return "qdrant_only"