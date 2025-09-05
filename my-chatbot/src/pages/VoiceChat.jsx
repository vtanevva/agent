
import { useState, useRef, useEffect } from "react"
import { useNavigate } from "react-router-dom"
import axios from "axios"
import EmailList from "../components/EmailList"
import ConnectGoogleModal from "../components/ConnectGoogleModal"
import AISpeakerBubble from "../components/AISpeakerBubble"

export default function VoiceChat({ userId, sessionId, setUseVoice }) {
  const [chat, setChat] = useState([])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const [isListening, setIsListening] = useState(false)
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [isSupported, setIsSupported] = useState(false)
  const [showChat, setShowChat] = useState(false)
  const [sessions, setSessions] = useState([])
  const [selectedSession, setSelectedSession] = useState(sessionId)
  const [emailChoices, setEmailChoices] = useState(null)
  const [showGoogleModal, setShowGoogleModal] = useState(false)
  const [googleConnectUrl, setGoogleConnectUrl] = useState("")
  const [showSidebar, setShowSidebar] = useState(false)
  const lastUserMessage = useRef("")

  const recognitionRef = useRef(null)
  const chatContainerRef = useRef(null)
  const navigate = useNavigate()

  // Fetch sessions function
  async function fetchSessions(id = userId) {
    if (!id || id === 'undefined' || id === 'null') {
      console.log("No valid userId, skipping fetchSessions");
      return;
    }
    try {
      const r = await fetch("/api/sessions-log", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: id }),
      });
      if (!r.ok) {
        throw new Error(`HTTP error! status: ${r.status}`);
      }
      const { sessions: sessionData = [] } = await r.json();
      setSessions(sessionData);
    } catch (err) {
      console.error("Error fetching sessions:", err);
    }
  }

  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    setIsSupported(!!SpeechRecognition && !!window.speechSynthesis)

    if (SpeechRecognition) {
      recognitionRef.current = new SpeechRecognition()
      recognitionRef.current.continuous = false
      recognitionRef.current.interimResults = false
      recognitionRef.current.lang = "en-US"

      recognitionRef.current.onresult = (event) => {
        const transcript = event.results[0][0].transcript
        setInput(transcript)
        setIsListening(false)
        setTimeout(() => handleSend(transcript), 100)
      }

      recognitionRef.current.onerror = () => setIsListening(false)
      recognitionRef.current.onend = () => setIsListening(false)
    }
  }, [])

  useEffect(() => {
    chatContainerRef.current?.scrollTo({ top: chatContainerRef.current.scrollHeight, behavior: "smooth" })
  }, [chat, emailChoices])

  // Load sessions when component mounts
  useEffect(() => {
    if (userId && userId !== 'undefined' && userId !== 'null') {
      fetchSessions(userId);
    }
  }, [userId]);

  // Clear email choices when session changes
  useEffect(() => {
    setEmailChoices(null);
  }, [sessionId]);

  // Load current session's chat when component mounts or sessionId changes
  useEffect(() => {
    if (userId && sessionId) {
      const loadSessionChat = async () => {
        try {
          const r = await fetch("/api/session_chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ user_id: userId, session_id: sessionId }),
          });
          const { chat: dbChat = [] } = await r.json();
          const normal = dbChat.map((m) => ({ role: m.role === "bot" ? "assistant" : m.role, text: m.text }));
          setChat(normal);
        } catch (e) {
          console.error("load session chat", e);
          // If session doesn't exist yet, start with empty chat
          setChat([]);
        }
      };
      loadSessionChat();
      setSelectedSession(sessionId);
    }
  }, [userId, sessionId]);

  useEffect(() => {
    const last = chat.at(-1)
    if (last?.role === "assistant" && !isSpeaking) speak(last.text)
  }, [chat])

  const speak = (text) => {
    if (!window.speechSynthesis) return
    console.log("Starting to speak:", text.substring(0, 50) + "...")
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.rate = 0.9
    utterance.pitch = 1
    utterance.volume = 0.8
    utterance.onend = () => {
      console.log("Speech ended")
      setIsSpeaking(false)
    }
    utterance.onerror = () => {
      console.log("Speech error")
      setIsSpeaking(false)
    }
    setIsSpeaking(true)
    window.speechSynthesis.speak(utterance)
  }

  const handleSend = async (msg = input) => {
    if (!msg.trim()) return
    const isFirstMessage = chat.length === 0
    lastUserMessage.current = msg
    setChat(prev => [...prev, { role: "user", text: msg }])
    setInput("")
    setLoading(true)

    try {
      const res = await axios.post("/api/chat", {
        message: msg,
        user_id: userId,
        session_id: sessionId,
      })
      
      // Handle connect_google action
      if (res.data.action === "connect_google") {
        setGoogleConnectUrl(res.data.connect_url);
        setShowGoogleModal(true);
        setChat(prev => [...prev, { role: "assistant", text: "To access your emails, please connect your Google account first." }]);
        setLoading(false);
        return;
      }
      
      const reply = res.data.reply
      const cleaned = reply.replace(/```json|```/gi, "").trim();
      let parsed = null;
      try { parsed = JSON.parse(cleaned); } catch {}
      if (Array.isArray(parsed) && parsed[0]?.threadId) {
        setEmailChoices(parsed);
      } else {
        setEmailChoices(null);
        setChat(prev => [...prev, { role: "assistant", text: reply }])
      }
      
      // If this was the first message in a new session, refresh the sessions list
      if (isFirstMessage) {
        setTimeout(() => fetchSessions(userId), 1000);
      }
    } catch (err) {
      console.error("Backend error:", err)
    }
    setLoading(false)
  }

  const startListening = () => {
    if (recognitionRef.current && !isListening) {
      setIsListening(true)
      recognitionRef.current.start()
    }
  }

  const stopListening = () => {
    recognitionRef.current?.stop()
    setIsListening(false)
  }

  const stopSpeaking = () => {
    window.speechSynthesis.cancel()
    setIsSpeaking(false)
  }

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleNewChat = () => {
    const newSessionId = `${userId}-${crypto.randomUUID().slice(0, 8)}`;
    setChat([]); // Clear current chat
    setEmailChoices(null); // Clear emails when starting new chat
    // Navigate to new chat session (voice mode is maintained in ChatPage state)
    navigate(`/chat/${userId}/${newSessionId}`);
    // Refresh sessions after a short delay to ensure the new session gets created
    setTimeout(() => fetchSessions(userId), 500);
  };

  const handleLogout = () => {
    navigate("/");
  };

  // Handle check emails button click
  const handleCheckEmails = async () => {
    // Trigger email fetching (handleSend will add the message to chat)
    await handleSend("Check my emails");
  };

  // Handle email selection
  function handleEmailSelect(threadId, from) {
    const m = /<([^>]+)>/.exec(from);
    const to = m ? m[1] : from;
    setInput(`Reply to thread ${threadId} to ${to}: `);
    setEmailChoices(null);
  }

  // Handle Google OAuth success
  const handleGoogleSuccess = () => {
    setShowGoogleModal(false);
    // Optionally retry the last message
    if (lastUserMessage.current) {
      handleSend(lastUserMessage.current);
    }
  };

  return (
    <div className="w-full max-w-7xl flex gap-6 h-[90vh] relative">
      {/* Mobile overlay */}
      {showSidebar && (
        <div 
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={() => setShowSidebar(false)}
        />
      )}

      {/* Sidebar */}
      <div className={`
        ${showSidebar ? 'translate-x-0' : '-translate-x-full'} 
        lg:translate-x-0 
        fixed lg:static 
        top-0 left-0 
        w-80 
        h-full 
        z-50 lg:z-0
        flex flex-col gap-4 
        overflow-y-auto custom-scrollbar
        bg-slate-900/95 lg:bg-transparent 
        backdrop-blur-md lg:backdrop-blur-none
        transition-transform duration-300 ease-in-out
        p-4 lg:p-0
      `}>
        {/* Mobile close button */}
        <button
          onClick={() => setShowSidebar(false)}
          className="lg:hidden absolute top-4 right-4 text-white hover:text-gray-300 z-10 bg-slate-800/50 rounded-full p-2"
        >
          ✕
        </button>

        {/* User Profile Section */}
        <div className="glass-effect-strong rounded-2xl p-4 shadow-glow">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 bg-gradient-to-br from-violet-400 via-purple-500 to-fuchsia-500 rounded-full flex items-center justify-center text-white font-bold text-lg shadow-lg">
              {userId.charAt(0).toUpperCase()}
            </div>
            <div>
              <div className="text-white font-semibold text-lg">
                {userId}
              </div>
              <div className="text-slate-300/60 text-sm">
                Voice Session: {sessionId?.slice(-8)}
              </div>
            </div>
          </div>
          
          <div className="mt-4 flex gap-2">
            <button
              onClick={() => setUseVoice(false)}
              className="flex-1 px-4 py-2 rounded-lg font-medium transition-all duration-300 bg-gradient-to-r from-emerald-500 to-teal-600 text-white btn-hover text-sm"
            >
              ← Text Mode
            </button>
            <button
              onClick={handleLogout}
              className="px-4 py-2 rounded-lg font-medium transition-all duration-300 bg-gradient-to-r from-red-500 to-red-600 text-white btn-hover text-sm"
            >
              Logout
            </button>
          </div>
        </div>

        {/* Voice Controls */}
        <div className="glass-effect-strong rounded-2xl p-4 shadow-glow">
          <h3 className="text-white font-semibold text-lg mb-3 flex items-center gap-2">
            🎙️ Voice Controls
          </h3>
          <div className="space-y-3">
            <button
              onClick={isListening ? stopListening : startListening}
              disabled={!isSupported}
              className={`w-full py-3 rounded-lg flex items-center justify-center gap-2 font-medium transition-all duration-300 ${
                isListening
                  ? "bg-gradient-to-r from-red-500 to-red-600 text-white animate-pulse"
                  : "bg-gradient-to-r from-emerald-500 to-teal-600 text-white hover:from-emerald-600 hover:to-teal-700"
              } ${!isSupported ? "opacity-50 cursor-not-allowed" : "btn-hover"}`}
            >
              {isListening ? "🔴 Stop Listening" : "🎤 Start Listening"}
            </button>
            
            {isSpeaking && (
              <button 
                onClick={stopSpeaking} 
                className="w-full py-3 rounded-lg flex items-center justify-center gap-2 font-medium transition-all duration-300 bg-gradient-to-r from-yellow-500 to-orange-600 text-white btn-hover"
              >
                🔇 Stop Speaking
              </button>
            )}
            
            <div className="text-center p-3 bg-slate-700/30 rounded-lg">
              <div className="text-white font-medium text-sm">
                {isListening ? "Listening..." : isSpeaking ? "Speaking..." : "Ready to listen"}
              </div>
              <div className="text-slate-300/60 text-xs mt-1">
                {isListening ? "Speak now..." : isSpeaking ? "AI is responding..." : "Click to start"}
              </div>
            </div>
          </div>
        </div>

        {/* Chat Toggle */}
        <div className="glass-effect-strong rounded-2xl p-4 shadow-glow">
          <h3 className="text-white font-semibold text-lg mb-3 flex items-center gap-2">
            💬 Chat Display
          </h3>
          <button
            onClick={() => setShowChat(!showChat)}
            className="w-full px-4 py-2 rounded-lg font-medium transition-all duration-300 bg-gradient-to-r from-violet-500 to-purple-600 text-white btn-hover text-sm"
          >
            {showChat ? "Hide Chat" : "Show Chat"}
          </button>
        </div>

        {/* Voice Sessions */}
        <div className="glass-effect-strong rounded-2xl p-4 shadow-glow">
          <h3 className="text-white font-semibold text-lg mb-3 flex items-center gap-2">
            Mindful Voice
          </h3>
          <div className="space-y-2">
            <button 
              onClick={handleNewChat}
              className="w-full text-left px-3 py-2 rounded-lg bg-slate-700/30 text-slate-300 hover:bg-slate-600/40 transition-all duration-200 text-sm"
            >
              + New Voice Session
            </button>
            {sessions.length > 0 && (
              <div className="space-y-2">
                <div className="text-slate-300 text-sm">Past Sessions:</div>
                <div className="max-h-32 overflow-y-auto custom-scrollbar">
                  {sessions.map((session) => (
                    <button
                      key={session.session_id || session}
                      onClick={async () => {
                        const id = session.session_id || session;
                        setSelectedSession(id);
                        setEmailChoices(null); // Clear emails when switching sessions
                        navigate(`/chat/${userId}/${id}`);
                        try {
                          const r = await fetch("/api/session_chat", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ user_id: userId, session_id: id }),
                          });
                          const { chat: dbChat = [] } = await r.json();
                          const normal = dbChat.map((m) => ({ role: m.role === "bot" ? "assistant" : m.role, text: m.text }));
                          setChat(normal);
                        } catch (e) {
                          console.error("load session", e);
                        }
                      }}
                      className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-all duration-200 ${
                        selectedSession === (session.session_id || session)
                          ? "bg-emerald-600/30 text-emerald-300"
                          : "bg-slate-700/30 text-slate-400 hover:bg-slate-600/40 hover:text-slate-300"
                      }`}
                    >
                      {(session.session_id || session).slice(-8)}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <div className="text-xs text-slate-400 p-2 bg-slate-700/20 rounded">
              Voice conversations are saved automatically
            </div>
          </div>
        </div>

        {/* Voice Settings */}
        <div className="glass-effect-strong rounded-2xl p-4 shadow-glow">
          <h3 className="text-white font-semibold text-lg mb-3 flex items-center gap-2">
            Voice Settings
          </h3>
          <div className="space-y-2">
            <div className="bg-slate-700/30 rounded-lg p-3">
              <div className="text-slate-300 text-sm">
                <div className="flex items-center gap-2 mb-1">
                  <div className="w-2 h-2 bg-emerald-400 rounded-full"></div>
                  <span className="font-medium">Auto-playback</span>
                </div>
                <div className="text-xs text-slate-400">
                  AI responses play automatically
                </div>
              </div>
            </div>
            <div className="bg-slate-700/30 rounded-lg p-3">
              <div className="text-slate-300 text-sm">
                <div className="flex items-center gap-2 mb-1">
                  <div className="w-2 h-2 bg-blue-400 rounded-full"></div>
                  <span className="font-medium">Voice Recognition</span>
                </div>
                <div className="text-xs text-slate-400">
                  High accuracy mode enabled
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Email Integration */}
        <div className="glass-effect-strong rounded-2xl p-4 shadow-glow">
          <h3 className="text-white font-semibold text-lg mb-3 flex items-center gap-2">
            Quick Actions
          </h3>
          <div className="space-y-2">
            <button 
              onClick={handleCheckEmails}
              className="w-full text-left px-3 py-2 rounded-lg bg-violet-600/20 text-violet-300 hover:bg-violet-600/30 transition-all duration-200 text-sm"
            >
              Check Emails
            </button>
            <button className="w-full text-left px-3 py-2 rounded-lg bg-orange-600/20 text-orange-300 hover:bg-orange-600/30 transition-all duration-200 text-sm">
              Calendar Events
            </button>
            <button className="w-full text-left px-3 py-2 rounded-lg bg-pink-600/20 text-pink-300 hover:bg-pink-600/30 transition-all duration-200 text-sm">
              Compose Email
            </button>
          </div>
        </div>

        {/* Smart Insights */}
        <div className="glass-effect-strong rounded-2xl p-4 shadow-glow">
          <h3 className="text-white font-semibold text-lg mb-3 flex items-center gap-2">
            Smart Insights
          </h3>
          <div className="space-y-2">
            <div className="bg-slate-700/30 rounded-lg p-3">
              <div className="text-slate-300 text-sm">
                <div className="flex items-center gap-2 mb-1">
                  <div className="w-2 h-2 bg-emerald-400 rounded-full"></div>
                  <span className="font-medium">Voice Session Active</span>
                </div>
                <div className="text-xs text-slate-400">
                  {chat.length} messages in current session
                </div>
              </div>
            </div>
            <div className="bg-slate-700/30 rounded-lg p-3">
              <div className="text-slate-300 text-sm">
                <div className="flex items-center gap-2 mb-1">
                  <div className="w-2 h-2 bg-violet-400 rounded-full"></div>
                  <span className="font-medium">Voice Mode</span>
                </div>
                <div className="text-xs text-slate-400">
                  {isSupported ? "Fully supported" : "Limited support"}
                </div>
              </div>
            </div>
            <div className="bg-slate-700/30 rounded-lg p-3">
              <div className="text-slate-300 text-sm">
                <div className="flex items-center gap-2 mb-1">
                  <div className="w-2 h-2 bg-blue-400 rounded-full"></div>
                  <span className="font-medium">Sessions</span>
                </div>
                <div className="text-xs text-slate-400">
                  {sessions.length} conversations saved
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Voice Status */}
        <div className="glass-effect-strong rounded-2xl p-4 shadow-glow">
          <h3 className="text-white font-semibold text-lg mb-3 flex items-center gap-2">
            Status
          </h3>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-slate-300">Chat:</span>
              <span className={showChat ? "text-emerald-400" : "text-slate-400"}>
                {showChat ? "Visible" : "Hidden"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-300">Speaking:</span>
              <span className={isSpeaking ? "text-emerald-400" : "text-slate-400"}>
                {isSpeaking ? "Yes" : "No"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-300">Listening:</span>
              <span className={isListening ? "text-emerald-400" : "text-slate-400"}>
                {isListening ? "Yes" : "No"}
              </span>
            </div>
            {!isSupported && (
              <div className="mt-2 p-2 bg-red-500/20 rounded text-red-300 text-xs">
                Voice features not supported
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Main Voice Chat Area */}
      <div className="flex-1 flex flex-col glass-effect-strong rounded-3xl shadow-glow border border-slate-600/30 lg:ml-0 ml-0">
        {/* Chat Header */}
        <div className="p-4 lg:p-6 border-b border-slate-600/20">
          <div className="flex justify-between items-center">
            <div className="flex items-center gap-3">
              {/* Mobile menu button */}
              <button
                onClick={() => setShowSidebar(true)}
                className="lg:hidden text-white hover:text-gray-300 p-2 -ml-2"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                </svg>
              </button>
              <div>
                <h2 className="text-white font-bold text-lg lg:text-xl">Voice Chat</h2>
                <p className="text-slate-300/70 text-sm"></p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 bg-emerald-400 rounded-full animate-pulse"></div>
              <span className="text-emerald-400 text-sm font-medium">Voice Active</span>
            </div>
          </div>
        </div>

        {/* Chat Messages */}
        {showChat && (
          <div ref={chatContainerRef} className="flex-1 overflow-y-auto custom-scrollbar p-4 lg:p-6">
            <div className="space-y-6">
              {chat.map((msg, idx) => (
                <div
                  key={idx}
                  className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"} message-enter`}
                >
                  <div
                    className={`max-w-xs lg:max-w-md px-4 lg:px-6 py-3 lg:py-4 rounded-2xl shadow-lg ${
                      msg.role === "user"
                        ? "glass-effect-violet text-white rounded-br-md shadow-glow"
                        : "glass-effect-emerald text-slate-800 rounded-bl-md shadow-glow-emerald"
                    }`}
                  >
                    <div className="flex items-start gap-4">
                      {/* Avatar */}
                      <div className={`w-10 h-10 rounded-full flex items-center justify-center text-sm font-semibold ${
                        msg.role === "user" 
                          ? "bg-gradient-to-br from-violet-400 to-purple-500 shadow-lg" 
                          : "bg-gradient-to-br from-emerald-400 to-teal-500 shadow-lg"
                      }`}>
                        {msg.role === "user" ? "👤" : "🌸"}
                      </div>
                      
                      {/* Message content */}
                      <div className="flex-1 min-w-0">
                        <div className={`text-sm font-semibold mb-2 ${
                          msg.role === "user" ? "text-violet-100" : "text-emerald-800"
                        }`}>
                          {msg.role === "user" ? "You" : "Mindful AI"}
                        </div>
                        <div className={`text-sm leading-relaxed whitespace-pre-wrap ${
                          msg.role === "user" ? "text-white" : "text-slate-700"
                        }`}>
                          {msg.text}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
              
              {loading && (
                <div className="flex justify-start">
                  <div className="glass-effect-emerald text-slate-800 rounded-2xl rounded-bl-md shadow-glow-emerald px-6 py-4">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-full bg-gradient-to-br from-emerald-400 to-teal-500 shadow-lg flex items-center justify-center">
                        
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-emerald-800 font-medium">Thinking...</span>
                      </div>
                    </div>
                  </div>
                </div>
              )}
              
              {emailChoices && <EmailList emails={emailChoices} onSelect={handleEmailSelect} />}
            </div>
          </div>
        )}

        {/* AI Speaking Animation (when chat is hidden) */}
        {!showChat && isSpeaking && (
          <div className="flex-1 flex items-center justify-center" style={{ minHeight: '400px' }}>
            <div className="text-center space-y-6">
              {/* AI Speaker Bubble */}
              <div className="flex justify-center">
                <AISpeakerBubble isSpeaking={isSpeaking} className="scale-150" />
              </div>
              
              <div className="text-white/80 text-lg font-medium">
              </div>
              

            </div>
          </div>
        )}

        {/* Placeholder when chat is hidden and AI is not speaking */}
        {!showChat && !isSpeaking && (
          <div className="flex-1 flex items-center justify-center" style={{ minHeight: '400px' }}>
            <div className="text-center space-y-6">
              <div className="w-32 h-32 bg-gradient-to-br from-violet-400/20 via-purple-500/20 to-fuchsia-500/20 rounded-full flex items-center justify-center mx-auto">
                <div className="text-4xl">🎙️</div>
              </div>
              <div className="text-white/60 text-lg">
                Click the microphone to start speaking
              </div>
            </div>
          </div>
        )}

        {/* Input Area */}
        <div className="p-4 lg:p-6 border-t border-slate-600/20">
          <div className="flex flex-col sm:flex-row gap-3 lg:gap-4 items-stretch sm:items-end">
            <div className="flex-1 relative">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                className="w-full px-4 lg:px-6 py-3 lg:py-4 rounded-xl text-white bg-slate-800/50 placeholder-slate-300/60 border border-slate-600/30 focus:border-violet-400/50 input-focus resize-none focus:bg-slate-800/70 transition-all duration-300 text-sm lg:text-base"
                placeholder={isListening ? "Listening..." : "Type your message or use voice..."}
                rows="1"
                style={{
                  minHeight: '48px',
                  maxHeight: '120px'
                }}
              />
            </div>
            <button
              onClick={() => handleSend()}
              disabled={loading || !input.trim()}
              className="bg-gradient-to-r from-violet-500 to-purple-600 hover:from-violet-600 hover:to-purple-700 text-white px-6 lg:px-8 py-3 lg:py-4 rounded-xl disabled:opacity-50 disabled:cursor-not-allowed btn-hover font-semibold flex items-center justify-center gap-2 lg:gap-3 shadow-lg text-sm lg:text-base min-h-[48px]"
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
          </div>
        </div>
      </div>

      {/* Google Connect Modal */}
      <ConnectGoogleModal
        isOpen={showGoogleModal}
        onRequestClose={() => setShowGoogleModal(false)}
        connectUrl={googleConnectUrl}
        onSuccess={handleGoogleSuccess}
      />
    </div>
  )
}
