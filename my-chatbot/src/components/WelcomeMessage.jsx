export default function WelcomeMessage() {
  return (
    <div className="text-center space-y-8 py-12">
      {/* Hero Section */}
      <div className="space-y-6">
        <div className="relative">
          <div className="w-24 h-24 bg-gradient-to-br from-violet-500 via-purple-500 to-fuchsia-500 rounded-full flex items-center justify-center mx-auto text-4xl shadow-2xl animate-pulse">
            🌸
          </div>
          <div className="absolute -top-2 -right-2 w-8 h-8 bg-gradient-to-br from-pink-400 to-rose-500 rounded-full flex items-center justify-center text-sm animate-bounce">
            ✨
          </div>
        </div>
        
        <div className="space-y-4">
          <h2 className="text-3xl font-bold bg-gradient-to-r from-violet-400 via-purple-400 to-fuchsia-400 bg-clip-text text-transparent">
            Welcome to Mindful AI
          </h2>
          <p className="text-slate-200/80 text-lg max-w-2xl mx-auto leading-relaxed">
            Your compassionate AI companion for mental wellness. I'm here to listen, support, and guide you on your journey to better mental health.
          </p>
        </div>
      </div>

      {/* Features Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-4xl mx-auto">
        <div className="group bg-gradient-to-br from-violet-500/10 to-purple-500/10 backdrop-blur-sm rounded-2xl p-6 border border-violet-400/20 hover:border-violet-400/40 transition-all duration-300 hover:scale-105">
          <div className="w-12 h-12 bg-gradient-to-br from-violet-400 to-purple-500 rounded-xl flex items-center justify-center mx-auto mb-4 group-hover:scale-110 transition-transform duration-300">
            <span className="text-2xl">🧘‍♀️</span>
          </div>
          <h3 className="text-violet-200 font-semibold text-lg mb-2">Mindful Conversations</h3>
          <p className="text-slate-300/70 text-sm leading-relaxed">
            Safe, confidential space for open dialogue about your thoughts and feelings
          </p>
        </div>
        
        <div className="group bg-gradient-to-br from-emerald-500/10 to-teal-500/10 backdrop-blur-sm rounded-2xl p-6 border border-emerald-400/20 hover:border-emerald-400/40 transition-all duration-300 hover:scale-105">
          <div className="w-12 h-12 bg-gradient-to-br from-emerald-400 to-teal-500 rounded-xl flex items-center justify-center mx-auto mb-4 group-hover:scale-110 transition-transform duration-300">
            <span className="text-2xl"></span>
          </div>
          <h3 className="text-emerald-200 font-semibold text-lg mb-2">Smart Insights</h3>
          <p className="text-slate-300/70 text-sm leading-relaxed">
            AI-powered analysis and personalized recommendations for your wellbeing
          </p>
        </div>
        
        <div className="group bg-gradient-to-br from-rose-500/10 to-pink-500/10 backdrop-blur-sm rounded-2xl p-6 border border-rose-400/20 hover:border-rose-400/40 transition-all duration-300 hover:scale-105">
          <div className="w-12 h-12 bg-gradient-to-br from-rose-400 to-pink-500 rounded-xl flex items-center justify-center mx-auto mb-4 group-hover:scale-110 transition-transform duration-300">
            <span className="text-2xl">🌟</span>
          </div>
          <h3 className="text-rose-200 font-semibold text-lg mb-2">24/7 Support</h3>
          <p className="text-slate-300/70 text-sm leading-relaxed">
            Always here when you need someone to talk to, day or night
          </p>
        </div>
      </div>

      {/* Call to Action */}
      <div className="space-y-4">
        <div className="flex items-center justify-center gap-2 text-slate-300/60">
          <div className="w-2 h-2 bg-gradient-to-r from-violet-400 to-purple-400 rounded-full animate-pulse"></div>
          <span className="text-sm font-medium">Ready to begin your wellness journey?</span>
          <div className="w-2 h-2 bg-gradient-to-r from-purple-400 to-fuchsia-400 rounded-full animate-pulse"></div>
        </div>
        <p className="text-slate-400/80 text-sm">
          Start typing below to share your thoughts...
        </p>
      </div>
    </div>
  );
}


