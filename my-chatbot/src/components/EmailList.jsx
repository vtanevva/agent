export default function EmailList({ emails, onSelect }) {
  return (
    <div className="space-y-4 mt-6">
      <div className="text-center mb-4">
        <h3 className="text-lg font-semibold text-white mb-2">📧 Recent Emails</h3>
        <p className="text-slate-300/60 text-sm">Select an email to reply to</p>
      </div>
      
      <div className="grid gap-3 max-h-96 overflow-y-auto custom-scrollbar">
        {emails.map((email, index) => (
          <div
            key={email.threadId}
            className="group cursor-pointer glass-effect p-4 rounded-xl border border-slate-600/30 hover:border-violet-400/50 transition-all duration-300 hover:bg-slate-700/20 card-hover"
            onClick={() => onSelect(email.threadId, email.from)}
          >
            <div className="flex items-start gap-3">
              {/* Email icon */}
              <div className="flex-shrink-0 w-10 h-10 bg-gradient-to-br from-violet-500 to-purple-600 rounded-full flex items-center justify-center text-white text-sm font-semibold shadow-lg group-hover:scale-110 transition-transform duration-300">
                {email.from.charAt(0).toUpperCase()}
              </div>
              
              {/* Email content */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <p className="text-sm font-medium text-white truncate">
                    {email.from.replace(/<[^>]*>/g, '').trim()}
                  </p>
                  <span className="text-xs text-slate-400 bg-slate-700/50 px-2 py-1 rounded-full">
                    #{email.idx}
                  </span>
                </div>
                
                <h4 className="text-sm font-semibold text-white mb-2 line-clamp-1 group-hover:text-violet-300 transition-colors duration-300">
                  {email.subject}
                </h4>
                
                <p className="text-xs text-slate-300/80 line-clamp-2 leading-relaxed">
                  {email.snippet}
                </p>
                
                {/* Hover indicator */}
                <div className="mt-2 flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                  <span className="text-xs text-violet-400 font-medium">Click to reply</span>
                  <svg className="w-3 h-3 text-violet-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                </div>
              </div>
              
              {/* Thread ID badge */}
              <div className="flex-shrink-0">
                <span className="text-xs text-slate-500 bg-slate-800/50 px-2 py-1 rounded-md font-mono">
                  {email.threadId.slice(-8)}
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>
      
      {emails.length === 0 && (
        <div className="text-center py-8">
          <div className="w-16 h-16 bg-slate-700/50 rounded-full flex items-center justify-center mx-auto mb-4">
            📭
          </div>
          <p className="text-slate-300/60 text-sm">No emails found</p>
        </div>
      )}
    </div>
  );
}
