
import { useState, useRef, useEffect } from "react"
import { useNavigate } from "react-router-dom"
import axios from "axios"
import EmailList from "../components/EmailList"

export default function VoiceChat({ userId: rawUserId, sessionId, setUseVoice }) {
  // Decode the userId if it's URL encoded
  const userId = rawUserId ? decodeURIComponent(rawUserId) : rawUserId;
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
  const [showSidebar, setShowSidebar] = useState(false)
  const lastUserMessage = useRef("")

  const recognitionRef = useRef(null)
  const chatContainerRef = useRef(null)
  const navigate = useNavigate()

  // Listen for OAuth success messages from popup
  useEffect(() => {
    const handleMessage = (event) => {
      if (event.data.type === 'GOOGLE_AUTH_SUCCESS') {
        // User successfully authenticated, retry the last message
        if (lastUserMessage.current) {
          handleSend(lastUserMessage.current);
        }
      }
    };

    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, []);

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

  // Note: Email choices are now restored from chat history when loading sessions

  // Function to extract email choices from chat history
  const extractEmailChoicesFromChat = (chatHistory) => {
    // Look for the last assistant message that contains email data
    for (let i = chatHistory.length - 1; i >= 0; i--) {
      const msg = chatHistory[i];
      if (msg.role === "assistant") {
        const cleaned = msg.text.replace(/```json\n?|\n?```/g, '').trim();
        let parsed = null;
        try { 
          parsed = JSON.parse(cleaned); 
        } catch {}
        if (Array.isArray(parsed) && parsed[0]?.threadId) {
          return parsed;
        }
      }
    }
    return null;
  };

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
          
          // Only set email choices for the current session
          const emailData = extractEmailChoicesFromChat(normal);
          setEmailChoices(emailData);
        } catch (e) {
          console.error("load session chat", e);
          // If session doesn't exist yet, start with empty chat
          setChat([]);
          setEmailChoices(null);
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
        setChat(prev => [...prev, { role: "assistant", text: "Opening Google authentication in system browser..." }]);
        setLoading(false);
        // Force system browser to comply with Google's secure browser policy
        try {
          const newWindow = window.open(res.data.connect_url, '_blank', 'noopener,noreferrer');
          if (!newWindow || newWindow.closed || typeof newWindow.closed === 'undefined') {
            // Fallback to direct redirect
            window.location.href = res.data.connect_url;
          }
        } catch (e) {
          // Fallback to direct redirect
          window.location.href = res.data.connect_url;
        }
        return;
      }
      
      let reply = (res.data && typeof res.data.reply !== 'undefined') ? res.data.reply : undefined;
      if (!reply && Array.isArray(res.data)) {
        reply = JSON.stringify(res.data);
      }
      if (reply == null) reply = "";
      if (typeof reply !== 'string') {
        try { reply = JSON.stringify(reply); } catch { reply = String(reply); }
      }
      const cleaned = String(reply).replace(/```json|```/gi, "").trim();
      let parsed = null;
      try { parsed = JSON.parse(cleaned); } catch {}
      if (Array.isArray(parsed) && parsed[0]?.threadId) {
        setEmailChoices(parsed);
        // Also push assistant reply so inline UI can render at the right place
        setChat(prev => [...prev, { role: "assistant", text: reply }])
      } else {
        // Try markdown formatted list (e.g., numbered with **From:** etc.)
        const md = cleaned.replace(/\r\n/g, '\n');
        const re = /\n?\s*\d+\.\s+\*\*From:\*\*\s*([\s\S]*?)\n\s*\*\*Subject:\*\*\s*([\s\S]*?)\n\s*\*\*Snippet:\*\*\s*([\s\S]*?)(?=\n\s*\d+\.\s|$)/g;
        let m; let idx = 1; const items = [];
        while ((m = re.exec(md)) !== null) {
          const from = m[1].trim();
          const subject = m[2].trim();
          const snippet = m[3].trim();
          items.push({ idx, from, subject, snippet, threadId: `md-${idx}` });
          idx += 1;
        }
        if (items.length > 0) {
          setEmailChoices(items);
          setChat(prev => [...prev, { role: "assistant", text: reply }])
        } else {
          setEmailChoices(null);
          setChat(prev => [...prev, { role: "assistant", text: reply }])
        }
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


  return (
    <div className="w-full max-w-full lg:max-w-full flex gap-6 h-[87vh] lg:h-[calc(100vh-2rem)] relative overflow-hidden overflow-y-hidden">
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
        w-full lg:w-80 
        h-full 
        z-50 lg:z-0
        flex flex-col gap-3 
        overflow-y-auto custom-scrollbar
        bg-white lg:bg-transparent 
        backdrop-blur-none
        transition-transform duration-300 ease-in-out
        p-2 lg:p-0
      `}>
        <div className="w-96 sm:w-[28rem] lg:w-full mx-auto">
        {/* Mobile close button */}
        <button
          onClick={() => setShowSidebar(false)}
          className="lg:hidden absolute top-6 right-10 text-gray-600 hover:text-gray-800 z-10 p-2"
        >
          ✕
        </button>

        {/* User Profile Section */}
        <div className="glass-effect-strong rounded-xl p-4 sm:p-4 border border-dark-500/10 mb-4 sm:mb-4">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 bg-gradient-to-br from-accent-500 via-secondary-500 to-dark-500 rounded-full flex items-center justify-center text-primary-50 font-bold text-lg shadow-lg">
              {userId.charAt(0).toUpperCase()}
            </div>
            <div>
              <div className="text-primary-900 font-semibold text-lg">
                {userId}
              </div>
              <div className="text-primary-900/60 text-sm">
                Voice Session: {sessionId?.slice(-8)}
              </div>
            </div>
          </div>
          
          <div className="mt-4 sm:mt-3 flex gap-2">
            <button
              onClick={() => {
                console.log('Text Mode clicked - closing sidebar');
                setUseVoice(false);
                setShowSidebar(false);
              }}
              className="flex-1 px-4 py-3 sm:px-3 sm:py-2 rounded-lg font-medium transition-all duration-300 bg-gradient-to-r from-secondary-500 to-secondary-600 text-primary-50 btn-hover text-base sm:text-sm"
            >
              Text Mode
            </button>
            <button
              onClick={() => {
                handleLogout();
                setShowSidebar(false);
              }}
              className="px-4 py-3 sm:px-3 sm:py-2 rounded-lg font-medium transition-all duration-300 bg-gradient-to-r from-dark-500 to-dark-600 text-primary-50 btn-hover text-base sm:text-sm"
            >
              Logout
            </button>
          </div>
        </div>

        {/* Voice Controls */}
        <div className="glass-effect-strong rounded-xl p-4 sm:p-4 border border-dark-500/10 mb-4 sm:mb-4">
          <h3 className="text-primary-900 font-semibold text-xl sm:text-xl mb-4 sm:mb-4 flex items-center gap-2">
            Voice Controls
          </h3>
          <div className="space-y-4">
            <button
              onClick={() => {
                if (isListening) {
                  stopListening();
                } else {
                  startListening();
                }
                setShowSidebar(false);
              }}
              disabled={!isSupported}
              className={`w-full py-4 sm:py-3 rounded-lg flex items-center justify-center gap-2 font-medium transition-all duration-300 ${
                isListening
                  ? "bg-gradient-to-r from-dark-500 to-dark-600 text-primary-50 animate-pulse"
                  : "bg-gradient-to-r from-secondary-500 to-secondary-600 text-primary-50 hover:from-secondary-600 hover:to-secondary-700"
              } ${!isSupported ? "opacity-50 cursor-not-allowed" : "btn-hover"}`}
            >
              {isListening ? "Stop Listening" : "Start Listening"}
            </button>
            
            {isSpeaking && (
              <button 
                onClick={() => {
                  stopSpeaking();
                  setShowSidebar(false);
                }} 
                className="w-full py-4 sm:py-3 rounded-lg flex items-center justify-center gap-2 font-medium transition-all duration-300 bg-gradient-to-r from-accent-500 to-accent-600 text-primary-50 btn-hover"
              >
                Stop Speaking
              </button>
            )}
            
            <div className="text-center p-3 sm:p-2 bg-secondary-500/20 rounded-lg border border-dark-500/5">
              <div className="text-primary-900 font-medium text-sm sm:text-xs">
                {isListening ? "Listening..." : isSpeaking ? "Speaking..." : "Ready to listen"}
              </div>
              <div className="text-primary-900/60 text-sm sm:text-xs mt-1">
                {isListening ? "Speak now..." : isSpeaking ? "AI is responding..." : "Click to start"}
              </div>
            </div>
          </div>
        </div>

        {/* Chat Toggle */}
        <div className="glass-effect-strong rounded-xl p-4 sm:p-4 border border-dark-500/10 mb-4 sm:mb-4">
          <h3 className="text-primary-900 font-semibold text-xl sm:text-xl mb-4 sm:mb-4 flex items-center gap-2">
            Chat Display
          </h3>
          <button
            onClick={() => {
              setShowChat(!showChat);
              setShowSidebar(false);
            }}
            className="w-full px-4 py-4 sm:px-3 sm:py-3 rounded-lg font-medium transition-all duration-300 bg-gradient-to-r from-dark-500 to-dark-600 text-primary-50 btn-hover text-lg sm:text-base"
          >
            {showChat ? "Hide Chat" : "Show Chat"}
          </button>
        </div>

        {/* Voice Sessions */}
        <div className="glass-effect-strong rounded-xl p-4 sm:p-4 border border-dark-500/10 mb-4 sm:mb-4">
          <h3 className="text-primary-900 font-semibold text-xl sm:text-xl mb-4 sm:mb-4 flex items-center gap-2">
            Mindful Voice
          </h3>
          <div className="space-y-4">
            <button 
              onClick={() => {
                handleNewChat();
                setShowSidebar(false);
              }}
              className="w-full text-left px-4 py-4 sm:px-3 sm:py-3 rounded-lg bg-secondary-500/20 text-secondary-700 hover:bg-secondary-500/30 transition-all duration-200 text-lg sm:text-base"
            >
              New Voice Session
            </button>
            {sessions.length > 0 && (
              <div className="space-y-4">
                <div className="text-secondary-600 text-lg sm:text-base">Past Sessions:</div>
                <div className="max-h-48 overflow-y-auto custom-scrollbar space-y-2">
                  {sessions.map((session) => (
                    <button
                      key={session.session_id || session}
                      onClick={async () => {
                        console.log('Past conversation clicked - closing sidebar');
                        setShowSidebar(false); // Close menu on mobile FIRST
                        const id = session.session_id || session;
                        setSelectedSession(id);
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
                          
                          // Only set email choices if this is the current session, not for past conversations
                          if (id === sessionId) {
                            const emailData = extractEmailChoicesFromChat(normal);
                            setEmailChoices(emailData);
                          } else {
                            setEmailChoices(null);
                          }
                        } catch (e) {
                          console.error("load session", e);
                          setEmailChoices(null);
                        }
                      }}
                      className={`w-full text-left px-4 py-4 sm:px-3 sm:py-3 rounded-lg text-lg sm:text-base transition-all duration-200 ${
                        selectedSession === (session.session_id || session)
                          ? "bg-secondary-500/30 text-secondary-700"
                          : "bg-secondary-500/10 text-secondary-600/70 hover:bg-secondary-500/20 hover:text-secondary-700"
                      }`}
                    >
                      {(session.session_id || session).slice(-8)}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <div className="text-xs text-primary-900/60 p-2 bg-primary-200/20 rounded border border-dark-500/5">
              Voice conversations are saved automatically
            </div>
          </div>
        </div>

        {/* Voice Settings */}
        <div className="glass-effect-strong rounded-xl p-4 sm:p-4 border border-dark-500/10 mb-4 sm:mb-4">
          <h3 className="text-primary-900 font-semibold text-xl sm:text-xl mb-4 sm:mb-4 flex items-center gap-2">
            Voice Settings
          </h3>
          <div className="space-y-4">
            <div className="bg-accent-500/20 rounded-lg px-4 py-5 sm:px-3 sm:py-4 border border-dark-500/5">
              <div className="text-primary-900 text-lg sm:text-base">
                <div className="flex items-center gap-2 mb-1">
                  <div className="w-2 h-2 sm:w-1.5 sm:h-1.5 bg-secondary-500 rounded-full"></div>
                  <span className="font-medium">Auto-playback</span>
                </div>
                <div className="text-base sm:text-sm text-primary-900/60">
                  AI responses play automatically
                </div>
              </div>
            </div>
            <div className="bg-accent-500/20 rounded-lg px-4 py-5 sm:px-3 sm:py-4 border border-dark-500/5">
              <div className="text-primary-900 text-lg sm:text-base">
                <div className="flex items-center gap-2 mb-1">
                  <div className="w-2 h-2 sm:w-1.5 sm:h-1.5 bg-accent-500 rounded-full"></div>
                  <span className="font-medium">Voice Recognition</span>
                </div>
                <div className="text-base sm:text-sm text-primary-900/60">
                  High accuracy mode enabled
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Email Integration */}
        <div className="glass-effect-strong rounded-xl p-4 sm:p-4 border border-dark-500/10 mb-4 sm:mb-4">
          <h3 className="text-primary-900 font-semibold text-xl sm:text-xl mb-4 sm:mb-4 flex items-center gap-2">
            Quick Actions
          </h3>
          <div className="space-y-4">
            <button 
              onClick={() => {
                handleCheckEmails();
                setShowSidebar(false);
              }}
              className="w-full text-left px-4 py-4 sm:px-3 sm:py-3 rounded-lg bg-accent-500/20 text-accent-700 hover:bg-accent-500/30 transition-all duration-200 text-lg sm:text-base"
            >
              Check Emails
            </button>
            <button 
              onClick={() => {
                setShowSidebar(false);
              }}
              className="w-full text-left px-4 py-4 sm:px-3 sm:py-3 rounded-lg bg-secondary-500/20 text-secondary-700 hover:bg-secondary-500/30 transition-all duration-200 text-lg sm:text-base"
            >
              Calendar Events
            </button>
            <button 
              onClick={() => {
                setShowSidebar(false);
              }}
              className="w-full text-left px-4 py-4 sm:px-3 sm:py-3 rounded-lg bg-dark-500/20 text-dark-600 hover:bg-dark-500/30 transition-all duration-200 text-lg sm:text-base"
            >
              Compose Email
            </button>
          </div>
        </div>

        {/* Smart Insights */}
        <div className="glass-effect-strong rounded-xl p-4 sm:p-4 border border-dark-500/10 mb-4 sm:mb-4">
          <h3 className="text-primary-900 font-semibold text-xl sm:text-xl mb-4 sm:mb-4 flex items-center gap-2">
            Smart Insights
          </h3>
          <div className="space-y-4 sm:space-y-3">
            <div className="bg-accent-500/20 rounded-lg px-4 py-5 sm:px-3 sm:py-4 border border-dark-500/5">
              <div className="text-primary-900 text-lg sm:text-base">
                <div className="flex items-center gap-2 mb-1">
                  <div className="w-2 h-2 sm:w-1.5 sm:h-1.5 bg-secondary-500 rounded-full"></div>
                  <span className="font-medium">Voice Session Active</span>
                </div>
                <div className="text-base sm:text-sm text-primary-900/60">
                  {chat.length} messages in current session
                </div>
              </div>
            </div>
            <div className="bg-accent-500/20 rounded-lg px-4 py-5 sm:px-3 sm:py-4 border border-dark-500/5">
              <div className="text-primary-900 text-lg sm:text-base">
                <div className="flex items-center gap-2 mb-1">
                  <div className="w-2 h-2 sm:w-1.5 sm:h-1.5 bg-accent-500 rounded-full"></div>
                  <span className="font-medium">Voice Mode</span>
                </div>
                <div className="text-base sm:text-sm text-primary-900/60">
                  {isSupported ? "Fully supported" : "Limited support"}
                </div>
              </div>
            </div>
            <div className="bg-accent-500/20 rounded-lg px-4 py-5 sm:px-3 sm:py-4 border border-dark-500/5">
              <div className="text-primary-900 text-lg sm:text-base">
                <div className="flex items-center gap-2 mb-1">
                  <div className="w-2 h-2 sm:w-1.5 sm:h-1.5 bg-dark-500 rounded-full"></div>
                  <span className="font-medium">Sessions</span>
                </div>
                <div className="text-base sm:text-sm text-primary-900/60">
                  {sessions.length} conversations saved
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Voice Status */}
        <div className="glass-effect-strong rounded-xl p-4 sm:p-4 border border-dark-500/10 mb-4 sm:mb-4">
          <h3 className="text-primary-900 font-semibold text-xl sm:text-xl mb-4 sm:mb-4 flex items-center gap-2">
            Status
          </h3>
          <div className="space-y-3 sm:space-y-2 text-lg sm:text-base">
            <div className="flex justify-between">
              <span className="text-primary-900/70 text-lg sm:text-base">Chat:</span>
              <span className={`text-lg sm:text-base ${showChat ? "text-secondary-600" : "text-primary-900/40"}`}>
                {showChat ? "Visible" : "Hidden"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-primary-900/70 text-lg sm:text-base">Speaking:</span>
              <span className={`text-lg sm:text-base ${isSpeaking ? "text-secondary-600" : "text-primary-900/40"}`}>
                {isSpeaking ? "Yes" : "No"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-primary-900/70 text-lg sm:text-base">Listening:</span>
              <span className={`text-lg sm:text-base ${isListening ? "text-secondary-600" : "text-primary-900/40"}`}>
                {isListening ? "Yes" : "No"}
              </span>
            </div>
            {!isSupported && (
              <div className="mt-2 p-2 bg-dark-500/20 rounded text-dark-600 text-xs border border-dark-500/30">
                Voice features not supported
              </div>
            )}
          </div>
        </div>
        </div>
      </div>

      {/* Main Voice Chat Area */}
      <div className="flex-1 w-full h-full lg:flex-1 lg:w-auto lg:h-auto flex flex-col glass-effect-strong rounded-3xl lg:rounded-3xl border border-dark-500/20 lg:ml-0 ml-0 max-w-full overflow-hidden">
        {/* Chat Header */}
        <div className="p-3 lg:p-4 border-b border-dark-500/10">
          <div className="flex justify-between items-center">
            <div className="flex items-center gap-3">
              {/* Mobile menu button */}
              <button
                onClick={() => setShowSidebar(true)}
                className="lg:hidden text-primary-900 hover:text-primary-900/70 p-2 -ml-2"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                </svg>
              </button>
              <div>
                <h2 className="text-primary-900 font-bold text-lg lg:text-xl">Voice Chat</h2>
                <p className="text-primary-900/70 text-sm"></p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-secondary-600 text-sm font-medium"></span>
            </div>
          </div>
        </div>

        {/* Chat Messages */}
        {showChat && (
          <div ref={chatContainerRef} className="flex-1 overflow-y-auto custom-scrollbar p-3 lg:p-4">
            <div className="space-y-6">
              {chat.map((msg, idx) => (
                <div
                  key={idx}
                  className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"} message-enter`}
                >
                  <div
                    className={`max-w-xs lg:max-w-md px-4 lg:px-6 py-3 lg:py-4 rounded-2xl shadow-lg border ${
                      msg.role === "user"
                        ? "glass-effect-violet text-primary-900 rounded-br-md shadow-glow border-accent-500/20"
                        : "glass-effect-emerald text-primary-900 rounded-bl-md shadow-glow-emerald border-secondary-500/20"
                    }`}
                  >
                    <div className="flex items-start gap-4">
                      {/* Avatar */}
                      <div className={`w-10 h-10 rounded-full flex items-center justify-center text-sm font-semibold ${
                        msg.role === "user" 
                          ? "bg-gradient-to-br from-accent-500 to-accent-600 shadow-lg text-primary-50" 
                          : "bg-gradient-to-br from-secondary-500 to-secondary-600 shadow-lg text-primary-50"
                      }`}>
                        {msg.role === "user" ? (
                          <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd" d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z" clipRule="evenodd" />
                          </svg>
                        ) : (
                          <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd" d="M10 2a8 8 0 100 16 8 8 0 000-16zM7 8a1 1 0 100-2 1 1 0 000 2zm6 0a1 1 0 100-2 1 1 0 000 2zM7 12a1 1 0 100-2 1 1 0 000 2zm6 0a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
                            <path d="M8 6h4v1H8V6z" />
                          </svg>
                        )}
                      </div>
                      
                      {/* Message content */}
                      <div className="flex-1 min-w-0">
                        <div className={`text-sm font-semibold mb-2 ${
                          msg.role === "user" ? "text-accent-700" : "text-secondary-700"
                        }`}>
                          {msg.role === "user" ? "You" : "Aivis"}
                        </div>
                        {(() => {
                          if (msg.role === "assistant" && typeof msg.text === "string") {
                            const sanitize = (s) => s.replace(/,\s*(?=[}\]])/g, "").replace(/'/g, '"');
                            const noFences = msg.text.replace(/```[a-zA-Z]*\r?\n?|```/g, '').trim();
                            // Try full parse first
                            try {
                              const parsed = JSON.parse(noFences);
                              if (Array.isArray(parsed) && (parsed[0]?.threadId || parsed.find?.(e=>e?.threadId))) {
                                return (
                                  <div className="mt-1">
                                    <EmailList emails={parsed} onSelect={handleEmailSelect} />
                                  </div>
                                );
                              }
                            } catch {}
                            // Try to extract first balanced array
                            const start = noFences.indexOf('[');
                            if (start !== -1) {
                              let depth = 0;
                              for (let i = start; i < noFences.length; i++) {
                                const ch = noFences[i];
                                if (ch === '[') depth++; else if (ch === ']') depth--;
                                if (depth === 0) {
                                  let candidate = noFences.slice(start, i + 1);
                                  candidate = sanitize(candidate);
                                  try {
                                    const parsed = JSON.parse(candidate);
                                    if (Array.isArray(parsed) && (parsed[0]?.threadId || parsed.find?.(e=>e?.threadId))) {
                                      return (
                                        <div className="mt-1">
                                          <EmailList emails={parsed} onSelect={handleEmailSelect} />
                                        </div>
                                      );
                                    }
                                  } catch {}
                                  break;
                                }
                              }
                            }
                            // Last resort: sanitize whole
                            try {
                              const parsed = JSON.parse(sanitize(noFences));
                              if (Array.isArray(parsed) && (parsed[0]?.threadId || parsed.find?.(e=>e?.threadId))) {
                                return (
                                  <div className="mt-1">
                                    <EmailList emails={parsed} onSelect={handleEmailSelect} />
                                  </div>
                                );
                              }
                            } catch {}
                          }
                          return (
                            <div className={`text-sm leading-relaxed whitespace-pre-wrap ${
                              msg.role === "user" ? "text-primary-900" : "text-primary-900"
                            }`}>
                              {msg.text}
                            </div>
                          );
                        })()}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
              {loading && (
                <div className="flex justify-start">
                  <div className="glass-effect-emerald text-primary-900 rounded-2xl rounded-bl-md shadow-glow-emerald px-6 py-4 border border-secondary-500/20">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-full bg-gradient-to-br from-secondary-500 to-secondary-600 shadow-lg flex items-center justify-center">
                        AI
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-secondary-700 font-medium">Thinking...</span>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* AI Speaking Animation (when chat is hidden) */}
        {!showChat && isSpeaking && (
          <div className="flex-1 flex items-center justify-center" style={{ minHeight: '400px' }}>
            <div className="text-center space-y-6">
              <div className="w-32 h-32 bg-gradient-to-br from-dark-500/40 via-dark-600/40 to-dark-700/40 rounded-full flex items-center justify-center mx-auto">
              </div>
              <div className="text-primary-900/80 text-lg font-medium text-center">
                AI is speaking...
              </div>
            </div>
          </div>
        )}

        {/* Placeholder when chat is hidden and AI is not speaking */}
        {!showChat && !isSpeaking && (
          <div className="flex-1 flex items-center justify-center" style={{ minHeight: '400px' }}>
            <div className="text-center space-y-6">
              <div className="w-32 h-32 bg-gradient-to-br from-accent-500/20 via-secondary-500/20 to-dark-500/20 rounded-full flex items-center justify-center mx-auto">
              </div>
              <div className="text-primary-900/60 text-lg">
                Click to start speaking
              </div>
              
              {/* Microphone Section */}
              <div className="flex flex-col items-center gap-2">
                <button
                  onClick={isListening ? stopListening : startListening}
                  disabled={!isSupported}
                  className={`w-16 h-16 lg:w-18 lg:h-18 rounded-full font-semibold flex items-center justify-center shadow-lg transition-all duration-300 ${
                    isListening
                      ? "bg-white hover:bg-gray-100 text-secondary-600 animate-pulse"
                      : "bg-gradient-to-r from-secondary-500 to-secondary-600 hover:from-secondary-600 hover:to-secondary-700 text-primary-50"
                  } ${!isSupported ? "opacity-50 cursor-not-allowed" : "btn-hover"}`}
                >
                  <svg className="w-6 h-6 lg:w-7 lg:h-7" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z"/>
                    <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/>
                  </svg>
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Input Area */}
        <div className="p-4 lg:p-6 border-t border-dark-500/10">
          <div className="p-3 lg:p-1">
            <div className="flex flex-col sm:flex-row gap-3 lg:gap-4 items-stretch sm:items-end lg:items-end">
            <div className="flex-1 relative">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                onFocus={(e) => {
                  e.target.style.border = 'none';
                  e.target.style.outline = 'none';
                  e.target.style.boxShadow = 'none';
                }}
                className="w-full px-4 lg:px-6 py-3 lg:py-4 rounded-xl text-primary-900 bg-primary-100/50 placeholder-primary-900/40 border-0 focus:border-0 focus:outline-none focus:ring-0 focus:ring-offset-0 resize-none focus:bg-primary-100/70 transition-all duration-300 text-sm lg:text-base overflow-y-hidden"
                placeholder={isListening ? "Listening..." : "Type your message or use voice..."}
                rows="1"
                style={{
                  minHeight: '48px',
                  maxHeight: '120px',
                  height: '48px',
                  border: 'none !important',
                  outline: 'none !important',
                  boxShadow: 'none !important'
                }}
              />
            </div>
            <button
              onClick={() => {
                console.log("Send button clicked");
                console.log("Current input:", input);
                console.log("Loading state:", loading);
                console.log("Input trimmed:", input.trim());
                handleSend();
              }}
              disabled={loading || !input.trim()}
              className="bg-gradient-to-r from-accent-500 to-accent-600 hover:from-accent-600 hover:to-accent-700 text-primary-50 px-6 lg:px-8 py-3 lg:py-4 rounded-xl disabled:opacity-50 disabled:cursor-not-allowed btn-hover font-semibold flex items-center justify-center gap-2 lg:gap-3 shadow-lg border border-accent-600/30 text-sm lg:text-base min-h-[48px]"
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
      </div>

    </div>
  )
}
