import TypingIndicator from './TypingIndicator';
import WelcomeMessage from './WelcomeMessage';

export default function MessageList({ chat, loading }) {
  if (chat.length === 0 && !loading) {
    return <WelcomeMessage />;
  }

  return (
    <div className="space-y-6">
      {chat.map((msg, idx) => (
        <div
          key={idx}
          className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"} message-enter`}
        >
          <div
            className={`max-w-xs lg:max-w-md px-6 py-4 rounded-2xl shadow-lg ${
              msg.role === "user"
                ? "glass-effect-violet text-white rounded-br-md shadow-glow"
                : "glass-effect-emerald text-slate-800 rounded-bl-md shadow-glow-emerald"
            }`}
          >
            <div className="flex items-start gap-4">
              {/* Avatar */}
              <div className={`w-10 h-10 rounded-full flex items-center justify-center text-sm font-semibold ${
                msg.role === "user" 
                  ? "bg-gradient-to-br from-violet-400 to-purple-500 shadow-lg" 
                  : "bg-gradient-to-br from-emerald-400 to-teal-500 shadow-lg"
              }`}>
                {msg.role === "user" ? "👤" : "🌸"}
              </div>
              
              {/* Message content */}
              <div className="flex-1 min-w-0">
                <div className={`text-sm font-semibold mb-2 ${
                  msg.role === "user" ? "text-violet-100" : "text-emerald-800"
                }`}>
                  {msg.role === "user" ? "You" : "Mindful AI"}
                </div>
                <div className={`text-sm leading-relaxed whitespace-pre-wrap ${
                  msg.role === "user" ? "text-white" : "text-slate-700"
                }`}>
                  {msg.text}
                </div>
              </div>
            </div>
          </div>
        </div>
      ))}
      
      {loading && <TypingIndicator />}
    </div>
  );
}
