export default function EmailList({ emails, onSelect }) {
  return (
    <div className="space-y-4 mt-6">
      <div className="text-center mb-4">
        <h3 className="text-lg font-semibold text-primary-900 mb-2">Recent Emails</h3>
        <p className="text-primary-900/60 text-sm">Select an email to reply to</p>
      </div>
      
      <div className="grid gap-3 max-h-96 overflow-y-auto custom-scrollbar">
        {emails.map((email, index) => (
          <div
            key={email.threadId}
            className="group cursor-pointer glass-effect p-4 rounded-xl border border-dark-500/20 hover:border-accent-500/50 transition-all duration-300 hover:bg-primary-200/20 card-hover"
            onClick={() => onSelect(email.threadId, email.from)}
          >
            <div className="flex items-start gap-3">
              {/* Email icon */}
              <div className="flex-shrink-0 w-10 h-10 bg-gradient-to-br from-accent-500 to-secondary-600 rounded-full flex items-center justify-center text-primary-50 text-sm font-semibold shadow-lg group-hover:scale-110 transition-transform duration-300">
                {email.from.charAt(0).toUpperCase()}
              </div>
              
              {/* Email content */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <p className="text-sm font-medium text-primary-900 truncate">
                    {email.from.replace(/<[^>]*>/g, '').trim()}
                  </p>
                  <span className="text-xs text-primary-900/60 bg-primary-200/50 px-2 py-1 rounded-full">
                    #{email.idx}
                  </span>
                </div>
                
                <h4 className="text-sm font-semibold text-primary-900 mb-2 line-clamp-1 group-hover:text-accent-600 transition-colors duration-300">
                  {email.subject}
                </h4>
                
                <p className="text-xs text-primary-900/70 line-clamp-2 leading-relaxed">
                  {email.snippet}
                </p>
                
                {/* Hover indicator */}
                <div className="mt-2 flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                  <span className="text-xs text-accent-600 font-medium">Click to reply</span>
                  <svg className="w-3 h-3 text-accent-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                </div>
              </div>
              
              {/* Thread ID badge */}
              <div className="flex-shrink-0">
                <span className="text-xs text-primary-900/60 bg-primary-200/50 px-2 py-1 rounded-md font-mono">
                  {email.threadId.slice(-8)}
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>
      
      {emails.length === 0 && (
        <div className="text-center py-8">
          <div className="w-16 h-16 bg-primary-200/50 rounded-full flex items-center justify-center mx-auto mb-4 border border-dark-500/10">
            📭
          </div>
          <p className="text-primary-900/60 text-sm">No emails found</p>
        </div>
      )}
    </div>
  );
}
