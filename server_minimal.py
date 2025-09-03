import os
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from datetime import datetime

# ──────────────────────────────────────────────────────────────────
# App setup
# ──────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder="my-chatbot/build", static_url_path="")
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

# Debug info
port = os.environ.get("PORT", "10000")
print(f"🚀 [STARTUP] Server starting on port: {port}")
print(f"🌍 [STARTUP] Binding to 0.0.0.0:{port}")
print(f"📁 [STARTUP] Static folder: my-chatbot/build")
print(f"🔗 [STARTUP] Available environment variables: PORT={port}")

# ──────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    """Serve the React frontend"""
    try:
        return send_from_directory("my-chatbot/build", "index.html")
    except Exception as e:
        return f"Error serving frontend: {str(e)}", 500

@app.route("/health")
def health_check():
    """Health check endpoint for Render"""
    return jsonify({
        "status": "healthy",
        "message": "Minimal server is running",
        "timestamp": datetime.now().isoformat(),
        "port": os.environ.get("PORT", "unknown"),
        "version": "minimal-1.0"
    }), 200

@app.route("/api/test")
def api_test():
    """Simple API test endpoint"""
    return jsonify({
        "message": "API is working!",
        "timestamp": datetime.now().isoformat(),
        "port": os.environ.get("PORT", "unknown")
    }), 200

@app.route("/api/chat", methods=["POST"])
def chat():
    """Placeholder chat endpoint"""
    return jsonify({
        "message": "Chat endpoint is working! (Features will be added back gradually)",
        "status": "success",
        "timestamp": datetime.now().isoformat()
    }), 200

# ──────────────────────────────────────────────────────────────────
# Error handlers
# ──────────────────────────────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found", "status": 404}), 404

@app.errorhandler(500)
def internal_error(e):
    return jsonify({"error": "Internal server error", "status": 500}), 500

# ──────────────────────────────────────────────────────────────────
# Debug info
# ──────────────────────────────────────────────────────────────────
print(f"✅ [STARTUP] Flask app created successfully")
print(f"📋 [STARTUP] Available routes:")
for rule in app.url_map.iter_rules():
    print(f"   {rule.rule} -> {rule.endpoint}")

# ──────────────────────────────────────────────────────────────────
# Main (for local testing)
# ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"🚀 Starting development server on 0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=True)
