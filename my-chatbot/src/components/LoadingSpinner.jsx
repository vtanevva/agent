export default function LoadingSpinner({ size = "md", text = "Loading..." }) {
  const sizeClasses = {
    sm: "w-6 h-6",
    md: "w-10 h-10", 
    lg: "w-16 h-16",
    xl: "w-20 h-20"
  };

  return (
    <div className="flex flex-col items-center justify-center space-y-4">
      <div className={`${sizeClasses[size]} relative`}>
        {/* Outer ring */}
        <div className="absolute inset-0 rounded-full border-2 border-slate-600/30"></div>
        
        {/* Animated gradient ring */}
        <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-violet-400 border-r-purple-400 border-b-fuchsia-400 border-l-pink-400 animate-spin"></div>
        
        {/* Inner glow */}
        <div className="absolute inset-1 rounded-full bg-gradient-to-br from-violet-500/20 to-purple-500/20 blur-sm"></div>
      </div>
      
      {text && (
        <div className="text-center">
          <p className="text-slate-300/80 text-sm font-medium animate-pulse">
            {text}
          </p>
          <div className="flex justify-center mt-2 space-x-1">
            <div className="w-1 h-1 bg-violet-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
            <div className="w-1 h-1 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
            <div className="w-1 h-1 bg-fuchsia-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
          </div>
        </div>
      )}
    </div>
  );
}


