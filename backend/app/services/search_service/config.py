"""Конфигурация сервиса поиска."""
from dataclasses import dataclass


@dataclass
class SearchConfig:
    """Конфигурация поиска."""
    
    # SEMANTIC ANCHOR
    ENABLE_SEMANTIC_ANCHOR: bool = True
    ANCHOR_THRESHOLD: float = 0.85
    ANCHOR_TOP_K: int = 3
    ANCHOR_CONFIDENCE_THRESHOLD: float = 0.88
    
    # LLM ПАРСЕР
    ALWAYS_USE_LLM_PARSER: bool = True
    PARSER_TIMEOUT: int = 30
    PARSER_MAX_RETRIES: int = 2
    
    # QDRANT
    QDRANT_SEARCH_LIMIT_MULTIPLIER: int = 2
    QDRANT_MIN_SCORE: float = 0.3
    
    # NEO4J
    NEO4J_MAX_PATH_LENGTH: int = 3
    
    # RRF
    RRF_K: int = 60
    
    # LLM ГЕНЕРАЦИЯ
    LLM_MAX_CONTEXT_CHUNKS: int = 10
    LLM_MAX_TOKENS: int = 2000
    LLM_TEMPERATURE: float = 0.4
    
    # ЛОГИРОВАНИЕ
    RETURN_DEBUG_INFO: bool = True
    LOG_TIMING: bool = True


# Глобальный экземпляр
config = SearchConfig()