export default function InputBar({ input, setInput, loading, onSend, showConnectButton, onConnect }) {
  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      console.log("Enter key pressed, calling onSend");
      onSend();
    }
  };

  const handleSendClick = () => {
    console.log("Send button clicked");
    console.log("Current input:", input);
    console.log("Loading state:", loading);
    console.log("Input trimmed:", input.trim());
    onSend();
  };

  return (
    <div className="glass-effect-strong rounded-2xl p-4 lg:p-6 shadow-glow border border-dark-500/10">
      <div className="flex flex-col sm:flex-row gap-3 lg:gap-4 items-stretch sm:items-end">
        {/* Input field */}
        <div className="flex-1 relative">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            className="w-full px-4 lg:px-6 py-3 lg:py-4 rounded-xl text-primary-900 bg-primary-100/50 placeholder-primary-900/40 border border-dark-500/20 focus:border-accent-500/50 input-focus resize-none focus:bg-primary-100/70 transition-all duration-300 text-sm lg:text-base"
            placeholder="Share your thoughts, feelings, or ask me anything..."
            rows="1"
            style={{
              minHeight: '48px',
              maxHeight: '120px'
            }}
          />
          
        </div>

        {/* Send button */}
        <button
          onClick={handleSendClick}
          disabled={loading || !input.trim()}
          className="bg-gradient-to-r from-accent-500 to-accent-600 hover:from-accent-600 hover:to-accent-700 text-primary-50 px-6 lg:px-8 py-3 lg:py-4 rounded-xl disabled:opacity-50 disabled:cursor-not-allowed btn-hover font-semibold flex items-center justify-center gap-2 lg:gap-3 shadow-lg text-sm lg:text-base min-h-[48px]"
        >
          {loading ? (
            <>
              <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
              <span>Sending...</span>
            </>
          ) : (
            <>
              <span>Send</span>
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            </>
          )}
        </button>

        {/* Connect Google button */}
        {showConnectButton && (
          <button
            onClick={onConnect}
            className="bg-gradient-to-r from-secondary-500 to-secondary-600 hover:from-secondary-600 hover:to-secondary-700 text-primary-50 px-4 lg:px-6 py-3 lg:py-4 rounded-xl btn-hover font-semibold flex items-center justify-center gap-2 lg:gap-3 shadow-lg text-sm lg:text-base min-h-[48px]"
          >
            <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
              <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
              <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
              <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
              <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
            </svg>
            <span>Connect</span>
          </button>
        )}
      </div>
    </div>
  );
}
