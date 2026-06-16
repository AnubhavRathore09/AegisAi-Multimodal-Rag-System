# 🚀 AegisAI: Adaptive Multimodal RAG System

![License](https://img.shields.io/badge/License-MIT-blue.svg)
![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?logo=fastapi&logoColor=white)
![Gemini](https://img.shields.io/badge/Gemini-2.5%20Flash-4285F4?logo=google&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-Caching-red)
![Deploy](https://img.shields.io/badge/Deploy-Production-green)

AegisAI is a production-grade Adaptive Multimodal RAG system that intelligently routes user queries across text, images, documents, and voice to deliver context-aware, hallucination-resistant responses using dynamic retrieval pipelines.

---

## 🧠 Overview

AegisAI is a production-grade **Adaptive Multimodal Retrieval-Augmented Generation (RAG)** system designed to intelligently handle diverse user queries across text, documents, images, and voice.

Unlike traditional RAG systems, AegisAI dynamically analyzes user intent and selects the most optimal processing path in real time — whether it requires direct LLM reasoning, knowledge retrieval, conversational memory, or multimodal understanding.

The system integrates:

- 🔹 Adaptive query routing for intelligent decision-making  
- 🔹 Hybrid retrieval (FAISS + MongoDB) for grounded responses  
- 🔹 Session + long-term MongoDB memory for conversational continuity  
- 🔹 Multimodal pipelines (OCR + speech-to-text) for rich input handling  
- 🔹 Confidence-based fallback to minimize hallucinations  

This architecture ensures that responses are not only accurate and context-aware but also efficient and scalable for real-world production use.

AegisAI bridges the gap between static chatbots and truly intelligent AI systems by enabling dynamic reasoning, contextual awareness, and multimodal interaction within a unified pipeline.
---

## ✨ Features

- Adaptive Query Routing Engine  
  Dynamically selects optimal execution path (Direct / RAG / Memory / Multimodal) based on intent classification and confidence scoring
- Tavily-backed live web search for current events, sports, finance, weather, and breaking news
- Multimodal Input Support  
  Handles text, documents, images, and voice seamlessly
- FAISS-based retrieval with confidence-aware fallback
- MongoDB-backed conversational memory
- OCR pipeline for image understanding
- Gemini-backed streaming and speech-to-text
- Tavily web search for real-time factual answers
- Query correction and rewriting
- Hallucination reduction using grounded responses
- Streaming chat responses
- Redis-based caching with fallback
- Evaluation pipeline for RAG quality
- Structured logging and observability
- Rate limiting for production reliability
- Async-ready FastAPI backend

---

## ❗ Problem
Traditional LLMs suffer from hallucinations, lack real-time knowledge, and fail to handle multimodal inputs effectively.

## ✅ Solution
AegisAI introduces an adaptive routing-based RAG architecture that dynamically selects the best reasoning pipeline, integrates retrieval grounding, and supports multimodal understanding.

---

## 🚀 Why AegisAI Stands Out
- Adaptive routing (not static RAG)
- Multimodal + memory unified system
- Explainable AI responses
- Production-ready architecture

---

## 🎥 Demo

### 💬 Chat Interface
<img width="1440" height="816" alt="Screenshot 2026-06-16 at 12 16 57 PM" src="https://github.com/user-attachments/assets/80eb309c-f7c3-4ffa-a698-77c30d4a0e84" />



### 📂 File Upload & Processing
<img width="1440" height="818" alt="Screenshot 2026-06-16 at 12 19 57 PM" src="https://github.com/user-attachments/assets/c07a5577-5ad7-4c3f-b02f-d3f11841cd70" />



### 🧠 Explainability Panel
<img width="1440" height="817" alt="Screenshot 2026-06-16 at 12 17 18 PM" src="https://github.com/user-attachments/assets/1e195b68-5872-4f7b-ba7d-16fc9a23e74f" />

### 🔐 Authentication System
<img width="1439" height="817" alt="Screenshot 2026-06-16 at 12 16 38 PM" src="https://github.com/user-attachments/assets/45c922e7-5c55-42ee-b11b-d360aae14ba4" />




## 🏗️ Architecture

```
User Input (Text / Image / Voice)
↓
LLM Router (Intent + Confidence)
↓
| Direct | RAG | Memory | Multimodal |

↓ ↓ ↓ ↓
LLM Retriever Memory OCR/Voice
↓
Context Injection
↓
LLM
↓
Response + Logs + Cache + Evaluation
```

---

## 🛠️ Tech Stack

- Python
- FastAPI
- Google Gemini API
- Tavily Search API
- FAISS
- MongoDB
- Redis
- Tesseract OCR
- Uvicorn
- NumPy
- HTML / CSS / JavaScript
- PyPDF

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
│       ├── llm_router.py
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
├── data/
├── notebooks/
├── result/
├── tests/
├── requirements.txt
├── Dockerfile
├── .env.example
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

If you see a broken interpreter like `venv/bin/python3.14: no such file or directory`, delete the old virtual environment and recreate it with Python 3.11 or 3.12.

---

## 🔐 Environment Variables

```env
GEMINI_API_KEY=your_gemini_api_key
GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
MODEL_NAME=gemini-2.5-flash
FALLBACK_MODEL_NAME=
ROUTER_MODEL_NAME=
SUMMARY_MODEL_NAME=
TRANSCRIPTION_MODEL_NAME=
TAVILY_API_KEY=
TAVILY_MAX_RESULTS=5
WEB_SEARCH_TIMEOUT_SECONDS=12

MONGODB_URI=mongodb://localhost:27017
MONGODB_DB=aegisai

REDIS_URL=redis://localhost:6379/0

CORS_ORIGINS=*
TESSERACT_CMD=
RATE_LIMIT_REQUESTS=10
RATE_LIMIT_WINDOW_SECONDS=60
ROUTER_USE_LLM=true
ROUTER_LLM_CONFIDENCE_THRESHOLD=0.55
MEMORY_SUMMARY_TRIGGER_MESSAGES=8
MEMORY_SUMMARY_MAX_MESSAGES=20
LONG_TERM_MEMORY_SUMMARIES=4
LONG_TERM_MEMORY_CHAR_LIMIT=2200
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
⚡ Avg Latency: ~120ms  
🎯 Confidence Threshold: 0.75  
📊 Retrieval Accuracy: High (via hybrid search)

Run batch evaluation:

```bash
python3 -m app.evaluate_batch eval_samples.json
```

---
## 🌐 Frontend Features
- Chat bubble UI
- Streaming responses
- Upload preview (image / PDF)
- Loading indicators
- Clean responsive interface

---

## 🔍 Explainability

Each response includes internal reasoning:
- Selected route
- Confidence score
- Routing reason
- Retrieved documents + scores
- Fallback usage

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

## 🛡️ Hallucination Control

- Confidence-based retrieval filtering  
- Context grounding using FAISS  
- Smart fallback to LLM  
- Query rewriting  
- Memory-aware responses 


## 📊 Sample Results

User Query: What is artificial intelligence?  
Route: direct  
Response: AI is the simulation of human intelligence in machines.  

---

User Query: Explain machine learning from document  
Route: rag  
Retrieved Docs:  
- doc1.txt (0.89)  
- doc2.txt (0.84)  

Response: Machine learning is a subset of AI that learns from data.  

---

User Query: What did I ask before?  
Route: memory  
Response: You previously asked about machine learning.  

---

User Query: Analyze this image  
Route: multimodal  
OCR Output: "Deep learning model"  
Response: The image contains deep learning-related text.

## 👨‍💻 Author

Anubhav Rathore

---

## 📜 License

MIT License
