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
import {API_BASE_URL} from '../config/api';
import EmailReplyModal from '../components/EmailReplyModal';

export default function ChatPage() {
  const route = useRoute();
  const navigation = useNavigation();
  const {userId, sessionId} = route.params || {};
  
  const [chat, setChat] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessions, setSessions] = useState([]);
  const [selectedSession, setSelectedSession] = useState(sessionId);
  const [showCalendar, setShowCalendar] = useState(false);
  const [calendarEvents, setCalendarEvents] = useState([]);
  const [showSidebar, setShowSidebar] = useState(false);
  const [googleConnected, setGoogleConnected] = useState(false);
  const [googleEmail, setGoogleEmail] = useState(null);
  const [replyOpen, setReplyOpen] = useState(false);
  const [replyThreadId, setReplyThreadId] = useState(null);
  const [replyTo, setReplyTo] = useState(null);
  const chatRef = useRef(null);
  const lastUserMessage = useRef('');
  const sidebarAnim = useRef(new Animated.Value(-280)).current;

  // Animate sidebar
  useEffect(() => {
    Animated.timing(sidebarAnim, {
      toValue: showSidebar ? 0 : -280,
      duration: 300,
      useNativeDriver: true,
    }).start();
  }, [showSidebar]);

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

  // Check Google connection status
  const checkGoogleConnection = useCallback(async () => {
    if (!userId) return;
    
    try {
      const url = `${API_BASE_URL}/api/google-profile`;
      console.log('Checking Google connection for:', userId);
      console.log('API URL:', url);
      
      const r = await fetch(url, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId}),
      });
      
      console.log('Google profile response status:', r.status);
      
      if (!r.ok) {
        const errorText = await r.text();
        console.error('Google profile error response:', errorText);
        throw new Error(`HTTP error! status: ${r.status}`);
      }
      
      const data = await r.json();
      console.log('Google profile data:', data);
      if (data.email) {
        setGoogleConnected(true);
        setGoogleEmail(data.email);
      } else {
        setGoogleConnected(false);
        setGoogleEmail(null);
      }
    } catch (e) {
      console.error('Error checking Google connection:', e);
      console.error('Error details:', e.message);
      setGoogleConnected(false);
      setGoogleEmail(null);
    }
  }, [userId]);

  useEffect(() => {
    if (userId) {
      fetchSessions();
      checkGoogleConnection();
    }
  }, [userId, fetchSessions, checkGoogleConnection]);

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
    
    if (!msg.trim()) {
      console.log('Empty message, returning');
      return;
    }
    
    lastUserMessage.current = msg;
    setInput('');
    setChat((c) => [...c, {role: 'user', text: msg}]);
    setLoading(true);
    
    try {
      const requestBody = {
        message: msg,
        user_id: userId,
        session_id: sessionId,
      };
      
      console.log('Sending request:', requestBody);
      
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
      } 
      // Handle calendar events
      else if (parsed && parsed.success && parsed.events) {
        setCalendarEvents(parsed.events);
        setShowCalendar(true);
        setChat((c) => [...c, {role: 'assistant', text: '📅 Here are your calendar events:'}]);
      } 
      // Handle regular text responses
      else {
        setChat((c) => [...c, {role: 'assistant', text: reply}]);
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
    navigation.navigate('Login');
  };

  const handleCheckEmails = async () => {
    await handleSend('Check my emails');
  };

  const handleCheckCalendar = async () => {
    await handleSend('Show my calendar events');
  };

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
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

            {/* Google Connection Status */}
            <View style={styles.sectionCard}>
              <Text style={styles.sectionTitle}>Google Account</Text>
              {googleConnected ? (
                <View style={styles.connectionStatus}>
                  <Text style={styles.connectionText}>
                     {googleEmail || 'Gmail'}
                  </Text>
                </View>
              ) : (
                <TouchableOpacity
                  onPress={async () => {
                    // Get the current Expo web URL (for web platform)
                    const expoRedirect = Platform.OS === 'web' 
                      ? (typeof window !== 'undefined' ? window.location.origin : 'http://localhost:8081')
                      : 'exp://localhost:8081';
                    const authUrl = `${API_BASE_URL}/google/auth/${encodeURIComponent(userId)}?expo_app=true&expo_redirect=${encodeURIComponent(expoRedirect)}`;
                    const canOpen = await Linking.canOpenURL(authUrl);
                    if (canOpen) {
                      await Linking.openURL(authUrl);
                      // Check connection status after a delay
                      setTimeout(() => {
                        checkGoogleConnection();
                      }, 2000);
                    }
                  }}
                  style={styles.connectButton}>
                  <LinearGradient
                    colors={[colors.accent[500], colors.accent[600]]}
                    style={styles.buttonGradient}>
                    <Text style={styles.buttonText}>Connect Google</Text>
                  </LinearGradient>
                </TouchableOpacity>
              )}
            </View>

            {/* Quick Actions */}
            <View style={styles.sectionCard}>
              <Text style={styles.sectionTitle}>Quick Actions</Text>
              <TouchableOpacity onPress={handleCheckEmails} style={styles.actionButton}>
                <Text style={styles.actionText}>Check Emails</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={handleCheckCalendar} style={styles.actionButton}>
                <Text style={styles.actionText}>Calendar Events</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.actionButton}>
                <Text style={styles.actionText}>Compose Email</Text>
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
            <Text style={styles.chatTitle}>
              Session: {sessionId?.slice(-8) || 'New'}
            </Text>
          </View>

          {/* Messages Container */}
          <View style={styles.messagesContainer}>
            <MessageList
              chat={chat}
              loading={loading}
              onEmailSelect={handleEmailSelect}
            />
          </View>

          {/* Input */}
          <InputBar
            input={input}
            setInput={setInput}
            loading={loading}
            onSend={handleSend}
            showConnectButton={false}
            onConnect={() => {}}
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
            }
          }}
          userId={userId}
          threadId={replyThreadId}
          to={replyTo}
        />
      </View>
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
  messagesContainer: {
    flex: 1,
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

