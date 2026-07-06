
# 🏗️ Gordian-Forge: GraphRAG-система для научного поиска

> **Интеллектуальный поиск по научным публикациям в области горно-металлургии.**  
> Хакатон ПАО «ГМК Норильский никель» 2026 — **топ-10 из 180 команд** 🏆

---

## 📖 О проекте

Gordian-Forge — это **GraphRAG-система**, которая индексирует научные статьи, строит граф знаний и отвечает на вопросы пользователей с точным цитированием источников.

**Как это работает:**
1. Пользователь загружает научную статью (PDF/DOCX)
2. Система парсит документ, извлекает сущности (материалы, процессы, оборудование, эксперты) и связи между ними
3. Строит граф знаний в **Neo4j** и индексирует чанки в векторной БД **Qdrant**
4. При вопросе пользователя выполняет **гибридный поиск** и генерирует ответ со ссылками на источники

---

## 🏛️ Архитектура

```
┌─────────────┐      ┌──────────────────────────────────────┐
│   Frontend  │      │            Backend (FastAPI)         │
│  (React +   │◀────▶│  ┌──────────┐  ┌─────────────────┐  │
│  Socket.IO) │      │  │  Parser  │  │  Search Service │  │
└─────────────┘      │  └────┬─────┘  └────────┬────────┘  │
                     │       │                  │           │
                     │       ▼                  ▼           │
                     │  ┌──────────────────────────────┐   │
                     │  │  LLM (Qwen 3.5 Plus API)     │   │
                     │  └──────────────────────────────┘   │
                     └──────────────┬───────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
┌──────────────┐          ┌──────────────────┐        ┌──────────────┐
│  PostgreSQL  │          │      Qdrant      │        │    Neo4j     │
│ (метаданные) │          │ (dense + sparse) │        │  (граф)      │
└──────────────┘          └──────────────────┘        └──────────────┘
        ▲
        │
┌──────────────┐
│  S3 TimeWeb  │
│  (файлы)     │
└──────────────┘
```

---

## 🔑 Ключевые фичи

### 🔍 Гибридный поиск (Dense + Sparse + RRF)

| Компонент | Модель | Назначение |
|-----------|--------|------------|
| **Dense** | `intfloat/multilingual-e5-large` (1024-dim) | Семантический поиск |
| **Sparse** | `Qdrant/bm42` (SPLADE-подобная) | Лексический поиск по терминам |
| **Fusion** | RRF (k=60) | Объединение результатов |

### ⚓ Semantic Anchoring (авторская техника)

Перед основным поиском находится чанк с **косинусным сходством > 0.85**, из него извлекаются сущности и используются для обогащения запроса.

**Пример:**
```
Запрос: "Как Коржаков очищал сточные воды?"
    ↓
Якорь найден: чанк про Коржакова (score=0.91)
    ↓
Извлечены сущности: {эксперт: "Коржаков", процесс: "электроэкстракция"}
    ↓
Поиск обогащён через граф Neo4j
    ↓
Точный ответ с цитированием источников
```

### 🎯 Адаптивный роутер стратегий

LLM парсит запрос и выбирает одну из 4 стратегий:

| Стратегия | Когда используется |
|-----------|---------------------|
| `qdrant_only` | Общие семантические запросы |
| `neo4j_then_qdrant` | Запросы с конкретными сущностями |
| `graph_rag` | Сравнительные запросы |
| `param_search` | Числовые условия («температура > 500K») |

### 🛡️ Защита от галлюцинаций LLM

1. Строгий промпт с запретом додумывать факты
2. Пониженная температура (0.2)
3. Дедупликация источников по `doc_id`
4. Обязательное цитирование в формате `[Источник N]`
5. Фильтрация источников без названия

---

## 🛠️ Стек технологий

| Слой | Технологии |
|------|-----------|
| **ML / NLP** | PyTorch, Sentence-Transformers, FastEmbed, HuggingFace |
| **LLM** | Qwen 3.5 Plus API (TimeWeb Cloud AI) |
| **Векторная БД** | Qdrant 1.18.2 (гибридный поиск) |
| **Граф** | Neo4j 5.26 Community + APOC |
| **Реляционная БД** | PostgreSQL 16 |
| **Backend** | Python 3.12, FastAPI, Socket.IO, SQLAlchemy async |
| **Хранилище** | TimeWeb Object Storage (S3) |
| **Frontend** | React, TypeScript, Vite, Socket.IO-client |
| **Инфраструктура** | Docker Compose, Nginx, Let's Encrypt |
| **Парсинг** | pdfplumber, python-docx, LangChain TextSplitters |

---

## 📁 Структура проекта

```
gordian-forge/
├── backend/
│   ├── app/
│   │   ├── services/
│   │   │   ├── embeddings.py           # Dense + sparse эмбеддинги
│   │   │   ├── qdrant_service.py       # Гибридный поиск + RRF
│   │   │   ├── parser.py               # Парсинг документов
│   │   │   ├── s3_service.py           # Работа с S3
│   │   │   ├── document_service.py     # CRUD документов
│   │   │   └── search_service/         # Поисковый pipeline
│   │   │       ├── config.py
│   │   │       ├── query_parser.py     # LLM-парсер запросов
│   │   │       ├── search_router.py    # Роутер стратегий
│   │   │       └── search_service.py   # Оркестратор поиска
│   │   ├── graph_service/              # Работа с Neo4j
│   │   ├── routes.py                   # REST API
│   │   └── socket_handlers.py          # WebSocket
│   ├── migrations/init.sql
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/features/
│   │   ├── upload/                     # Загрузка файлов
│   │   └── documents/                  # Список документов
│   ├── Dockerfile
│   └── package.json
├── nginx/
│   └── nginx.conf                      # Продакшен-конфиг
├── docker-compose.yml                  # Development
├── docker-compose.prod.yml             # Production
└── README.md
```

---

## 🚀 Быстрый старт

### Требования
- Docker & Docker Compose
- 8GB+ RAM (для моделей эмбеддингов)
- S3-ключи (TimeWeb или MinIO)

### Запуск в режиме разработки

```bash
# 1. Клонировать репозиторий
git clone https://github.com/Danya-programmer/Gordian-Forge.git
cd Gordian-Forge

# 2. Настроить окружение
cp backend/.env.example backend/.env
# Указать S3-ключи в backend/.env

# 3. Запустить все сервисы
docker compose up -d --build

# 4. Проверить логи
docker compose logs -f backend

# 5. Открыть в браузере:
# Frontend: http://localhost:3000
# API docs: http://localhost:8000/docs
# Neo4j:    http://localhost:7474
# Qdrant:   http://localhost:6333/dashboard
```

### Продакшен-деплой

```bash
# 1. Получить SSL-сертификат (нужен домен)
chmod +x init-letsencrypt.sh
./init-letsencrypt.sh

# 2. Запустить продакшен-стек
docker compose -f docker-compose.prod.yml up -d --build

# 3. Собрать и скопировать фронтенд
cd frontend && npm run build && cd ..
docker cp frontend/dist gordian-nginx:/usr/share/nginx/html
```

---

## 📡 API

### REST endpoints

| Метод | Endpoint | Описание |
|-------|----------|----------|
| `POST` | `/upload` | Загрузить документ (multipart) |
| `GET` | `/documents` | Список всех документов |
| `GET` | `/documents/{id}` | Детали документа |
| `GET` | `/documents/{id}/url` | Presigned URL для скачивания |

### WebSocket события

**Клиент → Сервер:**
```javascript
socket.emit('user_message', { text: 'Ваш вопрос' });
socket.emit('get_documents');
```

**Сервер → Клиент:**
```javascript
socket.on('ai_thinking', () => { /* AI думает */ });
socket.on('ai_answer', (data) => {
  // data.answer    — сгенерированный ответ
  // data.sources   — список источников с URL
  // data.strategy  — использованная стратегия
});
socket.on('documents_list', (data) => { /* список документов */ });
socket.on('document_status_update', (update) => {
  // update.status: uploading | processing | ready | failed
});
```

---

## 📊 Производительность

| Метрика | Значение |
|---------|----------|
| Обработка документа | 20-40 секунд |
| Поиск по базе | < 1 секунды |
| Генерация ответа | 5-10 секунд |
| Протестировано на | 50+ научных статьях |
| Проиндексировано чанков | ~1000 |
| Узлов графа знаний | ~3000 |
| Результат хакатона | **Топ-10 из 180 команд** 🏆 |

---



## 📬 Контакты

📧 danbgavindv90835@gmail.com  
📧 kotof.danila2016@yandex.ru

---

<div align="center">

**Сделано на хакатоне «Норникеля» 2026**

⭐ Поставьте звезду, если проект оказался полезным!

</div>
