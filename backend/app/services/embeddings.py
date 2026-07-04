import logging
import os
from typing import List, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

# Путь к кэшу HuggingFace
HF_CACHE_DIR = os.getenv("HF_HOME", "/root/.cache/huggingface")

# ============================================================
# DENSE EMBEDDINGS (multilingual-e5-large)
# ============================================================

_dense_model = None

def get_dense_model():
    """Ленивая загрузка модели с проверкой кэша."""
    global _dense_model
    if _dense_model is None:
        from sentence_transformers import SentenceTransformer
        
        model_name = "intfloat/multilingual-e5-large"
        cache_path = Path(HF_CACHE_DIR) / "hub"
        
        # Проверяем, есть ли модель в кэше
        model_cached = False
        if cache_path.exists():
            for item in cache_path.iterdir():
                if item.is_dir() and "multilingual-e5-large" in item.name:
                    model_cached = True
                    logger.info(f"✅ Модель найдена в кэше: {item}")
                    break
        
        if model_cached:
            logger.info(f"📦 Загрузка модели из кэша: {model_name}")
        else:
            logger.info(f"📥 Модель не найдена в кэше. Скачивание: {model_name}")
            logger.info(f"   Кэш: {HF_CACHE_DIR}")
            logger.info(f"   Размер модели: ~2.5 ГБ")
            logger.info(f"   Это займёт 2-5 минут при первом запуске...")
        
        _dense_model = SentenceTransformer(
            model_name,
            cache_folder=HF_CACHE_DIR,
        )
        
        logger.info(f"✅ Модель dense загружена: {model_name}")
        # ✅ ИСПРАВЛЕНО: используем новый метод
        try:
            dim = _dense_model.get_embedding_dimension()
        except AttributeError:
            dim = _dense_model.get_sentence_embedding_dimension()
        logger.info(f"   Размер вектора: {dim}")
    
    return _dense_model


def get_dense_embedding(text: str, is_query: bool = False) -> List[float]:
    """Генерирует dense эмбеддинг."""
    model = get_dense_model()
    prefix = "query: " if is_query else "passage: "
    text_with_prefix = f"{prefix}{text}"
    
    embedding = model.encode(
        text_with_prefix,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return embedding.tolist()


def get_dense_embeddings_batch(texts: List[str], is_query: bool = False) -> List[List[float]]:
    """Batch-генерация dense эмбеддингов."""
    model = get_dense_model()
    prefix = "query: " if is_query else "passage: "
    texts_with_prefix = [f"{prefix}{t}" for t in texts]
    
    embeddings = model.encode(
        texts_with_prefix,
        normalize_embeddings=True,
        show_progress_bar=False,
        batch_size=32,
    )
    return embeddings.tolist()


# ============================================================
# SPARSE EMBEDDINGS (Qdrant/bm42 — рекомендуемая модель)
# ============================================================

_sparse_model = None

def get_sparse_model():
    """
    Ленивая загрузка sparse модели.
    Используем Qdrant/bm42 — современная модель от Qdrant.
    """
    global _sparse_model
    if _sparse_model is None:
        from fastembed import SparseTextEmbedding
        
        # ✅ ИСПРАВЛЕНО: используем поддерживаемую модель от Qdrant
        model_name = "Qdrant/bm42-all-minilm-l6-v2-attentions"
        
        logger.info(f"📦 Загрузка модели sparse: {model_name}")
        logger.info(f"   Кэш: {HF_CACHE_DIR}")
        
        _sparse_model = SparseTextEmbedding(model_name=model_name)
        
        logger.info(f"✅ Модель sparse загружена: {model_name}")
    
    return _sparse_model


def get_sparse_embedding(text: str) -> Dict[str, Any]:
    """Генерирует sparse эмбеддинг."""
    model = get_sparse_model()
    sparse_embeddings = list(model.embed(text))
    
    if not sparse_embeddings:
        return {"indices": [], "values": []}
    
    sparse = sparse_embeddings[0]
    return {
        "indices": sparse.indices.tolist(),
        "values": sparse.values.tolist(),
    }


def get_sparse_embeddings_batch(texts: List[str]) -> List[Dict[str, Any]]:
    """Batch-генерация sparse эмбеддингов."""
    model = get_sparse_model()
    sparse_embeddings = list(model.embed(texts))
    
    results = []
    for sparse in sparse_embeddings:
        results.append({
            "indices": sparse.indices.tolist(),
            "values": sparse.values.tolist(),
        })
    return results


# ============================================================
# УДОБНЫЙ ИНТЕРФЕЙС
# ============================================================

def get_hybrid_embeddings(text: str, is_query: bool = False) -> Dict[str, Any]:
    """Возвращает оба эмбеддинга сразу."""
    dense = get_dense_embedding(text, is_query=is_query)
    sparse = get_sparse_embedding(text)
    
    return {
        "dense": dense,
        "sparse": sparse,
    }