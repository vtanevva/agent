export default function TypingIndicator() {
  return (
    <div className="flex justify-start mb-4">
      <div className="bg-gradient-to-r from-secondary-500/20 to-dark-500/20 backdrop-blur-xl rounded-2xl px-6 py-4 max-w-xs border border-secondary-500/30 shadow-lg">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-gradient-to-br from-secondary-500 to-dark-500 rounded-full flex items-center justify-center">
            <span className="text-primary-50 text-sm">🤖</span>
          </div>
          
          {/* Typing animation dots */}
          <div className="flex space-x-1">
            <div className="w-2 h-2 bg-secondary-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
            <div className="w-2 h-2 bg-secondary-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
            <div className="w-2 h-2 bg-secondary-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
          </div>
        </div>
        
        <div className="text-xs text-primary-900/80 mt-2 font-medium">
          AI is crafting a thoughtful response...
        </div>
      </div>
    </div>
  );
}


