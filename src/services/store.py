from src.db.mongo import collection
from src.services.embedding import get_embedding

def store_document(text: str):
    embedding = get_embedding(text)

    doc = {
        "text": text,
        "embedding": embedding
    }

    collection.insert_one(doc)
