from __future__ import annotations

from src.config import DATA_DIR, settings
from src.services.documents import chunk_text
from src.services.logging_service import app_logger
from src.services.vector_store import vector_store


def main() -> None:
    docs = []
    for path in DATA_DIR.glob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").strip()
        if not text:
            continue
        for chunk in chunk_text(text, settings.chunk_size, settings.chunk_overlap):
            docs.append(
                {
                    "text": chunk,
                    "source": path.name,
                    "kind": "document",
                    "path": str(path),
                }
            )
    if docs:
        indexed = vector_store.add_documents(docs)
        app_logger.log("ingest_data", indexed=indexed, files=[doc["source"] for doc in docs[:20]])
        print(f"Indexed {indexed} chunks")
    else:
        print("No data indexed")


if __name__ == "__main__":
    main()
