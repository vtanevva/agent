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
  const [showSidebar, setShowSidebar] = useState(false);
  const lastUserMessage = useRef("");

  /* ── refs & effects ── */
  const chatRef = useRef(null);
  useEffect(() => {
    if (chatRef.current) {
      chatRef.current.scrollTo({ top: chatRef.current.scrollHeight, behavior: "smooth" });
    }
  }, [chat, emailChoices]);

  // Function to extract email choices from chat history
  const extractEmailChoicesFromChat = useCallback((chatHistory) => {
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
  }, []);

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
      
      // Check if there are email choices in the chat history
      const emailData = extractEmailChoicesFromChat(normal);
      setEmailChoices(emailData);
    } catch (e) {
      console.error("Error loading session chat:", e);
      // If loading fails, start with empty chat (new session)
      setChat([]);
      setEmailChoices(null);
    }
  }, [userId, extractEmailChoicesFromChat]);

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
        setLoading(false);
        return;
      }
      
      let reply = (data && typeof data.reply !== 'undefined') ? data.reply : undefined;
      if (!reply && Array.isArray(data)) {
        // Backend might have returned the array directly
        reply = JSON.stringify(data);
      }
      if (reply == null) reply = "";
      if (typeof reply !== 'string') {
        try { reply = JSON.stringify(reply); } catch { reply = String(reply); }
      }
      const cleaned = String(reply).replace(/```json|```/gi, "").trim();
      let parsed = null;
      try { parsed = JSON.parse(cleaned); } catch {}
      
      // Handle email choices
      if (Array.isArray(parsed) && parsed[0]?.threadId) {
        setEmailChoices(parsed);
        // Also add the assistant message so inline UI can render at the correct position
        setChat((c) => [...c, { role: "assistant", text: reply }]);
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
    <div className="w-full max-w-full lg:max-w-full flex gap-6 h-[90vh] lg:h-[calc(100vh-2rem)] relative overflow-hidden">
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
        w-full lg:w-96 
        h-full 
        z-50 lg:z-0
        flex flex-col gap-6 
        overflow-y-auto custom-scrollbar
        bg-white lg:bg-transparent 
        backdrop-blur-none
        transition-transform duration-300 ease-in-out
        p-4 lg:p-0
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
        <div className="glass-effect-strong rounded-2xl p-4 sm:p-5 md:p-6 border border-dark-500/10 mb-5 sm:mb-6">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 bg-gradient-to-br from-accent-500 via-secondary-500 to-dark-500 rounded-full flex items-center justify-center text-primary-50 font-bold text-lg shadow-lg">
              {userId.charAt(0).toUpperCase()}
            </div>
            <div>
              <div className="text-primary-900 font-semibold text-lg">
                {userId}
              </div>
                              <div className="text-primary-900/60 text-sm">
                  {new Date().getDate()}/{new Date().getMonth() + 1}
                </div>
            </div>
          </div>
          
          <div className="mt-4 flex gap-2">
            <button
              onClick={() => setUseVoice(true)}
              className="flex-1 px-5 py-3 rounded-lg font-medium transition-all duration-300 bg-gradient-to-r from-secondary-500 to-secondary-600 hover:from-secondary-600 hover:to-secondary-700 text-primary-50 btn-hover text-base shadow-lg border border-secondary-600/30"
            >
              Voice Mode
            </button>
            <button
              onClick={handleLogout}
              className="px-5 py-3 rounded-lg font-medium transition-all duration-300 bg-gradient-to-r from-dark-500 to-dark-600 hover:from-dark-600 hover:to-dark-700 text-primary-50 btn-hover text-base shadow-lg border border-dark-600/30"
            >
              Logout
            </button>
          </div>
        </div>

        {/* Mindful Conversations */}
        <div className="glass-effect-strong rounded-2xl p-4 sm:p-5 md:p-6 border border-dark-500/10 mb-5 sm:mb-6">
          <h3 className="text-primary-900 font-semibold text-xl sm:text-2xl md:text-3xl mb-4 sm:mb-5 flex items-center gap-2">
            Conversations
          </h3>
          <div className="space-y-3">
            <button 
              onClick={() => {
                console.log('New conversation clicked - closing sidebar');
                setShowSidebar(false); // Close menu on mobile FIRST
                handleNewChat();
              }}
              className="w-full text-left px-5 py-4 rounded-lg bg-secondary-500/20 text-secondary-700 hover:bg-secondary-500/30 transition-all duration-200 text-lg"
            >
              New Conversation
            </button>
            {sessions.length > 0 && (
              <div className="space-y-3">
                <div className="text-secondary-600 text-lg">Past Conversations:</div>
                <div className="max-h-64 overflow-y-auto transparent-scrollbar space-y-2">
                  {sessions.map((session) => (
                    <button
                      key={session.session_id || session}
                      onClick={() => {
                        console.log('Past conversation clicked - closing sidebar');
                        setShowSidebar(false); // Close menu on mobile FIRST
                        const id = session.session_id || session;
                        setSelectedSession(id);
                        navigate(`/chat/${userId}/${id}`);
                        
                        // Refresh sessions list to ensure we have the latest data
                        setTimeout(() => {
                          fetchSessions(userId);
                        }, 500);
                      }}
                      className={`w-full text-left px-5 py-4 rounded-lg text-lg transition-all duration-200 ${
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
          </div>
        </div>

        

        {/* Email Integration */}
        <div className="glass-effect-strong rounded-2xl p-4 sm:p-5 md:p-6 border border-dark-500/10 mb-5 sm:mb-6">
          <h3 className="text-primary-900 font-semibold text-xl sm:text-2xl md:text-3xl mb-4 sm:mb-5 flex items-center gap-2">
            Quick Actions
          </h3>
          <div className="space-y-3">
            <button 
              onClick={handleCheckEmails}
              className="w-full text-left px-5 py-4 rounded-lg bg-accent-500/20 text-accent-700 hover:bg-accent-500/30 transition-all duration-200 text-lg"
            >
              Check Emails
            </button>
            <button 
              onClick={handleCheckCalendar}
              className="w-full text-left px-5 py-4 rounded-lg bg-secondary-500/20 text-secondary-700 hover:bg-secondary-500/30 transition-all duration-200 text-lg"
            >
              Calendar Events
            </button>
            <button className="w-full text-left px-5 py-4 rounded-lg bg-dark-500/20 text-dark-600 hover:bg-dark-500/30 transition-all duration-200 text-lg">
              Compose Email
            </button>
          </div>
        </div>

        
        {/* Smart Insights */}
        <div className="glass-effect-strong rounded-2xl p-4 sm:p-5 md:p-6 border border-dark-500/10 mb-5 sm:mb-6">
          <h3 className="text-primary-900 font-semibold text-xl sm:text-2xl md:text-3xl mb-4 sm:mb-5 flex items-center gap-2">
            Smart Insights
          </h3>
          <div className="space-y-3">
            <div className="bg-accent-500/20 rounded-lg px-4 py-6 border border-dark-500/5">
              <div className="text-accent-700 text-lg">
                <div className="flex items-center gap-2 mb-1">
                  <div className="w-2 h-2 bg-accent-500 rounded-full"></div>
                  <span className="font-medium">Memory Active</span>
                </div>
                <div className="text-base text-accent-700/60">
                  {chat.length} messages in session
                </div>
              </div>
            </div>
            <div className="bg-accent-500/20 rounded-lg px-4 py-6 border border-dark-500/5">
              <div className="text-accent-700 text-lg">
                <div className="flex items-center gap-2 mb-1">
                  <div className="w-2 h-2 bg-accent-500 rounded-full"></div>
                  <span className="font-medium">Context Aware</span>
                </div>
                <div className="text-base text-accent-700/60">
                  Personal facts remembered
                </div>
              </div>
            </div>
          </div>
        </div>


        {/* Session Stats */}
        <div className="glass-effect-strong rounded-2xl p-4 sm:p-5 md:p-6 border border-dark-500/10 mb-5 sm:mb-6">
          <h3 className="text-primary-900 font-semibold text-xl sm:text-2xl md:text-3xl mb-4 sm:mb-5 flex items-center gap-2">
            Session Stats
          </h3>
          <div className="space-y-3 text-lg">
            <div className="flex justify-between">
              <span className="text-primary-900/70 text-lg">Messages:</span>
              <span className="text-secondary-600 text-lg">{chat.length}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-primary-900/70 text-lg">Sessions:</span>
              <span className="text-accent-600 text-lg">{sessions.length}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-primary-900/70 text-lg">Status:</span>
              <span className="text-secondary-600 text-lg">Active</span>
            </div>
          </div>
        </div>
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col glass-effect-strong rounded-3xl lg:rounded-2xl border border-dark-500/20 lg:ml-0 ml-0 max-w-full overflow-hidden">
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
                <p className="text-primary-900 font-bold text-lg lg:text-xl">Session: {sessionId?.slice(-8)}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-secondary-600 text-sm font-medium"></span>
            </div>
          </div>
        </div>

        {/* Chat Messages */}
        <div ref={chatRef} className="flex-1 overflow-y-auto custom-scrollbar p-3 lg:p-4">
          <MessageList chat={chat} loading={loading} onEmailSelect={handleEmailSelect} />
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
        <div className="p-4 lg:p-6 border-t border-dark-500/10">
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
