import os
import faiss
import numpy as np
from src.services.embedding import get_embedding_cached
from src.db.mongo import get_docs_collection
from src.core.logger import get_logger

logger = get_logger(__name__)

index = None
doc_store = []

def load_faiss_index():
    global index, doc_store
    try:
        if os.path.exists("vector_db/index.faiss") and os.path.exists("vector_db/docs.npy"):
            index = faiss.read_index("vector_db/index.faiss")
            doc_store = np.load("vector_db/docs.npy", allow_pickle=True).tolist()
        else:
            index = faiss.IndexFlatL2(768)
            doc_store = []
    except Exception as e:
        logger.error(f"FAISS load error: {str(e)}")
        index = faiss.IndexFlatL2(768)
        doc_store = []

def sync_from_mongo():
    global index, doc_store
    try:
        docs = list(get_docs_collection().find({}, {"_id": 0}))
        if not docs:
            return

        texts = [d.get("text", "") for d in docs if d.get("text")]
        embeddings = [get_embedding_cached(t) for t in texts]

        index = faiss.IndexFlatL2(len(embeddings[0]))
        index.add(np.array(embeddings).astype("float32"))

        doc_store = texts

    except Exception as e:
        logger.error(f"Mongo sync error: {str(e)}")

def retrieve_documents(query, k=3):
    try:
        if index is None or len(doc_store) == 0:
            return []

        query_embedding = get_embedding_cached(query)
        D, I = index.search(np.array([query_embedding]).astype("float32"), k)

        results = []
        for i in I[0]:
            if i < len(doc_store):
                results.append(doc_store[i])

        return results

    except Exception as e:
        logger.error(f"Retriever error: {str(e)}")
        return []
