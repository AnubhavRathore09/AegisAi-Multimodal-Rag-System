# 🚀 AegisAI: Adaptive Multimodal RAG System

![License](https://img.shields.io/badge/License-MIT-blue.svg)
![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?logo=fastapi&logoColor=white)
![Groq](https://img.shields.io/badge/Groq-LLM-orange)
![Redis](https://img.shields.io/badge/Redis-Caching-red)
![Deploy](https://img.shields.io/badge/Deploy-Production-green)

A production-grade adaptive multimodal Retrieval-Augmented Generation system designed for intelligent, context-aware, and scalable AI applications.

---

## 🧠 Overview

AegisAI is an advanced GenAI system that dynamically selects the optimal processing pipeline based on user intent. It combines retrieval, memory, and direct LLM reasoning to deliver accurate, grounded, and efficient responses across multiple modalities.

---

## ✨ Features

- Adaptive query routing: direct, rag, memory, multimodal
- Multimodal input support: text, documents, images, voice
- FAISS-based retrieval with confidence-aware fallback
- MongoDB-backed conversational memory
- OCR pipeline for image understanding
- Voice-to-text processing
- Query correction and rewriting
- Streaming chat responses
- Redis-based caching with fallback
- Evaluation pipeline for RAG quality
- Structured logging and observability
- Rate limiting for production reliability
- Async-ready FastAPI backend

---

## 🏗️ Architecture

```
User Query
   ↓
Query Router
   ├── direct → LLM
   ├── rag → Retriever → Context → LLM
   ├── memory → History → LLM
   └── multimodal → OCR / Voice → Router → LLM
   ↓
Response + Logging + Memory + Cache
```

---

## 🛠️ Tech Stack

- Python
- FastAPI
- Groq API
- FAISS
- MongoDB
- Redis
- Tesseract OCR
- Uvicorn
- NumPy

---

## 📂 Project Structure

```
AegisAI/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── schemas.py
│   ├── evaluate_batch.py
│   ├── routes/
│   │   ├── chat.py
│   │   ├── upload.py
│   │   └── compat.py
│   └── services/
│       ├── rag.py
│       ├── router.py
│       ├── query_processing.py
│       ├── vector_store.py
│       ├── memory.py
│       ├── documents.py
│       ├── ocr.py
│       ├── speech.py
│       ├── llm.py
│       ├── cache.py
│       ├── evaluator.py
│       ├── rate_limiter.py
│       └── logging_service.py
├── frontend/
├── storage/
├── requirements.txt
└── README.md
```

---

## ⚙️ Installation

```bash
git clone https://github.com/your-username/AegisAI.git
cd AegisAI
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 🔐 Environment Variables

```env
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_VISION_MODEL=meta-llama/llama-4-scout-17b-16e-instruct
GROQ_SPEECH_MODEL=whisper-large-v3-turbo

MONGODB_URI=mongodb://localhost:27017
MONGODB_DB=aegisai

REDIS_URL=redis://localhost:6379/0

CORS_ORIGINS=*
TESSERACT_CMD=
RATE_LIMIT_REQUESTS=10
RATE_LIMIT_WINDOW_SECONDS=60
ROUTER_USE_LLM=true
ROUTER_LLM_CONFIDENCE_THRESHOLD=0.55
```

---

## 🚀 Running the Application

```bash
python3 -m uvicorn src.main:app --reload
```

Open:
- http://127.0.0.1:8000
- http://127.0.0.1:8000/docs

---

## 🔌 API Endpoints

### Core
- POST /api/chat
- POST /api/stream
- POST /api/upload
- GET /api/health

### History
- GET /api/history
- GET /api/history/{session_id}
- DELETE /api/history/{session_id}

### Voice
- POST /voice/voice-chat

### Evaluation
- POST /api/evaluate

---

## 📊 Evaluation

Metrics supported:
- Precision
- Recall
- Context relevance
- Answer correctness

Run batch evaluation:

```bash
python3 -m app.evaluate_batch eval_samples.json
```

---

## 🛡️ Adaptive Routing

The system dynamically selects execution flow:
- direct → simple queries
- rag → retrieval-based queries
- memory → conversational queries
- multimodal → OCR, voice, file-based queries

---

## ⚡ Production Notes

- Use Redis for distributed caching
- Use MongoDB Atlas for persistence
- Configure proper CORS settings
- Deploy behind reverse proxy
- Enable HTTPS
- Monitor logs and latency
- Configure OCR dependencies properly

---

## 🎯 Use Cases

- Document question answering
- Multimodal assistants
- Enterprise knowledge search
- Voice-enabled AI systems
- Context-aware conversational AI

---

## 📌 Future Improvements

- Model-based reranking
- Advanced evaluation metrics
- Admin analytics dashboard
- Background ingestion workers
- Multi-user isolation

---

## 👨‍💻 Author

Anubhav Rathore

---

## 📜 License

MIT License
