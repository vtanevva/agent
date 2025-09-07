import TypingIndicator from './TypingIndicator';
import WelcomeMessage from './WelcomeMessage';
import EmailList from './EmailList';

export default function MessageList({ chat, loading, onEmailSelect }) {
  const sanitizeJson = (s) => {
    if (!s) return s;
    let out = s.replace(/,\s*(?=[}\]])/g, "");
    out = out.replace(/'(?=\s*[:,}\]])/g, '"');
    out = out.replace(/"\s*:\s*'([^']*)'/g, '" : "$1"');
    return out;
  };

  const parseMarkdownEmailList = (text) => {
    if (typeof text !== 'string') return [];
    const t = text.replace(/\r\n/g, '\n');
    const items = [];
    const re = /\n?\s*\d+\.\s+\*\*From:\*\*\s*([\s\S]*?)\n\s*\*\*Subject:\*\*\s*([\s\S]*?)\n\s*\*\*Snippet:\*\*\s*([\s\S]*?)(?=\n\s*\d+\.\s|$)/g;
    let m;
    let idx = 1;
    while ((m = re.exec(t)) !== null) {
      const from = m[1].trim();
      const subject = m[2].trim();
      const snippet = m[3].trim();
      items.push({ idx, from, subject, snippet, threadId: `md-${idx}` });
      idx += 1;
    }
    return items;
  };

  const parseEmailJson = (text) => {
    if (typeof text !== "string") return null;
    const noFences = text.replace(/```[a-zA-Z]*\r?\n?|```/g, "").trim();
    // Try full parse
    try {
      const parsed = JSON.parse(noFences);
      if (Array.isArray(parsed) && (parsed[0]?.threadId || parsed.find?.(e => e?.threadId))) return parsed;
    } catch {}
    // Try to extract the first balanced JSON array
    const start = noFences.indexOf('[');
    if (start !== -1) {
      let depth = 0;
      for (let i = start; i < noFences.length; i++) {
        const ch = noFences[i];
        if (ch === '[') depth++;
        else if (ch === ']') depth--;
        if (depth === 0) {
          let candidate = noFences.slice(start, i + 1);
          candidate = sanitizeJson(candidate);
          try {
            const parsed = JSON.parse(candidate);
            if (Array.isArray(parsed) && (parsed[0]?.threadId || parsed.find?.(e => e?.threadId))) return parsed;
          } catch {}
          break;
        }
      }
      // Fallback: from first '[' to last ']'
      const end = noFences.lastIndexOf(']');
      if (end > start) {
        let candidate = noFences.slice(start, end + 1);
        candidate = sanitizeJson(candidate);
        try {
          const parsed = JSON.parse(candidate);
          if (Array.isArray(parsed) && (parsed[0]?.threadId || parsed.find?.(e => e?.threadId))) return parsed;
        } catch {}
      }
    }
    // Last resort: sanitize entire string
    try {
      const parsed = JSON.parse(sanitizeJson(noFences));
      if (Array.isArray(parsed) && (parsed[0]?.threadId || parsed.find?.(e => e?.threadId))) return parsed;
    } catch {}
    return null;
  };

  if (chat.length === 0 && !loading) {
    return <WelcomeMessage />;
  }

  return (
    <div className="space-y-6">
      {chat.map((msg, idx) => {
        const emailsFromJson = msg.role !== 'user' ? parseEmailJson(msg.text) : null;
        const emailsFromMd = !emailsFromJson && msg.role !== 'user' ? parseMarkdownEmailList(msg.text) : [];
        return (
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
                {msg.role === "user" ? (
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z" clipRule="evenodd" />
                  </svg>
                ) : (
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M10 2a8 8 0 100 16 8 8 0 000-16zM7 8a1 1 0 100-2 1 1 0 000 2zM7 12a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
                    <path d="M8 6h4v1H8V6z" />
                  </svg>
                )}
              </div>
              
              {/* Message content */}
              <div className="flex-1 min-w-0">
                <div className={`text-sm font-semibold mb-2 ${
                  msg.role === "user" ? "text-accent-700" : "text-secondary-700"
                }`}>
                  {msg.role === "user" ? "You" : "Mindful AI"}
                </div>
                {emailsFromJson ? (
                  <div className="mt-1 -mx-6">
                    <EmailList emails={emailsFromJson} onSelect={onEmailSelect} />
                  </div>
                ) : emailsFromMd.length > 0 ? (
                  <div className="space-y-3 mt-1 -mx-6">
                    <div className="text-center mb-2">
                      <h3 className="text-lg font-semibold text-primary-900 mb-1">Recent Emails</h3>
                      <p className="text-primary-900/60 text-sm">(Read-only)</p>
                    </div>
                    <div className="grid gap-3 max-h-96 overflow-y-auto custom-scrollbar px-6">
                      {emailsFromMd.map((email, i) => (
                        <div
                          key={`md-${i}`}
                          className="glass-effect p-4 rounded-xl border border-dark-500/20 hover:border-accent-500/50 transition-all duration-300 hover:bg-primary-200/20 card-hover cursor-default w-full -ml-2 mr-2 sm:-ml-3 sm:mr-3 md:-ml-4 md:mr-4"
                        >
                          <div className="flex items-start gap-3">
                            <div className="flex-shrink-0 w-10 h-10 bg-gradient-to-br from-accent-500 to-secondary-600 rounded-full flex items-center justify-center text-primary-50 text-sm font-semibold shadow-lg">
                              {email.from?.charAt(0)?.toUpperCase?.() || 'E'}
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 mb-1">
                                <p className="text-sm font-medium text-primary-900 truncate">
                                  {email.from}
                                </p>
                                <span className="text-xs text-primary-900/60 bg-primary-200/50 px-2 py-1 rounded-full">#{email.idx}</span>
                              </div>
                              <h4 className="text-sm font-semibold text-primary-900 mb-2 line-clamp-1">
                                {email.subject}
                              </h4>
                              <p className="text-xs text-primary-900/70 line-clamp-2 leading-relaxed">
                                {email.snippet}
                              </p>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className={`text-sm leading-relaxed whitespace-pre-wrap ${
                    msg.role === "user" ? "text-primary-900" : "text-primary-900"
                  }`}>
                    {msg.text}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
        );
      })}
      
      {loading && <TypingIndicator />}
    </div>
  );
}
