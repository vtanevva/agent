"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import VoiceChat from "./VoiceChat";

import ChatHeader from "../components/ChatHeader";
import MessageList from "../components/MessageList";
import EmailList from "../components/EmailList";
import InputBar from "../components/InputBar";
import ConnectGoogleModal from "../components/ConnectGoogleModal";
import CalendarView from "../components/CalendarView";
import CalendarEvent from "../components/CalendarEvent";

export default function ChatPage() {
  const { userId, sessionId } = useParams();
  const navigate = useNavigate();
  
  // Add error boundary
  if (!userId) {
    console.error("No userId provided");
    return <div className="text-white">Error: No user ID provided</div>;
  }
  
  /* ── chat state ── */
  const [input, setInput] = useState("");
  const [chat, setChat] = useState([]);
  const [loading, setLoading] = useState(false);
  const [sessions, setSessions] = useState([]);
  const [selectedSession, setSelectedSession] = useState(null);
  const [useVoice, setUseVoice] = useState(false);
  const [emailChoices, setEmailChoices] = useState(null);
  const [showGoogleModal, setShowGoogleModal] = useState(false);
  const [googleConnectUrl, setGoogleConnectUrl] = useState("");
  const [showCalendar, setShowCalendar] = useState(false);
  const [calendarEvents, setCalendarEvents] = useState([]);
  const [calendarEvent, setCalendarEvent] = useState(null);
  const lastUserMessage = useRef("");

  /* ── refs & effects ── */
  const chatRef = useRef(null);
  useEffect(() => {
    if (chatRef.current) {
      chatRef.current.scrollTo({ top: chatRef.current.scrollHeight, behavior: "smooth" });
    }
  }, [chat, emailChoices]);

  // Function to load chat history for a session
  const loadSessionChat = useCallback(async (sessionId) => {
    if (!sessionId || !userId) {
      console.log("Missing sessionId or userId for loadSessionChat");
      return;
    }
    
    try {
      console.log("Loading chat for session:", sessionId);
      const r = await fetch("/api/session_chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, session_id: sessionId }),
      });
      
      if (!r.ok) {
        throw new Error(`HTTP error! status: ${r.status}`);
      }
      
      const { chat: dbChat = [] } = await r.json();
      const normal = dbChat.map((m) => ({ 
        role: m.role === "bot" ? "assistant" : m.role, 
        text: m.text 
      }));
      console.log("Loaded chat messages:", normal.length);
      
      if (normal.length === 0) {
        console.log("No chat history found - this is a new session");
      }
      
      setChat(normal);
    } catch (e) {
      console.error("Error loading session chat:", e);
      // If loading fails, start with empty chat (new session)
      setChat([]);
    }
  }, [userId]);

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
      const { sessions = [] } = await r.json();
      setSessions(sessions);
    } catch (err) {
      console.error("sessions", err);
    }
  }

  // Load sessions on component mount
  useEffect(() => {
    if (userId && userId !== 'undefined' && userId !== 'null') {
      fetchSessions(userId);
    }
  }, [userId]);

  // Refresh sessions list periodically to catch new conversations
  useEffect(() => {
    if (!userId) return;
    
    const interval = setInterval(() => {
      fetchSessions(userId);
    }, 30000); // Refresh every 30 seconds
    
    return () => clearInterval(interval);
  }, [userId]);

  // Handle session changes and load chat
  useEffect(() => {
    if (!sessionId || !userId) return;
    
    console.log("Session changed:", { sessionId, userId, sessionsCount: sessions.length });
    
    setEmailChoices(null);
    setSelectedSession(sessionId);
    
    // Always try to load chat history first
    // If it's empty, we know it's a new session
    loadSessionChat(sessionId);
  }, [sessionId, userId, loadSessionChat]);

  /* ── send handler ── */
  async function handleSend(msg = input) {
    console.log("handleSend called with:", msg);
    console.log("Current input:", input);
    console.log("Current loading state:", loading);
    
    if (!msg.trim()) {
      console.log("Message is empty, returning");
      return;
    }
    
    lastUserMessage.current = msg;
    setInput("");
    setChat((c) => [...c, { role: "user", text: msg }]);
    setLoading(true);
    
    console.log("Making API call to /api/chat");
    try {
      const requestBody = {
        message: msg,
        user_id: userId,
        session_id: sessionId,
      };
      console.log("Request body:", requestBody);
      
      const r = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestBody),
      });
      
      console.log("Response status:", r.status);
      console.log("Response headers:", Object.fromEntries(r.headers.entries()));
      
      const data = await r.json();
      console.log("Response data:", data);
      
      // Handle connect_google action
      if (data.action === "connect_google") {
        setGoogleConnectUrl(data.connect_url);
        setShowGoogleModal(true);
        setChat((c) => [...c, { role: "assistant", text: "To access your emails, please connect your Google account first." }]);
        return;
      }
      
      const { reply } = data;
      const cleaned = reply.replace(/```json|```/gi, "").trim();
      let parsed = null;
      try { parsed = JSON.parse(cleaned); } catch {}
      
      // Handle email choices
      if (Array.isArray(parsed) && parsed[0]?.threadId) {
        setEmailChoices(parsed);
      } 
      // Handle calendar events
      else if (parsed && parsed.success && parsed.events) {
        setCalendarEvents(parsed.events);
        setShowCalendar(true);
        setChat((c) => [...c, { role: "assistant", text: "📅 Here are your calendar events:" }]);
      } 
      // Handle regular text responses
      else {
        setEmailChoices(null);
        setChat((c) => [...c, { role: "assistant", text: reply }]);
      }
      
      // Refresh sessions list after sending a message to catch new sessions
      setTimeout(() => {
        fetchSessions(userId);
      }, 1000);
    } catch (e) {
      console.error("send error", e);
    } finally {
      setLoading(false);
    }
  }

  function handleEmailSelect(threadId, from) {
    const m = /<([^>]+)>/.exec(from);
    const to = m ? m[1] : from;
    setInput(`Reply to thread ${threadId} to ${to}: `);
    setEmailChoices(null);
  }

  const handleNewChat = () => {
    const newSessionId = `${userId}-${crypto.randomUUID().slice(0, 8)}`;
    setEmailChoices(null);
    setChat([]);
    setSelectedSession(newSessionId);
    
    // Add the new session to the sessions list immediately
    setSessions(prev => [...prev, newSessionId]);
    
    navigate(`/chat/${userId}/${newSessionId}`);
    
    // Refresh sessions list after a short delay to get the latest from server
    setTimeout(() => {
      fetchSessions(userId);
    }, 1000);
  };

  const handleLogout = () => {
    navigate("/");
  };

  const handleGoogleSuccess = () => {
    setShowGoogleModal(false);
    // Optionally retry the last message
    if (lastUserMessage.current) {
      handleSend(lastUserMessage.current);
    }
  };

  // Handle check emails button click
  const handleCheckEmails = async () => {
    // Trigger email fetching (handleSend will add the message to chat)
    await handleSend("Check my emails");
  };

  // Handle calendar button click
  const handleCheckCalendar = async () => {
    // Trigger calendar fetching (handleSend will add the message to chat)
    await handleSend("Show my calendar events");
  };

  // Handle calendar event click
  const handleCalendarEventClick = (event) => {
    setCalendarEvent(event);
  };

  /* ── VOICE MODE ── */
  if (useVoice) {
    return (
      <VoiceChat userId={userId} sessionId={sessionId} setUseVoice={setUseVoice} />
    );
  }

    /* ── MAIN CHAT ── */
  return (
    <div className="w-full max-w-7xl flex gap-6 h-[90vh]">
      {/* Sidebar */}
      <div className="w-80 flex flex-col gap-4 h-full overflow-y-auto custom-scrollbar">
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
                  {new Date().getDate()}/{new Date().getMonth() + 1}
                </div>
            </div>
          </div>
          
          <div className="mt-4 flex gap-2">
            <button
              onClick={() => setUseVoice(true)}
              className="flex-1 px-4 py-2 rounded-lg font-medium transition-all duration-300 bg-gradient-to-r from-emerald-500 to-teal-600 text-white btn-hover text-sm"
            >
              🎙️ Voice Mode
            </button>
            <button
              onClick={handleLogout}
              className="px-4 py-2 rounded-lg font-medium transition-all duration-300 bg-gradient-to-r from-red-500 to-red-600 text-white btn-hover text-sm"
            >
              Logout
            </button>
          </div>
        </div>

        {/* Mindful Conversations */}
        <div className="glass-effect-strong rounded-2xl p-4 shadow-glow">
          <h3 className="text-white font-semibold text-lg mb-3 flex items-center gap-2">
            Conversations
          </h3>
          <div className="space-y-2">
            <button 
              onClick={handleNewChat}
              className="w-full text-left px-3 py-2 rounded-lg bg-emerald-600/20 text-emerald-300 hover:bg-emerald-600/30 transition-all duration-200 text-sm"
            >
              + New Conversation
            </button>
            {sessions.length > 0 && (
              <div className="space-y-2">
                <div className="text-emerald-300 text-sm">Past Conversations:</div>
                <div className="max-h-32 overflow-y-auto transparent-scrollbar">
                  {sessions.map((session) => (
                    <button
                      key={session.session_id || session}
                      onClick={() => {
                        const id = session.session_id || session;
                        setSelectedSession(id);
                        setEmailChoices(null);
                        navigate(`/chat/${userId}/${id}`);
                        
                        // Refresh sessions list to ensure we have the latest data
                        setTimeout(() => {
                          fetchSessions(userId);
                        }, 500);
                      }}
                      className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-all duration-200 ${
                        selectedSession === (session.session_id || session)
                          ? "bg-emerald-600/30 text-emerald-300"
                          : "bg-emerald-600/10 text-emerald-400/70 hover:bg-emerald-600/20 hover:text-emerald-300"
                      }`}
                    >
                      {(session.session_id || session).slice(-8)}
                    </button>
                  ))}
                </div>
              </div>
            )}
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
            <button 
              onClick={handleCheckCalendar}
              className="w-full text-left px-3 py-2 rounded-lg bg-orange-600/20 text-orange-300 hover:bg-orange-600/30 transition-all duration-200 text-sm"
            >
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
                  <span className="font-medium">Memory Active</span>
                </div>
                <div className="text-xs text-slate-400">
                  {chat.length} messages in session
                </div>
              </div>
            </div>
            <div className="bg-slate-700/30 rounded-lg p-3">
              <div className="text-slate-300 text-sm">
                <div className="flex items-center gap-2 mb-1">
                  <div className="w-2 h-2 bg-blue-400 rounded-full"></div>
                  <span className="font-medium">Context Aware</span>
                </div>
                <div className="text-xs text-slate-400">
                  Personal facts remembered
                </div>
              </div>
            </div>
          </div>
        </div>


        {/* Session Stats */}
        <div className="glass-effect-strong rounded-2xl p-4 shadow-glow">
          <h3 className="text-white font-semibold text-lg mb-3 flex items-center gap-2">
            Session Stats
          </h3>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-slate-300">Messages:</span>
              <span className="text-emerald-400">{chat.length}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-300">Sessions:</span>
              <span className="text-blue-400">{sessions.length}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-300">Status:</span>
              <span className="text-emerald-400">Active</span>
            </div>
          </div>
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col glass-effect-strong rounded-3xl shadow-glow border border-slate-600/30">
        {/* Chat Header */}
        <div className="p-6 border-b border-slate-600/20">
          <div className="flex justify-between items-center">
            <div>
              <p className="text-white font-bold text-xl">Session: {sessionId?.slice(-8)}</p>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 bg-emerald-400 rounded-full animate-pulse"></div>
              <span className="text-emerald-400 text-sm font-medium">Online</span>
            </div>
          </div>
        </div>

        {/* Chat Messages */}
        <div ref={chatRef} className="flex-1 overflow-y-auto custom-scrollbar p-6">
          <MessageList chat={chat} loading={loading} />
          {emailChoices && <EmailList emails={emailChoices} onSelect={handleEmailSelect} />}
          {calendarEvent && (
            <div className="mt-4">
              <CalendarEvent 
                event={calendarEvent} 
                onEventClick={handleCalendarEventClick}
              />
            </div>
          )}
        </div>

        {/* Input Area */}
        <div className="p-6 border-t border-slate-600/20">
          <InputBar
            input={input}
            setInput={setInput}
            loading={loading}
            onSend={handleSend}
            showConnectButton={false}
            onConnect={() => {}}
          />
        </div>
      </div>

      {/* Google Connect Modal */}
      <ConnectGoogleModal
        isOpen={showGoogleModal}
        onRequestClose={() => setShowGoogleModal(false)}
        connectUrl={googleConnectUrl}
        onSuccess={handleGoogleSuccess}
      />

      {/* Calendar Modal */}
      {showCalendar && (
        <CalendarView
          events={calendarEvents}
          onEventClick={handleCalendarEventClick}
          onClose={() => setShowCalendar(false)}
        />
      )}
    </div>
  );
}
