import os
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import openai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Create Flask app
app = Flask(__name__, static_folder="my-chatbot/build", static_url_path="")
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

print(f"🚀 Simple server starting on port {os.getenv('PORT', '10000')}")

@app.route("/health")
def health_check():
    return jsonify({"status": "healthy", "message": "Simple server is running"})

@app.route("/api/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json()
        user_message = data.get("message", "")
        
        if not user_message:
            return jsonify({"error": "No message provided"}), 400
        
        # Simple chat with OpenAI
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful AI assistant."},
                {"role": "user", "content": user_message}
            ],
            max_tokens=500
        )
        
        reply = response.choices[0].message.content
        
        return jsonify({
            "reply": reply,
            "emotion": "neutral",
            "suicide_flag": False
        })
        
    except Exception as e:
        print(f"Chat error: {e}")
        return jsonify({"error": "Chat failed", "details": str(e)}), 500

@app.route("/api/sessions-log", methods=["POST"])
def sessions_log():
    # Simple mock response for sessions
    return jsonify({"sessions": []})

@app.route("/api/session_chat", methods=["POST"])
def session_chat():
    # Simple mock response for session chat
    return jsonify({"status": "ok"})

@app.route("/api/test")
def api_test():
    return jsonify({"message": "Simple server is working!"})

# Serve frontend
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    full_path = os.path.join(app.static_folder, path)
    if path and os.path.exists(full_path):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, "index.html")

if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    print(f"🚀 Starting simple server on port {port}")
    app.run(host="0.0.0.0", port=port, debug=True)
