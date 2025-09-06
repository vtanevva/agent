export default function WelcomeMessage() {
  return (
    <div className="text-center space-y-8 py-12">
      {/* Hero Section */}
      <div className="space-y-6">
        <div className="relative">
          <div className="w-24 h-24 bg-gradient-to-br from-accent-500 via-secondary-500 to-dark-500 rounded-full flex items-center justify-center mx-auto text-4xl shadow-2xl animate-pulse">
          </div>
        </div>
        
        <div className="space-y-4">
          <h2 className="text-3xl font-bold bg-gradient-to-r from-accent-600 via-secondary-600 to-dark-600 bg-clip-text text-transparent">
            Welcome to Aivis
          </h2>
          <p className="text-primary-900/80 text-lg max-w-2xl mx-auto leading-relaxed">
            Your compassionate AI companion for mental wellness. 
          </p>
        </div>
      </div>

      {/* Features Grid */}
      {/* Mobile: Icons only */}
      <div className="flex justify-center items-center gap-8 md:hidden">
        <div className="w-12 h-12 bg-gradient-to-br from-accent-500 to-secondary-500 rounded-xl flex items-center justify-center">
          <svg className="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>
        </div>
        <div className="w-12 h-12 bg-gradient-to-br from-secondary-500 to-dark-500 rounded-xl flex items-center justify-center">
          <svg className="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M9 21c0 .55.45 1 1 1h4c.55 0 1-.45 1-1v-1H9v1zm3-19C8.14 2 5 5.14 5 9c0 2.38 1.19 4.47 3 5.74V17c0 .55.45 1 1 1h6c.55 0 1-.45 1-1v-2.26c1.81-1.27 3-3.36 3-5.74 0-3.86-3.14-7-7-7zm2.85 11.1l-.85.6V16h-4v-2.3l-.85-.6C7.8 12.16 7 10.63 7 9c0-2.76 2.24-5 5-5s5 2.24 5 5c0 1.63-.8 3.16-2.15 4.1z"/></svg>
        </div>
        <div className="w-12 h-12 bg-gradient-to-br from-dark-500 to-accent-500 rounded-xl flex items-center justify-center">
          <svg className="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M16 4c0-1.11.89-2 2-2s2 .89 2 2-.89 2-2 2-2-.89-2-2zm4 18v-6h2.5l-2.54-7.63A1.5 1.5 0 0 0 18.54 8H17c-.8 0-1.54.37-2.01.99L14 10.5l-1.5-2c-.47-.62-1.21-.99-2.01-.99H9.46c-.8 0-1.54.37-2.01.99L6 10.5l-1.5-2C4.03 7.88 3.29 7.51 2.49 7.51H1.5L4.04 15.13A1.5 1.5 0 0 0 5.5 16H7v6h2v-6h2.5l1.5 2.5L14 16h2v6h2zm-8-8c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2z"/></svg>
        </div>
      </div>

      {/* Desktop: Full cards */}
      <div className="hidden md:grid grid-cols-3 gap-6 max-w-4xl mx-auto">
        <div className="group bg-gradient-to-br from-accent-500/10 to-secondary-500/10 backdrop-blur-sm rounded-2xl p-6 border border-accent-500/20 hover:border-accent-500/40 transition-all duration-300 hover:scale-105">
          <div className="w-12 h-12 bg-gradient-to-br from-accent-500 to-secondary-500 rounded-xl flex items-center justify-center mx-auto mb-4 group-hover:scale-110 transition-transform duration-300">
            <svg className="w-8 h-8 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>
          </div>
          <h3 className="text-accent-700 font-semibold text-lg mb-2">Mindful Conversations</h3>
          <p className="text-primary-900/70 text-sm leading-relaxed">
            Safe, confidential space for open dialogue about your thoughts and feelings
          </p>
        </div>
        
        <div className="group bg-gradient-to-br from-secondary-500/10 to-dark-500/10 backdrop-blur-sm rounded-2xl p-6 border border-secondary-500/20 hover:border-secondary-500/40 transition-all duration-300 hover:scale-105">
          <div className="w-12 h-12 bg-gradient-to-br from-secondary-500 to-dark-500 rounded-xl flex items-center justify-center mx-auto mb-4 group-hover:scale-110 transition-transform duration-300">
            <svg className="w-8 h-8 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M9 21c0 .55.45 1 1 1h4c.55 0 1-.45 1-1v-1H9v1zm3-19C8.14 2 5 5.14 5 9c0 2.38 1.19 4.47 3 5.74V17c0 .55.45 1 1 1h6c.55 0 1-.45 1-1v-2.26c1.81-1.27 3-3.36 3-5.74 0-3.86-3.14-7-7-7zm2.85 11.1l-.85.6V16h-4v-2.3l-.85-.6C7.8 12.16 7 10.63 7 9c0-2.76 2.24-5 5-5s5 2.24 5 5c0 1.63-.8 3.16-2.15 4.1z"/></svg>
          </div>
          <h3 className="text-secondary-700 font-semibold text-lg mb-2">Smart Insights</h3>
          <p className="text-primary-900/70 text-sm leading-relaxed">
            AI-powered analysis and personalized recommendations for your wellbeing
          </p>
        </div>
        
        <div className="group bg-gradient-to-br from-dark-500/10 to-accent-500/10 backdrop-blur-sm rounded-2xl p-6 border border-dark-500/20 hover:border-dark-500/40 transition-all duration-300 hover:scale-105">
          <div className="w-12 h-12 bg-gradient-to-br from-dark-500 to-accent-500 rounded-xl flex items-center justify-center mx-auto mb-4 group-hover:scale-110 transition-transform duration-300">
            <svg className="w-8 h-8 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M16 4c0-1.11.89-2 2-2s2 .89 2 2-.89 2-2 2-2-.89-2-2zm4 18v-6h2.5l-2.54-7.63A1.5 1.5 0 0 0 18.54 8H17c-.8 0-1.54.37-2.01.99L14 10.5l-1.5-2c-.47-.62-1.21-.99-2.01-.99H9.46c-.8 0-1.54.37-2.01.99L6 10.5l-1.5-2C4.03 7.88 3.29 7.51 2.49 7.51H1.5L4.04 15.13A1.5 1.5 0 0 0 5.5 16H7v6h2v-6h2.5l1.5 2.5L14 16h2v6h2zm-8-8c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2z"/></svg>
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
          <span className="text-sm font-medium">Ready to begin?</span>
          <div className="w-2 h-2 bg-gradient-to-r from-secondary-500 to-dark-500 rounded-full animate-pulse"></div>
        </div>
        <p className="text-primary-900/60 text-sm">
          Start typing below to share your thoughts...
        </p>
      </div>
    </div>
  );
}


