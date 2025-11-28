import os
import faiss
import pickle
import numpy as np
from dotenv import load_dotenv
from typing import List
from tiktoken import get_encoding

load_dotenv()

encoding = get_encoding("cl100k_base")


def _get_llm_service():
    """Get the LLM service instance."""
    from app.services.llm_service import get_llm_service
    return get_llm_service()

def split_text(text: str, max_tokens=300) -> List[str]:
    words = text.split()
    chunks = []
    chunk = []
    token_count = 0

    for word in words:
        token_count += len(encoding.encode(word))
        chunk.append(word)
        if token_count >= max_tokens:
            chunks.append(" ".join(chunk))
            chunk = []
            token_count = 0
    if chunk:
        chunks.append(" ".join(chunk))
    return chunks

def embed_text_chunks(chunks: List[str]):
    """Generate embeddings for text chunks using LLM service."""
    llm_service = _get_llm_service()
    return llm_service.generate_embeddings_batch(chunks)

def build_vector_store(file_path: str):
    with open(file_path, 'r', encoding='utf-8') as f:
        text = f.read()

    chunks = split_text(text)
    embeddings = embed_text_chunks(chunks)

    dim = len(embeddings[0])
    index = faiss.IndexFlatL2(dim)
    index.add(np.array(embeddings).astype("float32"))

    with open("rag_chunks.pkl", "wb") as f:
        pickle.dump(chunks, f)
    faiss.write_index(index, "rag_index.faiss")

    print("Vector store built and saved.")

def load_vector_store():
    try:
        # Check if files exist first
        if not os.path.exists("rag_index.faiss"):
            print("rag_index.faiss not found. RAG functionality will be disabled.")
            return None, []
        
        if not os.path.exists("rag_chunks.pkl"):
            print("rag_chunks.pkl not found. RAG functionality will be disabled.")
            return None, []
        
        # Load the files
        index = faiss.read_index("rag_index.faiss")
        with open("rag_chunks.pkl", "rb") as f:
            chunks = pickle.load(f)
        return index, chunks
    except Exception as e:
        print(f"Error loading vector store: {e}. RAG functionality will be disabled.")
        return None, []

def search_similar_chunks(user_query: str, top_k=3):
    """Search for similar chunks using FAISS and LLM service embeddings."""
    index, chunks = load_vector_store()
    
    # If vector store is not available, return empty results
    if index is None or len(chunks) == 0:
        print("Vector store not available. Returning empty search results.")
        return []
    
    llm_service = _get_llm_service()
    query_embedding = llm_service.generate_embedding(user_query)

    D, I = index.search(np.array([query_embedding], dtype='float32'), top_k)
    results = [chunks[i] for i in I[0]]
    return results

#  manual rebuild from CLI
if __name__ == "__main__":
    build_vector_store("data/psychology_guide.txt")
