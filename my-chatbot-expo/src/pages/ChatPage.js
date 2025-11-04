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
import {colors} from '../styles/colors';
import {commonStyles} from '../styles/commonStyles';
import MessageList from '../components/MessageList';
import InputBar from '../components/InputBar';
import CalendarView from '../components/CalendarView';
import {API_BASE_URL} from '../config/api';

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
      const r = await fetch(`${API_BASE_URL}/api/google-profile`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId}),
      });
      
      if (!r.ok) throw new Error(`HTTP error! status: ${r.status}`);
      
      const data = await r.json();
      if (data.email) {
        setGoogleConnected(true);
        setGoogleEmail(data.email);
      } else {
        setGoogleConnected(false);
        setGoogleEmail(null);
      }
    } catch (e) {
      console.error('Error checking Google connection:', e);
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
    setInput(`Reply to thread ${threadId} to ${to}: `);
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
              <LinearGradient
                colors={[colors.accent[500], colors.secondary[500], colors.dark[500]]}
                style={styles.avatar}>
                <Text style={styles.avatarText}>
                  {userId?.charAt(0)?.toUpperCase() || 'U'}
                </Text>
              </LinearGradient>
              <Text style={styles.profileName}>{userId}</Text>
              <Text style={styles.dateText}>
                {new Date().getDate()}/{new Date().getMonth() + 1}
              </Text>
              
              <View style={styles.profileButtons}>
                <TouchableOpacity
                  onPress={() => {
                    navigation.navigate('VoiceChat', {userId, sessionId});
                    setShowSidebar(false);
                  }}
                  style={styles.profileButton}>
                  <LinearGradient
                    colors={[colors.secondary[500], colors.secondary[600]]}
                    style={styles.buttonGradient}>
                    <Text style={styles.buttonText}>Voice Mode</Text>
                  </LinearGradient>
                </TouchableOpacity>
                
                <TouchableOpacity onPress={handleLogout} style={styles.profileButton}>
                  <LinearGradient
                    colors={[colors.dark[500], colors.dark[600]]}
                    style={styles.buttonGradient}>
                    <Text style={styles.buttonText}>Logout</Text>
                  </LinearGradient>
                </TouchableOpacity>
              </View>
            </View>

            {/* Google Connection Status */}
            <View style={styles.sectionCard}>
              <Text style={styles.sectionTitle}>Google Account</Text>
              {googleConnected ? (
                <View style={styles.connectionStatus}>
                  <View style={[styles.statusIndicator, {backgroundColor: '#10b981'}]} />
                  <Text style={styles.connectionText}>
                    Connected: {googleEmail || 'Gmail'}
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
    alignItems: 'center',
    marginBottom: 12,
    borderRadius: 12,
  },
  avatar: {
    width: 48,
    height: 48,
    borderRadius: 24,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 8,
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
    marginBottom: 2,
  },
  dateText: {
    fontSize: 12,
    color: colors.primary[900] + '90',
    marginBottom: 12,
  },
  profileButtons: {
    width: '100%',
    gap: 6,
  },
  profileButton: {
    borderRadius: 8,
    overflow: 'hidden',
    ...commonStyles.shadowSm,
  },
  buttonGradient: {
    paddingVertical: 10,
    paddingHorizontal: 12,
    alignItems: 'center',
  },
  buttonText: {
    color: colors.primary[50],
    fontSize: 14,
    fontWeight: '600',
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

