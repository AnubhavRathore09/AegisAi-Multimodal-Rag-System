from langchain.text_splitter import RecursiveCharacterTextSplitter
from src.services.embedding import get_embedding_cached
from src.db.mongo import get_docs_collection

def process_document(text: str, source: str = "uploaded"):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50
    )

    chunks = splitter.split_text(text)

    docs = []

    for chunk in chunks:
        emb = get_embedding_cached(chunk)

        docs.append({
            "text": chunk,
            "embedding": emb,
            "source": source
        })

    if docs:
        get_docs_collection().insert_many(docs)

    return len(docs)
