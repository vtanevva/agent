import { BrowserRouter, Routes, Route } from "react-router-dom";
import LoginPage from "./pages/LoginPage";
import ChatPage from "./pages/ChatPage";

export default function App() {
  return (
    <div className="h-screen relative overflow-hidden bg-secondary-500/20">
      {/* Minimalistic Background */}
      <div className="fixed inset-0">
        {/* Base background */}
        <div className="absolute inset-0 bg-secondary-500/20"></div>
        
        {/* Subtle gradient overlay */}
        <div className="absolute inset-0 bg-gradient-to-br from-primary-50 via-primary-100 to-primary-200 opacity-60"></div>
        
        {/* Floating organic shapes */}
        <div className="absolute inset-0">
          {[...Array(8)].map((_, i) => (
            <div
              key={i}
              className="absolute rounded-full blur-xl opacity-10 animate-pulse"
              style={{
                left: `${Math.random() * 100}%`,
                top: `${Math.random() * 100}%`,
                width: `${Math.random() * 200 + 80}px`,
                height: `${Math.random() * 200 + 80}px`,
                background: `radial-gradient(circle, ${
                  ['#012622', '#775B59', '#32161F'][Math.floor(Math.random() * 3)]
                }15, transparent)`,
                animationDelay: `${Math.random() * 8}s`,
                animationDuration: `${Math.random() * 15 + 15}s`
              }}
            />
          ))}
        </div>

        {/* Minimalistic geometric patterns */}
        <div className="absolute inset-0 opacity-3">
          <div className="absolute top-20 left-20 w-20 h-20 border border-dark-500/20 rotate-45 rounded-lg"></div>
          <div className="absolute top-40 right-32 w-16 h-16 border border-secondary-500/20 rounded-full"></div>
          <div className="absolute bottom-32 left-32 w-24 h-24 border border-accent-500/20 rotate-12 rounded-lg"></div>
          <div className="absolute bottom-20 right-20 w-18 h-18 border border-dark-500/20 transform rotate-45 rounded-full"></div>
        </div>

        {/* Subtle texture overlay */}
        <div className="absolute inset-0 opacity-20">
          <div className="w-full h-full" style={{
            backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E")`,
          }}></div>
        </div>
      </div>

      {/* Main content */}
      <div className="relative z-10 h-full flex flex-col items-center justify-center pt-0 px-2 pb-14 lg:p-4 lg:items-stretch lg:justify-start overflow-hidden">
        <Routes>
          <Route path="/" element={<LoginPage />} />
          <Route path="/chat/:userId/:sessionId" element={<ChatPage />} />
        </Routes>
      </div>

      {/* Subtle ambient effects */}
      <div className="fixed top-0 left-1/4 w-64 h-64 bg-accent-500/5 rounded-full blur-3xl animate-pulse"></div>
      <div className="fixed bottom-0 right-1/4 w-64 h-64 bg-secondary-500/5 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '3s' }}></div>
    </div>
  );
}
