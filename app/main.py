import os
import uuid
from chatbot import chat_with_gpt
from memory import save_message
from .chat_embeddings import save_chat_to_memory, search_chat_memory
import openai
from dotenv import load_dotenv

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")

# getting user ID and session
user_id = input("Enter your username: ").strip().lower()
session_id = f"{user_id}-{str(uuid.uuid4())[:8]}"

print(f"New Session Started (User: {user_id} | Session ID: {session_id})")
print("Type 'exit' to quit.\n")

while True:
    user_input = input("You: ")
    if user_input.lower() in ['exit', 'quit']:
        print("Ending session.")
        break

    # memory search
    if user_input.lower().startswith("memory:"):
        query = user_input.replace("memory:", "").strip()
        results = search_chat_memory(query, user_id=user_id)
        print("Top memory matches:")
        for i, r in enumerate(results, 1):
            print(f"{i}. {r}")
        continue

    # summarize request
    if user_input.lower().startswith("summarize:"):
        messages = search_chat_memory("reflect on all", user_id=user_id)
        context = "\n".join(messages)
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a gentle assistant. Summarize the user's recent concerns or emotional patterns."},
                {"role": "user", "content": context}
            ],
            max_tokens=300
        )
        print("Summary:\n", response.choices[0].message.content.strip())
        continue

    try:
        # main conversation logic
        reply, emotion, suicide_flag = chat_with_gpt(
                    user_input,
                    user_id=user_id,
                    session_id=session_id,
                    return_meta=True
        
                )
        print("Bot:", reply)

        save_message(session_id, user_input, reply, emotion, suicide_flag)
        from chat_embeddings import extract_facts_with_gpt

        extracted = extract_facts_with_gpt(user_input)
        for line in extracted.split("\n"):
            line = line.strip("- ").strip()
            if not line or line.lower() == "none":
                continue
            clean = line.removeprefix("FACT:").strip()
            print(f"[🧠 FACT FOUND] {clean}")
            save_chat_to_memory(
                clean,
                session_id=session_id,
                user_id=user_id,
                emotion=emotion
            )

    except Exception as e:
        import traceback
        print("❌ An error occurred:")
        traceback.print_exc()
