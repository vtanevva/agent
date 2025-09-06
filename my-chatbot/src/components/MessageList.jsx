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
            className={`max-w-xs lg:max-w-md px-6 py-4 rounded-2xl shadow-lg border ${
              msg.role === "user"
                ? "glass-effect-violet text-primary-900 rounded-br-md shadow-glow border-accent-500/20"
                : "glass-effect-emerald text-primary-900 rounded-bl-md shadow-glow-emerald border-secondary-500/20"
            }`}
          >
            <div className="flex items-start gap-4">
              {/* Avatar */}
              <div className={`w-10 h-10 rounded-full flex items-center justify-center text-sm font-semibold ${
                msg.role === "user" 
                  ? "bg-gradient-to-br from-accent-500 to-accent-600 shadow-lg text-primary-50" 
                  : "bg-gradient-to-br from-secondary-500 to-secondary-600 shadow-lg text-primary-50"
              }`}>
                {msg.role === "user" ? "👤" : "🌸"}
              </div>
              
              {/* Message content */}
              <div className="flex-1 min-w-0">
                <div className={`text-sm font-semibold mb-2 ${
                  msg.role === "user" ? "text-accent-700" : "text-secondary-700"
                }`}>
                  {msg.role === "user" ? "You" : "Mindful AI"}
                </div>
                <div className={`text-sm leading-relaxed whitespace-pre-wrap ${
                  msg.role === "user" ? "text-primary-900" : "text-primary-900"
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
