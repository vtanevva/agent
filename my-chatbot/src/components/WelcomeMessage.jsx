export default function WelcomeMessage() {
  return (
    <div className="text-center space-y-8 py-12">
      {/* Hero Section */}
      <div className="space-y-6">
        <div className="relative">
          <div className="w-24 h-24 bg-gradient-to-br from-accent-500 via-secondary-500 to-dark-500 rounded-full flex items-center justify-center mx-auto text-4xl shadow-2xl animate-pulse">
            AI
          </div>
          <div className="absolute -top-2 -right-2 w-8 h-8 bg-gradient-to-br from-accent-500 to-secondary-500 rounded-full flex items-center justify-center text-sm animate-bounce">
          </div>
        </div>
        
        <div className="space-y-4">
          <h2 className="text-3xl font-bold bg-gradient-to-r from-accent-600 via-secondary-600 to-dark-600 bg-clip-text text-transparent">
            Welcome to Mindful AI
          </h2>
          <p className="text-primary-900/80 text-lg max-w-2xl mx-auto leading-relaxed">
            Your compassionate AI companion for mental wellness. I'm here to listen, support, and guide you on your journey to better mental health.
          </p>
        </div>
      </div>

      {/* Features Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-4xl mx-auto">
        <div className="group bg-gradient-to-br from-accent-500/10 to-secondary-500/10 backdrop-blur-sm rounded-2xl p-6 border border-accent-500/20 hover:border-accent-500/40 transition-all duration-300 hover:scale-105">
          <div className="w-12 h-12 bg-gradient-to-br from-accent-500 to-secondary-500 rounded-xl flex items-center justify-center mx-auto mb-4 group-hover:scale-110 transition-transform duration-300">
            <span className="text-2xl">🧘</span>
          </div>
          <h3 className="text-accent-700 font-semibold text-lg mb-2">Mindful Conversations</h3>
          <p className="text-primary-900/70 text-sm leading-relaxed">
            Safe, confidential space for open dialogue about your thoughts and feelings
          </p>
        </div>
        
        <div className="group bg-gradient-to-br from-secondary-500/10 to-dark-500/10 backdrop-blur-sm rounded-2xl p-6 border border-secondary-500/20 hover:border-secondary-500/40 transition-all duration-300 hover:scale-105">
          <div className="w-12 h-12 bg-gradient-to-br from-secondary-500 to-dark-500 rounded-xl flex items-center justify-center mx-auto mb-4 group-hover:scale-110 transition-transform duration-300">
            <span className="text-2xl">💡</span>
          </div>
          <h3 className="text-secondary-700 font-semibold text-lg mb-2">Smart Insights</h3>
          <p className="text-primary-900/70 text-sm leading-relaxed">
            AI-powered analysis and personalized recommendations for your wellbeing
          </p>
        </div>
        
        <div className="group bg-gradient-to-br from-dark-500/10 to-accent-500/10 backdrop-blur-sm rounded-2xl p-6 border border-dark-500/20 hover:border-dark-500/40 transition-all duration-300 hover:scale-105">
          <div className="w-12 h-12 bg-gradient-to-br from-dark-500 to-accent-500 rounded-xl flex items-center justify-center mx-auto mb-4 group-hover:scale-110 transition-transform duration-300">
            <span className="text-2xl">🤝</span>
          </div>
          <h3 className="text-dark-600 font-semibold text-lg mb-2">24/7 Support</h3>
          <p className="text-primary-900/70 text-sm leading-relaxed">
            Always here when you need someone to talk to, day or night
          </p>
        </div>
      </div>

      {/* Call to Action */}
      <div className="space-y-4">
        <div className="flex items-center justify-center gap-2 text-primary-900/60">
          <div className="w-2 h-2 bg-gradient-to-r from-accent-500 to-secondary-500 rounded-full animate-pulse"></div>
          <span className="text-sm font-medium">Ready to begin your wellness journey?</span>
          <div className="w-2 h-2 bg-gradient-to-r from-secondary-500 to-dark-500 rounded-full animate-pulse"></div>
        </div>
        <p className="text-primary-900/60 text-sm">
          Start typing below to share your thoughts...
        </p>
      </div>
    </div>
  );
}


