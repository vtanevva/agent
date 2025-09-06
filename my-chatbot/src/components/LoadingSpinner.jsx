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
        <div className="absolute inset-0 rounded-full border-2 border-dark-500/30"></div>
        
        {/* Animated gradient ring */}
        <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-accent-500 border-r-secondary-500 border-b-dark-500 border-l-accent-600 animate-spin"></div>
        
        {/* Inner glow */}
        <div className="absolute inset-1 rounded-full bg-gradient-to-br from-accent-500/20 to-secondary-500/20 blur-sm"></div>
      </div>
      
      {text && (
        <div className="text-center">
          <p className="text-primary-900/80 text-sm font-medium animate-pulse">
            {text}
          </p>
          <div className="flex justify-center mt-2 space-x-1">
            <div className="w-1 h-1 bg-accent-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
            <div className="w-1 h-1 bg-secondary-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
            <div className="w-1 h-1 bg-dark-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
          </div>
        </div>
      )}
    </div>
  );
}


