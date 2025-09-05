import os
import numpy as np
from uuid import uuid4

import openai
from dotenv import load_dotenv
from tiktoken import get_encoding
import pinecone


load_dotenv()

# --- OpenAI setup -----------------------------------------------------------
openai.api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
encoding = get_encoding("cl100k_base")

# --- Pinecone env vars ------------------------------------------------------
PINECONE_API_KEY = (os.getenv("PINECONE_API_KEY") or "").strip()
PINECONE_ENV = (
    os.getenv("PINECONE_ENV") or
    os.getenv("PINECONE_ENVIRONMENT") or
    "us-east-1"
).strip()
INDEX_NAME = (os.getenv("PINECONE_INDEX_NAME") or "chatbot-facts").strip()

# --- Pinecone client (optional) ---------------------------------------------
index = None
if PINECONE_API_KEY:
    try:
        # Initialize Pinecone with SSL configuration
        # Use new Pinecone API format
        from pinecone import Pinecone
        pc = Pinecone(api_key=PINECONE_API_KEY)
        existing = [ix["name"] for ix in pc.list_indexes()]
        if INDEX_NAME not in existing:
            pc.create_index(
                name=INDEX_NAME,
                dimension=1536,
                metric="cosine"
            )
        index = pc.Index(INDEX_NAME)
        print("✅ Pinecone initialized successfully")
    except Exception as e:
        print(f"❌ Error getting facts from Pinecone: {e}")
        print("⚠️ Continuing without Pinecone vector database")
        index = None
else:
    print("⚠️ PINECONE_API_KEY not set - continuing without Pinecone")
    index = None


def should_embed(text: str) -> bool:
    IGNORE = ("thank you", "hi", "ok", "sure", "bye")
    if any(k in text.lower() for k in IGNORE):
        return False
    return len(text.split()) >= 3


def embed_text(text: str):
    resp = openai.embeddings.create(
        model="text-embedding-ada-002",
        input=text,
    )
    return resp.data[0].embedding


def save_chat_to_memory(message_text, session_id, user_id="default", emotion="neutral"):
    """
    Embeds and upserts a message into the Pinecone namespace for the given user_id.
    """
    if not index or not should_embed(message_text):
        return

    emb = embed_text(message_text)
    vid = f"{session_id}-{uuid4().hex[:6]}"

    metadata = {
        "text":       message_text,
        "session_id": session_id,
        "user_id":    user_id,
        "emotion":    emotion or ""
    }

    if index is None:
        print(f"⚠️ Pinecone not available - skipping fact save: {message_text!r}")
        return
    
    try:
        index.upsert(
            vectors=[{"id": vid, "values": emb, "metadata": metadata}],
            namespace=user_id,
        )
        print(f"✅ [🧠 FACT SAVED] {message_text!r} (id={vid}, user={user_id})")
    except Exception as e:
        print(f"❌ Pinecone upsert error: {e}", flush=True)


def search_chat_memory(query, top_k=3, user_id="default"):
    """
    Returns up to `top_k` stored texts for this user that best match `query`.
    """
    if not index:
        return []
        
    emb = embed_text(query)
    try:
        print(f"[DEBUG] querying namespace='{user_id}' for '{query}'")
        resp = index.query(
            namespace=user_id,
            vector=emb,
            top_k=top_k,
            include_metadata=True,
        )
        print(f"[DEBUG] got {len(resp.matches)} matches:")
        for m in resp.matches:
            print("       ", m.metadata, "→", m.score)
    except Exception as e:
        print(f"❌ Pinecone query error: {e}", flush=True)
        return []

    return [
        m.metadata.get("text")
        for m in resp.matches
        if m.metadata and m.metadata.get("text")
    ]


def get_user_facts(user_id, namespace=None):
    """
    Returns *all* saved facts for this user across sessions.
    """
    if not index:
        return []
        
    ns = namespace or user_id
    try:
        # Query with a random vector to retrieve all items in the namespace
        rand_vec = np.random.rand(1536).tolist()
        resp = index.query(
            namespace=ns,
            vector=rand_vec,
            top_k=200,
            include_metadata=True,
        )
    except Exception as e:
        print(f"❌ Error getting facts from Pinecone: {e}", flush=True)
        return []

    facts = []
    for m in resp.matches:
        md = m.metadata or {}
        txt = md.get("text") or md.get("fact")
        if txt:
            facts.append(txt)
    return facts

# ---------------------------------------------------------------------------
def summarize_old_facts(context_text: str) -> str:
    try:
        resp = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": (
                    "You are summarizing facts about a user to help a psychology chatbot "
                    "remember important details."
                )},
                {"role": "user", "content": f"Summarize these known facts about the user:\n\n{context_text}"},
            ],
            max_tokens=150,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print("❌ Error in summarize_old_facts():", e, flush=True)
        return ""


def extract_facts_with_gpt(user_input: str) -> str:
    prompt = f"""
Extract factual personal statements from the following user input. 
Examples: name, age, location, job, preferences, relationships, hobbies, beliefs, or other memorable details.
Respond one per line, each starting with 'FACT:'.
Return 'None' if there's nothing to store.

User input: "{user_input}"
"""
    try:
        resp = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a fact extractor for a psychology chatbot."},
                {"role": "user",   "content": prompt},
            ],
            max_tokens=100,
            temperature=0,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print("❌ Error extracting facts:", e, flush=True)
        return "None"
