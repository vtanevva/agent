import { useState } from "react";
import { useNavigate } from "react-router-dom";
import ConnectGoogleModal from "../components/ConnectGoogleModal";

/* helper */
const genSession = (id) => `${id}-${crypto.randomUUID().slice(0, 8)}`;

export default function LoginPage() {
  const [loginName, setLoginName] = useState("");
  const [showGoogleModal, setShowGoogleModal] = useState(false);
  const [googleConnectUrl, setGoogleConnectUrl] = useState("");
  const navigate = useNavigate();

  // build OAuth URL using loginName as the state param
  const BACKEND = import.meta.env.VITE_API_BASE_URL || "http://localhost:10000";
  const getGoogleAuthUrl = () =>
    `${BACKEND}/google/auth/${encodeURIComponent(loginName.trim().toLowerCase())}`;

  const handleGoogleSuccess = async () => {
    setShowGoogleModal(false);
    let realEmail;
    try {
      const r = await fetch("/api/google-profile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: loginName.trim().toLowerCase() }),
      });
      const { email } = await r.json();
      realEmail = email;
    } catch (err) {
      console.error("could not fetch google profile:", err);
    }
    const id = realEmail || loginName.trim().toLowerCase();
    const sessionId = genSession(id);
    navigate(`/chat/${id}/${sessionId}`);
  };

  const handleGuestLogin = () => {
    const id = loginName.trim().toLowerCase();
    const sessionId = genSession(id);
    navigate(`/chat/${id}/${sessionId}`);
  };

  return (
    <>
      <ConnectGoogleModal
        isOpen={showGoogleModal}
        connectUrl={googleConnectUrl}
        onRequestClose={() => setShowGoogleModal(false)}
        onSuccess={handleGoogleSuccess}
      />

      <div className="glass-effect-strong rounded-3xl p-8 max-w-md w-full text-center space-y-8 shadow-glow">
        {/* Logo and title */}
        <div className="space-y-6">
          <div className="relative">
            <div className="w-24 h-24 bg-gradient-to-br from-violet-500 via-purple-500 to-fuchsia-500 rounded-full flex items-center justify-center mx-auto text-4xl shadow-2xl animate-pulse">
              🌸
            </div>
            <div className="absolute -top-2 -right-2 w-8 h-8 bg-gradient-to-br from-pink-400 to-rose-500 rounded-full flex items-center justify-center text-sm animate-bounce">
              ✨
            </div>
          </div>
          <div>
            <h1 className="text-3xl font-bold text-gradient-violet mb-3">Aivis</h1>
            <p className="text-slate-200/80 text-sm"></p>
          </div>
        </div>

        {/* Username input */}
        <div className="space-y-4">
          <input
            value={loginName}
            onChange={(e) => setLoginName(e.target.value)}
            placeholder="Choose a username"
            className="w-full px-6 py-4 rounded-xl text-center text-white bg-slate-800/50 placeholder-slate-300/60 border border-slate-600/30 focus:border-violet-400/50 input-focus text-lg font-medium"
          />

          {/* Sign in with Google */}
          <button
            disabled={!loginName.trim()}
            onClick={() => {
              setGoogleConnectUrl(getGoogleAuthUrl());
              setShowGoogleModal(true);
            }}
            className="w-full bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-600 hover:to-teal-700 text-white px-6 py-4 rounded-xl disabled:opacity-50 btn-hover font-semibold flex items-center justify-center gap-3 shadow-lg"
          >
            <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
              <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
              <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
              <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
              <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
            </svg>
            <span>Sign in with Google</span>
          </button>

          <div className="flex items-center gap-4">
            <div className="flex-1 h-px bg-slate-600/30"></div>
            <span className="text-slate-300/60 text-sm font-medium">or</span>
            <div className="flex-1 h-px bg-slate-600/30"></div>
          </div>

          {/* Continue as guest */}
          <button
            disabled={!loginName.trim()}
            onClick={handleGuestLogin}
            className="w-full bg-gradient-to-r from-violet-500 to-purple-600 hover:from-violet-600 hover:to-purple-700 text-white px-6 py-4 rounded-xl disabled:opacity-50 btn-hover font-semibold shadow-lg"
          >
            Continue as "{loginName.trim().toLowerCase()}"
          </button>
        </div>

        {/* Features */}
        <div className="grid grid-cols-3 gap-4 pt-4">
          <div className="text-center">
            <div className="w-8 h-8 bg-slate-700/50 rounded-full flex items-center justify-center mx-auto mb-2">
              💬
            </div>
            <p className="text-slate-300/60 text-xs">Chat</p>
          </div>
          <div className="text-center">
            <div className="w-8 h-8 bg-slate-700/50 rounded-full flex items-center justify-center mx-auto mb-2">
              🎙️
            </div>
            <p className="text-slate-300/60 text-xs">Voice</p>
          </div>
          <div className="text-center">
            <div className="w-8 h-8 bg-slate-700/50 rounded-full flex items-center justify-center mx-auto mb-2">
              📧
            </div>
            <p className="text-slate-300/60 text-xs">Email</p>
          </div>
        </div>
      </div>
    </>
  );
}
