import json
import os
from datetime import datetime
import pinecone  # make sure you’ve done pinecone.init(...)
from your_embedding_lib import get_embedding  # wherever you get your embeddings

HISTORY_DIR = "chat_history"
INDEX_NAME = "your-index-name"

os.makedirs(HISTORY_DIR, exist_ok=True)
index = pinecone.Index(INDEX_NAME)

def get_history_path(session_id):
    return os.path.join(HISTORY_DIR, f"{session_id}.json")

def save_message(session_id, user_message, bot_reply, emotion=None, suicide_flag=False):
    timestamp = datetime.utcnow().isoformat()
    entry = {
        "timestamp": timestamp,
        "user": user_message,
        "bot": bot_reply,
        "emotion": emotion,
        "suicide_flag": suicide_flag
    }

    # 1) Save to disk
    path = get_history_path(session_id)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            history = json.load(f)
    else:
        history = []
    history.append(entry)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)

    # 2) Prepare metadata for Pinecone, dropping any nulls
    clean_meta = {
        k: v for k, v in {
            "user": user_message,
            "bot": bot_reply,
            "emotion": emotion,
            "suicide_flag": suicide_flag,
            # add other metadata keys here…
        }.items()
        if v is not None
    }

    # 3) Get the embedding for your “fact” (e.g. just the user_message, or user+bot, etc.)
    vector = get_embedding(user_message)

    # 4) Upsert into Pinecone with an ID that’s unique per session+time
    vec_id = f"{session_id}_{timestamp}"
    index.upsert(vectors=[{
        "id": vec_id,
        "values": vector,
        "metadata": clean_meta
    }])
