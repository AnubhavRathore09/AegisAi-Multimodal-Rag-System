import os
import logging

# ✅ Latest LangChain imports
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings

# 🔥 Logging setup
logging.basicConfig(level=logging.INFO)

# 📁 Vector DB path
DB_PATH = "vector_db"

# 🧠 Embedding model (fast + accurate)
embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)


def process_document(file_path: str):
    try:
        logging.info(f"📄 Processing file: {file_path}")

        # ✅ Ensure DB folder exists
        os.makedirs(DB_PATH, exist_ok=True)

        # 📄 Load PDF
        loader = PyPDFLoader(file_path)
        documents = loader.load()

        # 🏷️ Add metadata (IMPORTANT)
        for doc in documents:
            doc.metadata["source"] = file_path

        # ✂️ Split into chunks
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50
        )

        docs = splitter.split_documents(documents)
        logging.info(f"🔹 Chunks created: {len(docs)}")

        # 🔥 Load existing DB OR create new
        if os.path.exists(DB_PATH) and os.listdir(DB_PATH):
            db = FAISS.load_local(
                DB_PATH,
                embeddings,
                allow_dangerous_deserialization=True
            )
            db.add_documents(docs)
            logging.info("✅ Added to existing vector DB")
        else:
            db = FAISS.from_documents(docs, embeddings)
            logging.info("🆕 Created new vector DB")

        # 💾 Save DB
        db.save_local(DB_PATH)

        return {
            "status": "success",
            "chunks_added": len(docs),
            "file": file_path
        }

    except Exception as e:
        logging.error(f"❌ Error: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }
