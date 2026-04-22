import React, {useState, useEffect, useRef, useCallback} from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Modal,
  TextInput,
  Alert,
  Linking,
  Animated,
  Platform,
  KeyboardAvoidingView,
  ActivityIndicator,
} from 'react-native';
import {useRoute, useNavigation} from '@react-navigation/native';
import {LinearGradient} from 'expo-linear-gradient';
import {SafeAreaView} from 'react-native-safe-area-context';
import {Svg, Path} from 'react-native-svg';
import {colors} from '../styles/colors';
import {commonStyles} from '../styles/commonStyles';
import MessageList from '../components/MessageList';
import InputBar from '../components/InputBar';
import CalendarView from '../components/CalendarView';
import EmailList from '../components/EmailList';
import {API_BASE_URL, CORE_BACKEND_URL} from '../config/api';
import EmailReplyModal from '../components/EmailReplyModal';
import ComposeEmailModal from '../components/ComposeEmailModal';

export default function ChatPage() {
  const route = useRoute();
  const navigation = useNavigation();
  const {userId, sessionId} = route.params || {};
  
  // All state declarations first (React hooks rules)
  const [isParamsReady, setIsParamsReady] = useState(false);
  const [chat, setChat] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [viewMode, setViewMode] = useState('chat'); // "action" | "chat"
  const [actionEmails, setActionEmails] = useState([]);
  const [actionLoading, setActionLoading] = useState(false);
  const [actionError, setActionError] = useState('');
  const [sessions, setSessions] = useState([]);
  const [selectedSession, setSelectedSession] = useState(sessionId);
  const [showCalendar, setShowCalendar] = useState(false);
  const [calendarEvents, setCalendarEvents] = useState([]);
  const [showSidebar, setShowSidebar] = useState(false);
  const [googleConnected, setGoogleConnected] = useState(false);
  const [googleEmail, setGoogleEmail] = useState(null);
  const [outlookConnected, setOutlookConnected] = useState(false);
  const [outlookEmail, setOutlookEmail] = useState(null);
  const [replyOpen, setReplyOpen] = useState(false);
  const [replyThreadId, setReplyThreadId] = useState(null);
  const [replyTo, setReplyTo] = useState(null);
  const [composeOpen, setComposeOpen] = useState(false);
  const [composeInitial, setComposeInitial] = useState({to: '', subject: '', body: ''});
  const [hiddenThreads, setHiddenThreads] = useState([]);
  const [emailChoices, setEmailChoices] = useState(null);
  const [currentEmailIndex, setCurrentEmailIndex] = useState(0);
  const [selectedImages, setSelectedImages] = useState([]);
  const chatRef = useRef(null);
  const lastUserMessage = useRef('');
  const sidebarAnim = useRef(new Animated.Value(-280)).current;
  const hasCheckedParams = useRef(false);
  const ACTION_CATEGORIES = useRef(['urgent', 'action_items']).current;
  const actionFetchInFlight = useRef(false);
  const actionPollTimer = useRef(null);
  
  // ========== ALL HOOKS MUST BE CALLED BEFORE ANY CONDITIONAL RETURNS ==========
  
  // Animate sidebar
  useEffect(() => {
    Animated.timing(sidebarAnim, {
      toValue: showSidebar ? 0 : -280,
      duration: 300,
      useNativeDriver: true,
    }).start();
  }, [showSidebar, sidebarAnim]);

  // Load chat history
  const loadSessionChat = useCallback(async (sessionId) => {
    if (!sessionId || !userId) return;
    
    try {
      const r = await fetch(`${API_BASE_URL}/api/session_chat`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId, session_id: sessionId}),
      });
      
      if (!r.ok) throw new Error(`HTTP error! status: ${r.status}`);
      
      const {chat: dbChat = []} = await r.json();
      const normal = dbChat.map((m) => ({
        role: m.role === 'bot' ? 'assistant' : m.role,
        text: m.text,
      }));
      
      setChat(normal);
    } catch (e) {
      console.error('Error loading session chat:', e);
      setChat([]);
    }
  }, [userId]);

  // Fetch sessions
  const fetchSessions = useCallback(async () => {
    if (!userId) return;
    try {
      const r = await fetch(`${API_BASE_URL}/api/sessions-log`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId}),
      });
      if (!r.ok) throw new Error(`HTTP error! status: ${r.status}`);
      const {sessions = []} = await r.json();
      setSessions(sessions);
    } catch (err) {
      console.error('sessions', err);
    }
  }, [userId]);

  // Check email provider connections (Gmail and Outlook)
  const checkEmailConnections = useCallback(async () => {
    if (!userId) return;

    const applyGoogleProfile = async () => {
      const r2 = await fetch(`${API_BASE_URL}/api/google-profile`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId}),
      });
      if (!r2.ok) return false;
      const p = await r2.json();
      const email = p?.email ?? null;
      setGoogleConnected(!!email);
      setGoogleEmail(email);
      setOutlookConnected(false);
      setOutlookEmail(null);
      return true;
    };

    try {
      const url = `${API_BASE_URL}/api/email-connections`;
      const r = await fetch(url, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId}),
      });

      if (r.ok) {
        const data = await r.json();
        setGoogleConnected(data.gmail_connected || false);
        setGoogleEmail(data.gmail_email || null);
        setOutlookConnected(data.outlook_connected || false);
        setOutlookEmail(data.outlook_email || null);
        return;
      }

      if (r.status === 404 && (await applyGoogleProfile())) {
        return;
      }

      if (!r.ok) {
        throw new Error(`HTTP error! status: ${r.status}`);
      }
    } catch (e) {
      console.error('Error checking email connections:', e);
      setGoogleConnected(false);
      setGoogleEmail(null);
      setOutlookConnected(false);
      setOutlookEmail(null);
    }
  }, [userId]);

  // Legacy function for backward compatibility
  const checkGoogleConnection = checkEmailConnections;

  useEffect(() => {
    if (userId) {
      fetchSessions();
      checkEmailConnections();
    }
  }, [userId, fetchSessions, checkEmailConnections]);

  const fetchActionInbox = useCallback(async (showLoading = true) => {
    if (!userId) return;

    if (actionFetchInFlight.current && !showLoading) return;
    actionFetchInFlight.current = true;

    if (showLoading) setActionLoading(true);
    setActionError('');

    try {
      const params = new URLSearchParams({
        user_id: userId,
        limit: '200',
      });
      const r = await fetch(`${CORE_BACKEND_URL}/api/action-items?${params}`, {
        method: 'GET',
        headers: {'Content-Type': 'application/json'},
      });
      const data = await r.json();
      if (!r.ok || !data?.success) {
        throw new Error(data?.error || `HTTP ${r.status}`);
      }

      const items = Array.isArray(data?.items) ? data.items : [];
      setActionEmails(items);
    } catch (e) {
      console.error('Error fetching action inbox:', e);
      setActionEmails([]);
      setActionError(e?.message || 'Failed to load action inbox');
    } finally {
      if (showLoading) setActionLoading(false);
      actionFetchInFlight.current = false;
    }
  }, [userId]);

  // Auto-refresh Action Inbox (no manual refresh button needed)
  useEffect(() => {
    if (!userId || viewMode !== 'action') return;
    // Poll cadence: keeps UI fresh without hitting Gmail APIs
    const POLL_MS = 8000;
    if (actionPollTimer.current) {
      clearInterval(actionPollTimer.current);
      actionPollTimer.current = null;
    }
    actionPollTimer.current = setInterval(() => {
      fetchActionInbox(false);
    }, POLL_MS);
    return () => {
      if (actionPollTimer.current) {
        clearInterval(actionPollTimer.current);
        actionPollTimer.current = null;
      }
    };
  }, [userId, viewMode, fetchActionInbox]);

  // Default to Action view when Gmail is connected
  useEffect(() => {
    if (!userId) return;
    if (googleConnected) {
      setViewMode('action');
      fetchActionInbox(true);
    } else {
      setViewMode('chat');
    }
  }, [userId, googleConnected, fetchActionInbox]);

  // Auto-sync contacts once Google is connected (server skips if already initialized)
  useEffect(() => {
    if (!userId || !googleConnected) return;
    (async () => {
      try {
        await fetch(`${API_BASE_URL}/api/contacts/sync`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({user_id: userId, max_sent: 1000}),
        });
      } catch {}
    })();
  }, [userId, googleConnected]);
  useEffect(() => {
    if (sessionId && userId) {
      setSelectedSession(sessionId);
      loadSessionChat(sessionId);
    }
  }, [sessionId, userId, loadSessionChat]);

  // Send message
  const handleSend = useCallback(async (msg = input) => {
    console.log('handleSend called with msg:', msg);
    console.log('current input:', input);
    console.log('userId:', userId, 'sessionId:', sessionId);
    console.log('selectedImages:', selectedImages.length);
    setViewMode('chat');
    
    if (!msg.trim() && selectedImages.length === 0) {
      console.log('Empty message and no images, returning');
      return;
    }
    
    const messageText = msg.trim() || (selectedImages.length > 0 ? "What's in this image?" : "");
    lastUserMessage.current = messageText;
    setInput('');
    
    // Add user message to chat with images
    setChat((c) => [...c, {
      role: 'user',
      text: messageText,
      images: selectedImages.length > 0 ? selectedImages : undefined
    }]);
    
    setLoading(true);
    
    try {
      // Build request body - only include images if there are any
      const requestBody = {
        message: messageText,
        user_id: userId,
        session_id: sessionId,
      };
      
      // Only add images if there are any (don't send undefined)
      if (selectedImages.length > 0) {
        requestBody.images = selectedImages;
      }
      
      console.log('Sending request:', { ...requestBody, images_count: selectedImages.length });
      
      // Clear images after sending
      setSelectedImages([]);
      
      const r = await fetch(`${API_BASE_URL}/api/chat`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(requestBody),
      });
      
      console.log('Response status:', r.status);
      console.log('Response headers:', Object.fromEntries(r.headers.entries()));
      
      if (!r.ok) {
        const errorText = await r.text();
        console.error('Error response:', errorText);
        throw new Error(`HTTP ${r.status}: ${errorText}`);
      }
      
      const data = await r.json();
      
      console.log('Response data:', data);
      
      // Handle connect_google action
      if (data.action === 'connect_google') {
        setChat((c) => [...c, {role: 'assistant', text: 'Opening Google authentication...'}]);
        setLoading(false);
        const canOpen = await Linking.canOpenURL(data.connect_url);
        if (canOpen) {
          await Linking.openURL(data.connect_url);
          // Refresh Google connection status after a delay
          setTimeout(() => {
            checkGoogleConnection();
          }, 2000);
        }
        return;
      }
      
      // Handle compose modal request
      if (data.compose && data.compose.action === 'open_compose') {
        setComposeInitial({
          to: data.compose.to || '',
          subject: data.compose.subject || '',
          body: data.compose.body || '',
        });
        setComposeOpen(true);
        setChat((c) => [...c, {role: 'assistant', text: data.reply || 'Opening compose email...'}]);
        setLoading(false);
        return;
      }
      
      let reply = data?.reply || '';
      if (typeof reply !== 'string') {
        try {
          reply = JSON.stringify(reply);
        } catch {
          reply = String(reply);
        }
      }
      
      const cleaned = String(reply).replace(/```json|```/gi, '').trim();
      let parsed = null;
      try {
        parsed = JSON.parse(cleaned);
      } catch {}
      
      // Handle email choices
      if (Array.isArray(parsed) && parsed[0]?.threadId) {
        setChat((c) => [...c, {role: 'assistant', text: reply}]);
        setEmailChoices(parsed);
        setCurrentEmailIndex(0);
      } 
      // Handle calendar events - check for calendar JSON structure
      else if (parsed && typeof parsed === 'object' && parsed.success !== undefined) {
        console.log('Calendar JSON detected:', parsed);
        if (parsed.events !== undefined) {
          setCalendarEvents(parsed.events || []);
          setShowCalendar(true);
          setChat((c) => [...c, {role: 'assistant', text: '📅 Here are your calendar events:'}]);
        } else {
          // Calendar response but no events - might be error or empty
          setChat((c) => [...c, {role: 'assistant', text: reply}]);
        }
      } 
      // Handle regular text responses
      else {
        setChat((c) => [...c, {role: 'assistant', text: reply}]);
        // Try to extract markdown email list as choices
        try {
          const md = cleaned.replace(/\r\n/g, '\n');
          const re = /\n?\s*\d+\.\s+\*\*From:\*\*\s*([\s\S]*?)\n\s*\*\*Subject:\*\*\s*([\s\S]*?)\n\s*\*\*Snippet:\*\*\s*([\s\S]*?)(?=\n\s*\d+\.\s|$)/g;
          let m;
          let idx = 1;
          const items = [];
          while ((m = re.exec(md)) !== null) {
            const from = m[1].trim();
            const subject = m[2].trim();
            const snippet = m[3].trim();
            items.push({idx, from, subject, snippet, threadId: `md-${idx}`});
            idx += 1;
          }
          if (items.length > 0) {
            setEmailChoices(items);
            setCurrentEmailIndex(0);
          } else {
            setEmailChoices(null);
          }
        } catch {
          setEmailChoices(null);
        }
      }
      
      setTimeout(() => {
        fetchSessions();
      }, 1000);
    } catch (e) {
      console.error('send error', e);
      Alert.alert('Error', 'Failed to send message. Please try again.');
    } finally {
      setLoading(false);
    }
  }, [input, userId, sessionId, fetchSessions, checkGoogleConnection]);

  const handleEmailSelect = (threadId, from) => {
    const m = /<([^>]+)>/.exec(from);
    const to = m ? m[1] : from;
    setReplyThreadId(threadId);
    setReplyTo(to);
    setReplyOpen(true);
  };

  // Optimistic archive/done handlers
  const archiveThreadOptimistic = async (threadId) => {
    if (!threadId) return;
    setHiddenThreads((prev) => Array.from(new Set([...prev, threadId])));
    try {
      await fetch(`${API_BASE_URL}/api/gmail/archive`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId, thread_id: threadId}),
      });
    } catch (e) {
      // Optional: revert
      setHiddenThreads((prev) => prev.filter((t) => t !== threadId));
      console.error('Failed to archive thread:', e);
    }
  };

  const markHandledOptimistic = async (threadId) => {
    if (!threadId) return;
    setHiddenThreads((prev) => Array.from(new Set([...prev, threadId])));
    try {
      await fetch(`${API_BASE_URL}/api/gmail/mark-handled`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId, thread_id: threadId}),
      });
    } catch (e) {
      // Optional: revert
      setHiddenThreads((prev) => prev.filter((t) => t !== threadId));
      console.error('Failed to mark handled:', e);
    }
  };

  // Web-only keyboard shortcuts: j,k,r,e
  useEffect(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') return;
    const handleKeyDown = (e) => {
      const tag = (e.target?.tagName || '').toUpperCase();
      if (tag === 'INPUT' || tag === 'TEXTAREA') return;
      if (!emailChoices || emailChoices.length === 0) return;
      if (e.key === 'j') {
        setCurrentEmailIndex((i) => (i + 1) % emailChoices.length);
      } else if (e.key === 'k') {
        setCurrentEmailIndex((i) => (i - 1 + emailChoices.length) % emailChoices.length);
      } else if (e.key === 'r') {
        const sel = emailChoices[currentEmailIndex];
        if (sel) {
          const toVal = sel.from;
          handleEmailSelect(sel.threadId, toVal);
        }
      } else if (e.key === 'e') {
        const sel = emailChoices[currentEmailIndex];
        if (sel) {
          archiveThreadOptimistic(sel.threadId);
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [emailChoices, currentEmailIndex]);

  // Wait for params to be ready (handles OAuth redirect timing) - MUST BE LAST HOOK
  useEffect(() => {
    console.log('ChatPage useEffect - checking params:', {userId, sessionId, hasChecked: hasCheckedParams.current});
    
    // Only check params once on mount (prevents re-checking when switching sessions)
    if (hasCheckedParams.current) {
      console.log('ChatPage: Already checked params, skipping');
      return;
    }
    
    // Give React Navigation time to populate params from URL (for OAuth redirects)
    const timer = setTimeout(() => {
      hasCheckedParams.current = true;
      setIsParamsReady(true);
      console.log('ChatPage: Params ready after delay', {userId, sessionId});
      if (!userId || !sessionId) {
        console.warn('ChatPage: Missing userId or sessionId after delay, redirecting to Login');
        navigation.replace('Login');
      } else {
        console.log('ChatPage: Params valid, rendering chat interface');
      }
    }, 150);
    
    return () => clearTimeout(timer);
  }, [userId, sessionId, navigation]);

  // ========== ALL HOOKS COMPLETE - NOW REGULAR FUNCTIONS ==========

  const handleNewChat = () => {
    const newSessionId = `${userId}-${Math.random().toString(36).substring(2, 8)}`;
    setChat([]);
    setSelectedSession(newSessionId);
    setSessions((prev) => [...prev, newSessionId]);
    navigation.replace('Chat', {userId, sessionId: newSessionId});
    setTimeout(() => {
      fetchSessions();
    }, 1000);
  };

  const handleLogout = () => {
    // Web: do a hard navigation to fully clear any in-memory navigation state.
    // This avoids bouncing back into Chat due to stale state or URL handling.
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      // React Navigation (web) stores state in history.state; clear it before reload.
      try {
        window.history.replaceState(null, '', '/');
      } catch {}
      window.location.replace('/');
      return;
    }
    navigation.reset({index: 0, routes: [{name: 'Login'}]});
  };

  const handleCheckEmails = async () => {
    if (!googleConnected) {
      Alert.alert('Connect Gmail', 'Please connect Gmail to view your action emails.');
      return;
    }
    setViewMode('action');
    await fetchActionInbox(true);
  };

  const handleCheckCalendar = async () => {
    await handleSend('Show my calendar events');
  };

  // Show loading while waiting for params (prevents white screen during OAuth redirect)
  if (!isParamsReady || !userId || !sessionId) {
    console.log('ChatPage: Showing loading screen', {isParamsReady, userId, sessionId});
    return (
      <SafeAreaView style={[styles.container, {justifyContent: 'center', alignItems: 'center'}]}>
        <LinearGradient
          colors={[colors.primary[50], colors.primary[100]]}
          style={{flex: 1, width: '100%', justifyContent: 'center', alignItems: 'center'}}>
          <Text style={{color: colors.primary[900], fontSize: 16}}>Loading...</Text>
        </LinearGradient>
      </SafeAreaView>
    );
  }
  
  console.log('ChatPage: Rendering main chat interface', {userId, sessionId});

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      <KeyboardAvoidingView
        style={{flex: 1}}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        keyboardVerticalOffset={Platform.select({ios: 0, android: 24, default: 0})}
      >
      <View style={styles.content}>
        {/* Sidebar */}
        {showSidebar && (
          <TouchableOpacity
            style={styles.overlay}
            onPress={() => setShowSidebar(false)}
            activeOpacity={1}
          />
        )}
        
        <Animated.View style={[styles.sidebar, {transform: [{translateX: sidebarAnim}]}]}>
          <ScrollView style={styles.sidebarContent} showsVerticalScrollIndicator={false}>
            {/* User Profile */}
            <View style={styles.profileCard}>
              <View style={styles.profileHeader}>
              <LinearGradient
                colors={[colors.accent[500], colors.secondary[500], colors.dark[500]]}
                style={styles.avatar}>
                <Text style={styles.avatarText}>
                  {userId?.charAt(0)?.toUpperCase() || 'U'}
                </Text>
              </LinearGradient>
              <Text style={styles.dateText}>
                {new Date().getDate()}/{new Date().getMonth() + 1}
              </Text>
              </View>
              <Text style={styles.profileName}>{userId}</Text>
              
              <View style={styles.profileButtons}>
                <TouchableOpacity
                  onPress={() => {
                    navigation.navigate('VoiceChat', {userId, sessionId});
                    setShowSidebar(false);
                  }}
                  style={styles.iconButton}>
                  <View style={styles.iconButtonInner}>
                    <Svg width="20" height="20" viewBox="0 0 24 24" fill={colors.secondary[600]}>
                      <Path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z"/>
                      <Path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/>
                    </Svg>
                  </View>
                </TouchableOpacity>
                
                <TouchableOpacity
                  onPress={() => {
                    handleNewChat();
                    setShowSidebar(false);
                  }}
                  style={styles.iconButton}>
                  <View style={styles.iconButtonInner}>
                    <Svg width="20" height="20" viewBox="0 0 24 24" fill={colors.accent[600]}>
                      <Path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/>
                    </Svg>
                  </View>
                </TouchableOpacity>
                
                <TouchableOpacity
                  onPress={() => {
                    navigation.navigate('Settings', {userId, sessionId});
                    setShowSidebar(false);
                  }}
                  style={styles.iconButton}>
                  <View style={styles.iconButtonInner}>
                    <Svg width="20" height="20" viewBox="0 0 24 24" fill={colors.primary[600]}>
                      <Path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94L14.4 2.81c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.07.62-.07.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/>
                    </Svg>
                  </View>
                </TouchableOpacity>
                
                <TouchableOpacity
                  onPress={() => {
                    navigation.navigate('Menu', {userId, sessionId});
                    setShowSidebar(false);
                  }}
                  style={styles.iconButton}>
                  <View style={styles.iconButtonInner}>
                    <Svg width="20" height="20" viewBox="0 0 24 24" fill={colors.secondary[600]}>
                      <Path d="M3 18h18v-2H3v2zm0-5h18v-2H3v2zm0-7v2h18V6H3z"/>
                    </Svg>
                  </View>
                </TouchableOpacity>
                
                <TouchableOpacity onPress={handleLogout} style={styles.iconButton}>
                  <View style={[styles.iconButtonInner, styles.iconButtonDanger]}>
                    <Svg width="20" height="20" viewBox="0 0 24 24" fill={colors.dark[600]}>
                      <Path d="M13 3h-2v10h2V3zm4.83 2.17l-1.42 1.42C17.99 7.86 19 9.81 19 12c0 3.87-3.13 7-7 7s-7-3.13-7-7c0-2.19 1.01-4.14 2.59-5.41L6.17 5.17C4.23 6.82 3 9.26 3 12c0 4.97 4.03 9 9 9s9-4.03 9-9c0-2.74-1.23-5.18-3.17-6.83z"/>
                    </Svg>
                  </View>
                </TouchableOpacity>
              </View>
            </View>

            {/* Email Provider Connections */}
            <View style={styles.sectionCard}>
              <Text style={styles.sectionTitle}>Email Accounts</Text>
              
              {/* Gmail Connection */}
              <View style={{marginBottom: 12}}>
                <Text style={{fontSize: 14, fontWeight: '600', marginBottom: 6, color: colors.primary[900]}}>Gmail</Text>
                {googleConnected ? (
                  <View style={styles.connectionStatus}>
                    <Text style={styles.connectionText}>
                      {googleEmail || 'Gmail'} ✓
                    </Text>
                  </View>
                ) : (
                  <TouchableOpacity
                    onPress={async () => {
                      const expoRedirect =
                        Platform.OS === 'web' && typeof window !== 'undefined'
                          ? `${window.location.origin}${window.location.pathname || '/'}`
                          : 'exp://localhost:8081';
                      const authUrl = `${API_BASE_URL}/google/auth/${encodeURIComponent(userId)}?expo_app=true&expo_redirect=${encodeURIComponent(expoRedirect)}`;
                      try {
                        if (typeof sessionStorage !== 'undefined' && userId) {
                          sessionStorage.setItem('pending_oauth_username', String(userId).toLowerCase());
                        }
                      } catch {
                        /* ignore */
                      }
                      if (Platform.OS === 'web' && typeof window !== 'undefined') {
                        window.location.assign(authUrl);
                        return;
                      }
                      const canOpen = await Linking.canOpenURL(authUrl);
                      if (canOpen) {
                        await Linking.openURL(authUrl);
                        setTimeout(() => {
                          checkEmailConnections();
                        }, 2000);
                      }
                    }}
                    style={styles.connectButton}>
                    <LinearGradient
                      colors={[colors.accent[500], colors.accent[600]]}
                      style={styles.buttonGradient}>
                      <Text style={styles.buttonText}>Connect Gmail</Text>
                    </LinearGradient>
                  </TouchableOpacity>
                )}
              </View>
              
              {/* Outlook Connection */}
              <View>
                <Text style={{fontSize: 14, fontWeight: '600', marginBottom: 6, color: colors.primary[900]}}>Outlook</Text>
                {outlookConnected ? (
                  <View style={styles.connectionStatus}>
                    <Text style={styles.connectionText}>
                      {outlookEmail || 'Outlook'} ✓
                    </Text>
                  </View>
                ) : (
                  <TouchableOpacity
                    onPress={async () => {
                      const expoRedirect = Platform.OS === 'web' 
                        ? (typeof window !== 'undefined' ? window.location.origin : 'http://localhost:8081')
                        : 'exp://localhost:8081';
                      const authUrl = `${API_BASE_URL}/outlook/auth/${encodeURIComponent(userId)}?expo_app=true&expo_redirect=${encodeURIComponent(expoRedirect)}`;
                      const canOpen = await Linking.canOpenURL(authUrl);
                      if (canOpen) {
                        await Linking.openURL(authUrl);
                        setTimeout(() => {
                          checkEmailConnections();
                        }, 2000);
                      }
                    }}
                    style={styles.connectButton}>
                    <LinearGradient
                      colors={['#0078d4', '#106ebe']}
                      style={styles.buttonGradient}>
                      <Text style={styles.buttonText}>Connect Outlook</Text>
                    </LinearGradient>
                  </TouchableOpacity>
                )}
              </View>
            </View>

            {/* Quick Actions */}
            <View style={styles.sectionCard}>
              <Text style={styles.sectionTitle}>Quick Actions</Text>
              <TouchableOpacity
                onPress={() => {
                  setComposeOpen(true);
                  setShowSidebar(false);
                }}
                style={styles.actionButton}>
                <Text style={styles.actionText}>Compose Email</Text>
              </TouchableOpacity>
              <TouchableOpacity
                onPress={() => {
                  navigation.navigate('GmailAgent', {userId});
                  setShowSidebar(false);
                }}
                style={styles.actionButton}>
                <Text style={styles.actionText}>Open Gmail Agent</Text>
              </TouchableOpacity>
            </View>

            {/* Smart Insights */}
            <View style={styles.sectionCard}>
              <Text style={styles.sectionTitle}>Smart Insights</Text>
              <View style={styles.insightCard}>
                <View style={styles.insightRow}>
                  <View style={styles.indicator} />
                  <Text style={styles.insightTitle}>Memory Active</Text>
                </View>
                <Text style={styles.insightSubtext}>{chat.length} messages in session</Text>
              </View>
              <View style={styles.insightCard}>
                <View style={styles.insightRow}>
                  <View style={styles.indicator} />
                  <Text style={styles.insightTitle}>Context Aware</Text>
                </View>
                <Text style={styles.insightSubtext}>Personal facts remembered</Text>
              </View>
            </View>

            {/* Conversations */}
            <View style={styles.sectionCard}>
              <Text style={styles.sectionTitle}>Conversations</Text>
              <TouchableOpacity onPress={handleNewChat} style={styles.newChatButton}>
                <Text style={styles.newChatText}>New Conversation</Text>
              </TouchableOpacity>
              
              {sessions.length > 0 && (
                <View style={styles.sessionsList}>
                  <Text style={styles.sessionsLabel}>Past Conversations:</Text>
                  {sessions.map((session) => {
                    const id = session.session_id || session;
                    return (
                      <TouchableOpacity
                        key={id}
                        onPress={() => {
                          setSelectedSession(id);
                          navigation.replace('Chat', {userId, sessionId: id});
                          setShowSidebar(false);
                        }}
                        style={[
                          styles.sessionButton,
                          selectedSession === id && styles.sessionButtonActive,
                        ]}>
                        <Text
                          style={[
                            styles.sessionText,
                            selectedSession === id && styles.sessionTextActive,
                          ]}>
                          {id.slice(-8)}
                        </Text>
                      </TouchableOpacity>
                    );
                  })}
                </View>
              )}
            </View>

            {/* Session Stats */}
            <View style={styles.sectionCard}>
              <Text style={styles.sectionTitle}>Session Stats</Text>
              <View style={styles.statsRow}>
                <Text style={styles.statsLabel}>Messages:</Text>
                <Text style={styles.statsValue}>{chat.length}</Text>
              </View>
              <View style={styles.statsRow}>
                <Text style={styles.statsLabel}>Sessions:</Text>
                <Text style={styles.statsValue}>{sessions.length}</Text>
              </View>
              <View style={styles.statsRow}>
                <Text style={styles.statsLabel}>Status:</Text>
                <Text style={styles.statsValue}>Active</Text>
              </View>
            </View>
          </ScrollView>
        </Animated.View>

        {/* Main Chat Area */}
        <View style={styles.chatArea}>
          {/* Header */}
          <View style={styles.chatHeader}>
            <TouchableOpacity
              onPress={() => setShowSidebar(true)}
              style={styles.menuButton}>
              <Text style={styles.menuIcon}>☰</Text>
            </TouchableOpacity>
            <View style={{flex: 1}}>
              <Text style={styles.chatTitle}>
                Session: {sessionId?.slice(-8) || 'New'}
              </Text>
              {googleConnected && (
                <View style={styles.modeToggle}>
                  <TouchableOpacity
                    onPress={() => setViewMode('action')}
                    style={[
                      styles.modeBtn,
                      viewMode === 'action' && styles.modeBtnActive,
                    ]}>
                    <Text style={[
                      styles.modeBtnText,
                      viewMode === 'action' && styles.modeBtnTextActive,
                    ]}>
                      Action Inbox
                    </Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    onPress={() => setViewMode('chat')}
                    style={[
                      styles.modeBtn,
                      viewMode === 'chat' && styles.modeBtnActive,
                    ]}>
                    <Text style={[
                      styles.modeBtnText,
                      viewMode === 'chat' && styles.modeBtnTextActive,
                    ]}>
                      Chat
                    </Text>
                  </TouchableOpacity>
                </View>
              )}
            </View>
          </View>

          {/* Messages Container */}
          <View style={styles.messagesContainer}>
            {googleConnected && viewMode === 'action' ? (
              <View style={{flex: 1}}>
                {actionLoading ? (
                  <View style={styles.actionLoading}>
                    <ActivityIndicator size="large" color={colors.secondary[500]} />
                    <Text style={styles.actionLoadingText}>Loading action emails…</Text>
                  </View>
                ) : actionError ? (
                  <View style={styles.actionEmpty}>
                    <Text style={styles.actionEmptyTitle}>Couldn’t load action emails</Text>
                    <Text style={styles.actionEmptyText}>{actionError}</Text>
                    <TouchableOpacity onPress={() => fetchActionInbox(true)} style={styles.actionRetryBtn}>
                      <Text style={styles.actionRetryText}>Try again</Text>
                    </TouchableOpacity>
                  </View>
                ) : (
                  <EmailList
                    emails={actionEmails}
                    onSelect={handleEmailSelect}
                    onArchive={archiveThreadOptimistic}
                    onDone={markHandledOptimistic}
                    hiddenThreadIds={hiddenThreads}
                  />
                )}
              </View>
            ) : (
              <MessageList
                chat={chat}
                loading={loading}
                onEmailSelect={handleEmailSelect}
                onArchive={archiveThreadOptimistic}
                onDone={markHandledOptimistic}
                hiddenThreadIds={hiddenThreads}
              />
            )}
          </View>

          {/* Input */}
          <InputBar
            input={input}
            setInput={setInput}
            loading={loading}
            onSend={handleSend}
            showConnectButton={false}
            onConnect={() => {}}
            userId={userId}
            onImageSelect={setSelectedImages}
          />
        </View>

        {/* Calendar Modal */}
        {showCalendar && (
          <CalendarView
            events={calendarEvents}
            onEventClick={(event) => {
              // Handle event click
              console.log('Event clicked:', event);
            }}
            onClose={() => setShowCalendar(false)}
          />
        )}
        <EmailReplyModal
          visible={replyOpen}
          onClose={(sent) => {
            setReplyOpen(false);
            setReplyThreadId(null);
            setReplyTo(null);
            if (sent) {
              setChat((c) => [...c, {role: 'assistant', text: '✅ Reply sent.'}]);
              // Auto-advance: focus next email if exists
              if (emailChoices && emailChoices.length > 0) {
                setCurrentEmailIndex((i) => (i + 1) % emailChoices.length);
              }
            }
          }}
          userId={userId}
          threadId={replyThreadId}
          to={replyTo}
        />
        {/* Compose Modal */}
        <ComposeEmailModal
          visible={composeOpen}
          onClose={(sent) => {
            setComposeOpen(false);
            setComposeInitial({to: '', subject: '', body: ''});
            if (sent) {
              setChat((c) => [...c, {role: 'assistant', text: '✅ Email sent.'}]);
            }
          }}
          userId={userId}
          initialTo={composeInitial.to}
          initialSubject={composeInitial.subject}
          initialBody={composeInitial.body}
        />
      </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.primary[50],
  },
  content: {
    flex: 1,
    flexDirection: 'row',
  },
  overlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0,0,0,0.5)',
    zIndex: 1,
  },
  sidebar: {
    width: 280,
    backgroundColor: colors.primary[50],
    borderRightWidth: 1,
    borderRightColor: colors.dark[500] + '20',
    ...commonStyles.shadowMd,
    zIndex: 2,
    position: 'absolute',
    left: 0,
    top: 0,
    bottom: 0,
  },
  sidebarContent: {
    flex: 1,
    padding: 12,
  },
  profileCard: {
    ...commonStyles.glassEffectStrong,
    padding: 12,
    marginBottom: 12,
    borderRadius: 12,
  },
  profileHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  avatar: {
    width: 48,
    height: 48,
    borderRadius: 24,
    alignItems: 'center',
    justifyContent: 'center',
    ...commonStyles.shadowLg,
  },
  avatarText: {
    color: colors.primary[50],
    fontSize: 20,
    fontWeight: 'bold',
  },
  profileName: {
    fontSize: 16,
    fontWeight: '600',
    color: colors.primary[900],
    marginBottom: 8,
  },
  dateText: {
    fontSize: 12,
    color: colors.primary[900] + '90',
  },
  profileButtons: {
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'center',
    marginTop: 4,
  },
  iconButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
  },
  iconButtonInner: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.secondary[500] + '20',
    borderWidth: 1,
    borderColor: colors.secondary[500] + '40',
    alignItems: 'center',
    justifyContent: 'center',
  },
  iconButtonDanger: {
    backgroundColor: colors.dark[500] + '20',
    borderColor: colors.dark[500] + '40',
  },
  sectionCard: {
    ...commonStyles.glassEffectStrong,
    padding: 12,
    marginBottom: 12,
    borderRadius: 10,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: colors.primary[900],
    marginBottom: 10,
  },
  newChatButton: {
    backgroundColor: colors.secondary[500] + '30',
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: 8,
    marginBottom: 10,
  },
  newChatText: {
    color: colors.secondary[700],
    fontSize: 14,
    fontWeight: '500',
  },
  sessionsList: {
    gap: 6,
  },
  sessionsLabel: {
    fontSize: 12,
    color: colors.secondary[600],
    marginBottom: 8,
  },
  sessionButton: {
    backgroundColor: colors.secondary[500] + '15',
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: 8,
  },
  sessionButtonActive: {
    backgroundColor: colors.secondary[500] + '40',
  },
  sessionText: {
    fontSize: 12,
    color: colors.secondary[600] + '80',
  },
  sessionTextActive: {
    color: colors.secondary[700],
    fontWeight: '600',
  },
  actionButton: {
    backgroundColor: colors.accent[500] + '30',
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: 8,
    marginBottom: 6,
  },
  actionText: {
    color: colors.accent[700],
    fontSize: 14,
    fontWeight: '500',
  },
  connectionStatus: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingVertical: 8,
  },
  statusIndicator: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  connectionText: {
    fontSize: 12,
    color: colors.primary[900],
    fontWeight: '500',
  },
  connectButton: {
    borderRadius: 8,
    overflow: 'hidden',
    ...commonStyles.shadowMd,
  },
  buttonGradient: {
    paddingVertical: 12,
    paddingHorizontal: 16,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 8,
  },
  buttonText: {
    color: colors.primary[50],
    fontSize: 14,
    fontWeight: '600',
  },
  chatArea: {
    flex: 1,
    ...commonStyles.glassEffectStrong,
    margin: 4,
    borderRadius: 12,
  },
  chatHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    backgroundColor: colors.primary[50],
  },
  modeToggle: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: 8,
    flexWrap: 'wrap',
  },
  modeBtn: {
    paddingVertical: 8,
    paddingHorizontal: 10,
    borderRadius: 10,
    backgroundColor: colors.primary[200] + '30',
    borderWidth: 1,
    borderColor: colors.dark[500] + '15',
  },
  modeBtnActive: {
    backgroundColor: colors.secondary[500] + '30',
    borderColor: colors.secondary[600] + '50',
  },
  modeBtnText: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.primary[900] + '90',
  },
  modeBtnTextActive: {
    color: colors.secondary[700],
    fontWeight: '800',
  },
  messagesContainer: {
    flex: 1,
  },
  actionLoading: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    padding: 16,
  },
  actionLoadingText: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.primary[900] + '80',
  },
  actionEmpty: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
    gap: 10,
  },
  actionEmptyTitle: {
    fontSize: 16,
    fontWeight: '800',
    color: colors.primary[900],
    textAlign: 'center',
  },
  actionEmptyText: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.primary[900] + '70',
    textAlign: 'center',
  },
  actionRetryBtn: {
    marginTop: 6,
    paddingVertical: 10,
    paddingHorizontal: 14,
    borderRadius: 12,
    backgroundColor: colors.accent[500] + '20',
    borderWidth: 1,
    borderColor: colors.accent[500] + '35',
  },
  actionRetryText: {
    fontSize: 12,
    fontWeight: '800',
    color: colors.accent[700],
  },
  menuButton: {
    marginRight: 12,
    padding: 8,
  },
  menuIcon: {
    fontSize: 24,
    color: colors.primary[900],
  },
  chatTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: colors.primary[900],
  },
  insightCard: {
    backgroundColor: colors.accent[500] + '30',
    borderRadius: 8,
    padding: 10,
    marginBottom: 6,
  },
  insightRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 2,
    gap: 6,
  },
  indicator: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.accent[500],
  },
  insightTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.accent[700],
  },
  insightSubtext: {
    fontSize: 12,
    color: colors.accent[700] + '80',
  },
  statsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 6,
  },
  statsLabel: {
    fontSize: 14,
    color: colors.primary[900] + 'B0',
  },
  statsValue: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.secondary[600],
  },
});

