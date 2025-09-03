import os
from dotenv import load_dotenv
import openai

from .emotion_detection import detect_emotion, detect_suicidal_intent
from .embeddings import search_similar_chunks
from .chat_embeddings import get_user_facts
from .chat_embeddings import summarize_old_facts

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")


def chat_with_gpt(user_message, user_id="default", session_id=None, return_meta=False, session_memory=None):
    wants_detail = any(word in user_message.lower() for word in [
        "why", "explain", "details", "how", "in depth", "give me", "what does"
    ])

    emotion, _ = detect_emotion(user_message)
    suicide_flag = detect_suicidal_intent(user_message)

    # 🧠 Load long-term fact memory
    fact_list = get_user_facts(user_id=user_id)
    fact_memory = "\n".join(f"- {fact}" for fact in fact_list) if fact_list else "No known facts."
    fact_summary = summarize_old_facts("\n".join(fact_list)) if fact_list else "No past summary."

    # 📚 Get related RAG context
    top_chunks = search_similar_chunks(user_message)
    data_context = "\n\n".join(top_chunks) if top_chunks else "No relevant context found."

    # ⚠️ Add emotional safety note
    safety_note = ""
    if len(user_message.split()) >= 3:
        if suicide_flag:
            safety_note = (
                "⚠️ It sounds like you're really struggling. You're not alone.\n"
                "Please consider talking to someone:\n"
                "- https://findahelpline.com/\n"
                "- 113 Zelfmoordpreventie (NL): 0800-0113"
            )
        elif emotion in ["sadness", "fear"]:
            safety_note = f"I hear you're feeling {emotion}. I'm here for you."

    # 📥 System + factual + background messages
    messages = [
        {
            "role": "system",
            "content": (
                "You are a friendly, human-like psychology chatbot named Aivis. "
                "Respond casually and naturally, like you're talking to a friend. "
                "Keep responses short unless the user asks for detailed help. "
                "Use contractions, emojis occasionally, and speak in a relatable way. "
                "Don’t sound like an AI assistant. The user may have talked to you before.\n"
                f"Here are some personal facts you've learned about them:\n{fact_memory}\n"
                f"Here is what you've learned from past conversations:\n{fact_summary}\n"
                "Use these facts to personalize your replies when relevant."
            )
        },
        {
            "role": "system",
            "content": f"External psychological background context:\n{data_context}"
        }
    ]

    # 💬 Add recent session memory if provided
    if session_memory:
        messages += session_memory  # should be a list of {"role": ..., "content": ...}

    # ➕ Add the new user message
    messages.append({
        "role": "user",
        "content": f"{user_message}\n\n{safety_note}"
    })

    # 🧠 DEBUG
    print("\n--- FACT MEMORY ---")
    print(fact_memory)
    print("\n--- FULL PROMPT MESSAGES ---")
    for msg in messages:
        print(f"[{msg['role'].upper()}] {msg['content']}\n")

    # 🤖 Query GPT
    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=messages,
        max_tokens=300 if wants_detail else 100,
        temperature=0.8
    )

    reply = response.choices[0].message.content.strip()

    if return_meta:
        return reply, emotion, suicide_flag
    return reply
