import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";

/* helper */
const genSession = (id) => `${id}-${Math.random().toString(36).substring(2, 8)}`;

export default function LoginPage() {
  const [loginName, setLoginName] = useState("");
  const navigate = useNavigate();

  // Check for OAuth redirect parameters
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const username = urlParams.get('username');
    const email = urlParams.get('email');
    
    if (username && email) {
      // OAuth redirect detected, navigate to chat
      const sessionId = genSession(username);
      navigate(`/chat/${username}/${sessionId}`);
    }
  }, [navigate]);

  // Listen for OAuth success messages from popup
  useEffect(() => {
    const handleMessage = (event) => {
      if (event.data.type === 'GOOGLE_AUTH_SUCCESS') {
        const userEmail = event.data.userEmail;
        // Extract username from the current login name (this should be the username they entered)
        const username = loginName.trim().toLowerCase();
        const sessionId = genSession(username);
        navigate(`/chat/${username}/${sessionId}`);
      }
    };

    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [navigate]);

  // build OAuth URL using loginName as the state param
  const BACKEND = import.meta.env.VITE_API_BASE_URL || "https://web-production-0b6ce.up.railway.app";
  const getGoogleAuthUrl = () =>
    `${BACKEND}/google/auth/${encodeURIComponent(loginName.trim().toLowerCase())}`;

  const handleGoogleAuth = () => {
    // Force system browser to comply with Google's secure browser policy
    const authUrl = getGoogleAuthUrl();
    
    // Detect mobile devices
    const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
    
    if (isMobile) {
      // On mobile, use direct redirect to ensure system browser
      window.location.href = authUrl;
    } else {
      // On desktop, try popup first
      try {
        const newWindow = window.open(authUrl, '_blank', 'noopener,noreferrer');
        if (!newWindow || newWindow.closed || typeof newWindow.closed === 'undefined') {
          // Fallback to direct redirect
          window.location.href = authUrl;
        }
      } catch (e) {
        // Fallback to direct redirect
        window.location.href = authUrl;
      }
    }
  };

  const handleGuestLogin = () => {
    const id = loginName.trim().toLowerCase();
    const sessionId = genSession(id);
    navigate(`/chat/${id}/${sessionId}`);
  };

  return (
    <>
      {/* White screen overlay for desktop */}
      <div className="lg:fixed lg:inset-0 lg:bg-white lg:z-20"></div>

      <div className="w-full max-w-none lg:max-w-full flex items-center justify-center h-[87vh] lg:h-[calc(100vh-2rem)] relative overflow-y-hidden lg:z-30">
        <div className="glass-effect-strong lg:bg-white lg:shadow-none rounded-3xl lg:rounded-3xl p-6 lg:p-16 w-full h-full lg:max-w-full lg:w-full lg:h-auto text-center space-y-6 lg:space-y-6 border border-dark-500/10 lg:border-0 overflow-y-auto flex flex-col justify-center">
        {/* Logo and title */}
        <div className="space-y-4 lg:space-y-6">
          <div className="relative">
            <div className="w-24 h-24 lg:w-32 lg:h-32 bg-gradient-to-br from-accent-500 via-secondary-500 to-dark-500 rounded-full flex items-center justify-center mx-auto text-4xl lg:text-5xl shadow-2xl animate-pulse">
            </div>
          </div>
          <div>
            <h1 className="text-3xl lg:text-5xl font-bold text-gradient-violet mb-3">Aivis</h1>
            <p className="text-primary-900/60 text-sm lg:text-base"></p>
          </div>
        </div>

        {/* Username input */}
        <div className="space-y-3 lg:space-y-4 flex flex-col items-center">
          <input
            value={loginName}
            onChange={(e) => setLoginName(e.target.value)}
            placeholder="Choose a username"
            className="w-auto max-w-sm lg:w-auto lg:max-w-sm px-6 py-3 lg:px-6 lg:py-3.5 rounded-xl text-center text-primary-900 bg-secondary-500/10 placeholder-primary-900/40 border-0 focus:border-0 focus:outline-none focus:ring-0 focus:ring-offset-0 input-focus text-lg lg:text-base font-medium"
            onFocus={(e) => { e.target.style.border = 'none'; e.target.style.outline = 'none'; e.target.style.boxShadow = 'none'; }}
            style={{ border: 'none !important', outline: 'none !important', boxShadow: 'none !important' }}
          />

          {/* Sign in with Google */}
          <button
            disabled={!loginName.trim()}
            onClick={handleGoogleAuth}
            className="w-auto max-w-sm lg:w-auto lg:max-w-sm bg-gradient-to-r from-secondary-500 to-secondary-600 hover:from-secondary-600 hover:to-secondary-700 text-primary-50 px-4 py-3 lg:px-6 lg:py-3.5 rounded-xl disabled:opacity-50 btn-hover font-semibold flex items-center justify-center gap-3 shadow-lg border border-secondary-600/30 text-base lg:text-base"
          >
            <svg className="w-6 h-6 lg:w-7 lg:h-7" fill="currentColor" viewBox="0 0 24 24">
              <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
              <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
              <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
              <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
            </svg>
            <span>Sign in with Google</span>
          </button>

          <div className="flex items-center gap-4 lg:justify-center">
            <div className="flex-1 lg:flex-none lg:w-16 h-px bg-dark-500/20"></div>
            <span className="text-primary-900/50 text-sm font-medium">or</span>
            <div className="flex-1 lg:flex-none lg:w-16 h-px bg-dark-500/20"></div>
          </div>

          {/* Continue as guest */}
          <button
            disabled={!loginName.trim()}
            onClick={handleGuestLogin}
            className="w-auto max-w-sm lg:w-auto lg:max-w-sm bg-gradient-to-r from-accent-500 to-accent-600 hover:from-accent-600 hover:to-accent-700 text-primary-50 px-4 py-3 lg:px-6 lg:py-3.5 rounded-xl disabled:opacity-50 btn-hover font-semibold shadow-lg border border-accent-600/30 text-base lg:text-base"
          >
            Continue as "{loginName.trim().toLowerCase()}"
          </button>
        </div>

        {/* Features */}
        <div className="flex justify-center items-center gap-4 lg:gap-12 pt-4 lg:pt-6">
          <div className="text-center">
            <div className="w-12 h-12 lg:w-16 lg:h-16 bg-primary-200/60 rounded-full flex items-center justify-center mx-auto mb-2 border border-dark-500/10 text-lg lg:text-xl">
              <svg className="w-6 h-6 lg:w-8 lg:h-8 text-black" fill="currentColor" viewBox="0 0 24 24">
                <path d="M20 2H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h4l4 4 4-4h4c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-2 12H6v-2h12v2zm0-3H6V9h12v2zm0-3H6V6h12v2z"/>
              </svg>
            </div>
          </div>
          <div className="text-center">
            <div className="w-12 h-12 lg:w-16 lg:h-16 bg-primary-200/60 rounded-full flex items-center justify-center mx-auto mb-2 border border-dark-500/10 text-lg lg:text-xl">
              <svg className="w-6 h-6 lg:w-8 lg:h-8 text-black" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z"/>
                <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/>
              </svg>
            </div>
          </div>
          <div className="text-center">
            <div className="w-12 h-12 lg:w-16 lg:h-16 bg-primary-200/60 rounded-full flex items-center justify-center mx-auto mb-2 border border-dark-500/10 text-lg lg:text-xl">
              <svg className="w-6 h-6 lg:w-8 lg:h-8 text-black" fill="currentColor" viewBox="0 0 24 24">
                <path d="M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/>
              </svg>
            </div>
          </div>
        </div>
        </div>
      </div>
    </>
  );
}
