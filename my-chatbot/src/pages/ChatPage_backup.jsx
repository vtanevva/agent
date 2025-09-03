import { useState, useEffect, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";

export default function ChatPage() {
  const { userId, sessionId } = useParams();
  const navigate = useNavigate();
  
  const [input, setInput] = useState("");
  const [chat, setChat] = useState([]);
  const [loading, setLoading] = useState(false);

  const handleSend = async (msg = input) => {
    if (!msg.trim()) return;
    
    setInput("");
    setChat((c) => [...c, { role: "user", text: msg }]);
    setLoading(true);
    
    try {
      const r = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: msg,
          user_id: userId,
          session_id: sessionId,
        }),
      });
      
      const data = await r.json();
      const { reply } = data;
      setChat((c) => [...c, { role: "assistant", text: reply }]);
    } catch (e) {
      console.error("send error", e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="w-full max-w-2xl flex flex-col glass-effect-strong p-6 rounded-3xl shadow-glow border border-slate-600/30">
      <h1 className="text-white text-2xl font-bold mb-4">Chat with {userId}</h1>
      
      <div className="flex-1 overflow-y-auto mb-4 space-y-4">
        {chat.map((msg, idx) => (
          <div key={idx} className={`p-3 rounded-lg ${
            msg.role === "user" ? "bg-violet-600/20 text-white ml-12" : "bg-emerald-600/20 text-white mr-12"
          }`}>
            <strong>{msg.role === "user" ? "You" : "AI"}:</strong> {msg.text}
          </div>
        ))}
        
        {loading && (
          <div className="bg-emerald-600/20 text-white mr-12 p-3 rounded-lg">
            <strong>AI:</strong> Thinking...
          </div>
        )}
      </div>

      <div className="flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
          className="flex-1 px-4 py-2 rounded-lg bg-slate-800/50 text-white placeholder-slate-300/60 border border-slate-600/30"
          placeholder="Type your message..."
        />
        <button
          onClick={() => handleSend()}
          disabled={loading || !input.trim()}
          className="px-6 py-2 bg-violet-600 text-white rounded-lg hover:bg-violet-700 disabled:opacity-50"
        >
          Send
        </button>
      </div>

      <div className="mt-4 flex gap-2 justify-center">
        <button
          onClick={() => navigate("/")}
          className="text-sm text-slate-300/60 hover:text-white px-4 py-2 rounded-lg hover:bg-slate-700/30"
        >
          ← Back to Login
        </button>
      </div>
    </div>
  );
}
