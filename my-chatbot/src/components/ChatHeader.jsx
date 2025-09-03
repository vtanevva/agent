export default function ChatHeader({ userId, sessionId, useVoice, setUseVoice }) {
  return (
    <div className="glass-effect-strong rounded-2xl p-6 mb-6 shadow-glow">
      <div className="flex justify-between items-center">
        {/* User info */}
        <div className="flex items-center gap-4">
          <div className="w-14 h-14 bg-gradient-to-br from-violet-400 via-purple-500 to-fuchsia-500 rounded-full flex items-center justify-center text-white font-bold text-xl shadow-lg">
            {userId.charAt(0).toUpperCase()}
          </div>
          <div>
            <div className="text-white font-bold text-xl">
              {userId}
            </div>
            <div className="text-slate-300/70 text-sm">
              Session: {sessionId.slice(-8)}
            </div>
          </div>
        </div>

        {/* Voice toggle button */}
        <button
          onClick={() => setUseVoice(!useVoice)}
          className={`px-8 py-4 rounded-xl font-semibold transition-all duration-300 btn-hover shadow-lg ${
            useVoice 
              ? "bg-gradient-to-r from-emerald-500 to-teal-600 text-white" 
              : "bg-gradient-to-r from-violet-500 to-purple-600 text-white"
          }`}
        >
          <div className="flex items-center gap-3">
            {useVoice ? (
              <>
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
                <span>Text Mode</span>
              </>
            ) : (
              <>
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                </svg>
                <span>Voice Mode</span>
              </>
            )}
          </div>
        </button>
      </div>
    </div>
  );
}
