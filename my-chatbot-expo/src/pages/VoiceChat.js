import React, {useState, useEffect, useRef, useCallback} from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Alert,
  Linking,
  PermissionsAndroid,
  Platform,
  Animated,
} from 'react-native';
import {useRoute, useNavigation} from '@react-navigation/native';
import {LinearGradient} from 'expo-linear-gradient';
import {SafeAreaView} from 'react-native-safe-area-context';
import {Svg, Path} from 'react-native-svg';
import * as Speech from 'expo-speech';
// Note: Voice recognition in progress - temporarily disabled
// Will need alternative for voice input
import {colors} from '../styles/colors';
import {commonStyles} from '../styles/commonStyles';
import MessageList from '../components/MessageList';
import InputBar from '../components/InputBar';
import EmailList from '../components/EmailList';
import {API_BASE_URL} from '../config/api';

export default function VoiceChat() {
  const route = useRoute();
  const navigation = useNavigation();
  const {userId, sessionId} = route.params || {};
  
  const [chat, setChat] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isSupported, setIsSupported] = useState(false);
  const [showChat, setShowChat] = useState(false);
  const [sessions, setSessions] = useState([]);
  const [selectedSession, setSelectedSession] = useState(sessionId);
  const [emailChoices, setEmailChoices] = useState(null);
  const [showSidebar, setShowSidebar] = useState(false);
  const lastUserMessage = useRef('');
  const sidebarAnim = useRef(new Animated.Value(-280)).current;

  // Initialize TTS with Expo Speech
  useEffect(() => {
    // Expo Speech doesn't have event listeners, handled differently
    console.log('TTS initialized with Expo Speech');
    return () => {
      Speech.stop();
    };
  }, []);

  // Initialize Voice Recognition - TEMPORARILY DISABLED
  // TODO: Implement with Expo alternative
  useEffect(() => {
    console.log('Voice recognition temporarily disabled');
    // Voice.onSpeechStart = () => setIsListening(true);
    // Voice.onSpeechEnd = () => setIsListening(false);
    // Voice.onSpeechError = (e) => {
    //   console.error('Voice error:', e);
    //   setIsListening(false);
    //   Alert.alert('Speech Recognition Error', e.error?.message || 'Failed to recognize speech');
    // };
    // Voice.onSpeechResults = (e) => {
    //   const transcript = e.value?.[0] || '';
    //   if (transcript) {
    //     setInput(transcript);
    //     setTimeout(() => handleSend(transcript), 100);
    //   }
    //   setIsListening(false);
    // };

    // Request permissions
    const requestPermissions = async () => {
      if (Platform.OS === 'android') {
        try {
          const granted = await PermissionsAndroid.request(
            PermissionsAndroid.PERMISSIONS.RECORD_AUDIO,
          );
          if (granted !== PermissionsAndroid.RESULTS.GRANTED) {
            setIsSupported(false);
            Alert.alert('Permission Denied', 'Microphone permission is required for voice chat');
          }
        } catch (err) {
          console.error('Permission error:', err);
          setIsSupported(false);
        }
      }
    };
    requestPermissions();

    // return () => {
    //   Voice.destroy().then(Voice.removeAllListeners);
    // };
  }, []);

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
      console.error('Error fetching sessions:', err);
    }
  }, [userId]);

  useEffect(() => {
    if (userId) {
      fetchSessions();
    }
  }, [userId, fetchSessions]);

  // Load session chat
  const loadSessionChat = useCallback(async (sessionId) => {
    if (!sessionId || !userId) return;
    try {
      const r = await fetch(`${API_BASE_URL}/api/session_chat`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId, session_id: sessionId}),
      });
      const {chat: dbChat = []} = await r.json();
      const normal = dbChat.map((m) => ({
        role: m.role === 'bot' ? 'assistant' : m.role,
        text: m.text,
      }));
      setChat(normal);
      
      const extractEmailChoicesFromChat = (chatHistory) => {
        for (let i = chatHistory.length - 1; i >= 0; i--) {
          const msg = chatHistory[i];
          if (msg.role === 'assistant') {
            const cleaned = msg.text.replace(/```json\n?|\n?```/g, '').trim();
            try {
              const parsed = JSON.parse(cleaned);
              if (Array.isArray(parsed) && parsed[0]?.threadId) {
                return parsed;
              }
            } catch {}
          }
        }
        return null;
      };
      
      const emailData = extractEmailChoicesFromChat(normal);
      setEmailChoices(emailData);
    } catch (e) {
      console.error('load session chat', e);
      setChat([]);
      setEmailChoices(null);
    }
  }, [userId]);

  useEffect(() => {
    if (userId && sessionId) {
      loadSessionChat(sessionId);
      setSelectedSession(sessionId);
    }
  }, [userId, sessionId, loadSessionChat]);

  // Animate sidebar
  useEffect(() => {
    Animated.timing(sidebarAnim, {
      toValue: showSidebar ? 0 : -280,
      duration: 300,
      useNativeDriver: true,
    }).start();
  }, [showSidebar]);

  // Speak text
  const speak = (text) => {
    if (!text) return;
    Speech.stop();
    setIsSpeaking(true);
    Speech.speak(text, {
      language: 'en-US',
      pitch: 1.0,
      rate: 0.5,
      onDone: () => setIsSpeaking(false),
      onStopped: () => setIsSpeaking(false),
    });
  };

  // Auto-speak last assistant message
  useEffect(() => {
    const last = chat[chat.length - 1];
    if (last?.role === 'assistant' && !isSpeaking && last.text) {
      // Don't speak email JSON or markdown
      const isJson = /^\[.*\]$/.test(last.text.trim()) || last.text.includes('threadId');
      const isMarkdownEmail = /\*\*From:\*\*/i.test(last.text);
      if (!isJson && !isMarkdownEmail) {
        speak(last.text);
      }
    }
  }, [chat]);

  // Send message
  const handleSend = async (msg = input) => {
    if (!msg.trim()) return;
    
    lastUserMessage.current = msg;
    setChat((prev) => [...prev, {role: 'user', text: msg}]);
    setInput('');
    setLoading(true);
    
    try {
      const res = await fetch(`${API_BASE_URL}/api/chat`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          message: msg,
          user_id: userId,
          session_id: sessionId,
        }),
      });
      
      const data = await res.json();
      
      // Handle connect_google action
      if (data.action === 'connect_google') {
        setChat((prev) => [...prev, {role: 'assistant', text: 'Opening Google authentication...'}]);
        setLoading(false);
        const canOpen = await Linking.canOpenURL(data.connect_url);
        if (canOpen) {
          await Linking.openURL(data.connect_url);
        }
        return;
      }
      
      let reply = data?.reply || '';
      if (!reply && Array.isArray(data)) {
        reply = JSON.stringify(data);
      }
      if (reply == null) reply = '';
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
      
      if (Array.isArray(parsed) && parsed[0]?.threadId) {
        setEmailChoices(parsed);
        setChat((prev) => [...prev, {role: 'assistant', text: reply}]);
      } else {
        // Try markdown formatted list (e.g., numbered with **From:** etc.)
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
          setChat((prev) => [...prev, {role: 'assistant', text: reply}]);
        } else {
          setEmailChoices(null);
          setChat((prev) => [...prev, {role: 'assistant', text: reply}]);
        }
      }
      
      const isFirstMessage = chat.length === 0;
      if (isFirstMessage) {
        setTimeout(() => fetchSessions(userId), 1000);
      }
    } catch (err) {
      console.error('Backend error:', err);
      Alert.alert('Error', 'Failed to send message. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  // Voice controls
  const recognitionRef = useRef(null);

  // Initialize Web Speech Recognition for web platform
  useEffect(() => {
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (SpeechRecognition) {
        setIsSupported(true);
        recognitionRef.current = new SpeechRecognition();
        recognitionRef.current.continuous = false;
        recognitionRef.current.interimResults = false;
        recognitionRef.current.lang = 'en-US';

        recognitionRef.current.onresult = (event) => {
          const transcript = event.results[0][0].transcript;
          setInput(transcript);
          setIsListening(false);
          setTimeout(() => handleSend(transcript), 100);
        };

        recognitionRef.current.onerror = (event) => {
          console.error('Speech recognition error:', event);
          setIsListening(false);
          Alert.alert('Speech Recognition Error', 'Failed to recognize speech. Please try again.');
        };

        recognitionRef.current.onend = () => {
          setIsListening(false);
        };
      } else {
        setIsSupported(false);
      }
    }
  }, []);

  const startListening = async () => {
    if (isListening) return;
    
    if (Platform.OS === 'web' && recognitionRef.current) {
      try {
        setIsListening(true);
        recognitionRef.current.start();
      } catch (error) {
        console.error('Error starting speech recognition:', error);
        setIsListening(false);
        Alert.alert('Error', 'Failed to start voice recognition. Please try again.');
      }
    } else {
      // For mobile, show alert (needs native implementation)
      Alert.alert('Voice Input', 'Voice recognition coming soon for mobile!');
    }
  };

  const stopListening = async () => {
    if (Platform.OS === 'web' && recognitionRef.current) {
      recognitionRef.current.stop();
    }
    setIsListening(false);
  };

  const stopSpeaking = () => {
    Speech.stop();
    setIsSpeaking(false);
  };

  const handleNewChat = () => {
    const newSessionId = `${userId}-${Math.random().toString(36).substring(2, 8)}`;
    setChat([]);
    setEmailChoices(null);
    navigation.navigate('VoiceChat', {userId, sessionId: newSessionId});
    setTimeout(() => fetchSessions(userId), 500);
  };

  const handleLogout = () => {
    navigation.navigate('Login');
  };

  const handleEmailSelect = (threadId, from) => {
    const m = /<([^>]+)>/.exec(from);
    const to = m ? m[1] : from;
    setInput(`Reply to thread ${threadId} to ${to}: `);
    setEmailChoices(null);
  };

  const handleCheckEmails = async () => {
    await handleSend('Check my emails');
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
            {/* Profile */}
            <View style={styles.profileCard}>
              <View style={styles.profileHeader}>
                <LinearGradient
                  colors={[colors.accent[500], colors.secondary[500], colors.dark[500]]}
                  style={styles.avatar}>
                  <Text style={styles.avatarText}>
                    {userId?.charAt(0)?.toUpperCase() || 'U'}
                  </Text>
                </LinearGradient>
                <View style={styles.profileInfo}>
                  <Text style={styles.profileName}>{userId}</Text>
                  <Text style={styles.profileSubtext}>
                    Voice Session: {sessionId?.slice(-8) || 'New'}
                  </Text>
                </View>
              </View>
              
              <View style={styles.profileButtons}>
                <TouchableOpacity
                  onPress={() => {
                    navigation.navigate('Chat', {userId, sessionId});
                    setShowSidebar(false);
                  }}
                  style={styles.profileButton}>
                  <LinearGradient
                    colors={[colors.secondary[500], colors.secondary[600]]}
                    style={styles.buttonGradient}>
                    <Text style={styles.buttonText}>Text Mode</Text>
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

            {/* Voice Controls */}
            <View style={styles.sectionCard}>
              <Text style={styles.sectionTitle}>Voice Controls</Text>
              <View style={styles.voiceControlsContainer}>
                <TouchableOpacity
                  onPress={() => {
                    if (isListening) {
                      stopListening();
                    } else {
                      startListening();
                    }
                    setShowSidebar(false);
                  }}
                  disabled={!isSupported}
                  style={[
                    styles.voiceButton,
                    isListening && styles.voiceButtonActive,
                    !isSupported && styles.voiceButtonDisabled,
                  ]}>
                  <LinearGradient
                    colors={
                      isListening
                        ? [colors.dark[500], colors.dark[600]]
                        : [colors.secondary[500], colors.secondary[600]]
                    }
                    style={styles.buttonGradient}>
                    <Text style={styles.buttonText}>
                      {isListening ? 'Stop Listening' : 'Start Listening'}
                    </Text>
                  </LinearGradient>
                </TouchableOpacity>
                
                {isSpeaking && (
                  <TouchableOpacity 
                    onPress={() => {
                      stopSpeaking();
                      setShowSidebar(false);
                    }}
                    style={styles.voiceButton}>
                    <LinearGradient
                      colors={[colors.accent[500], colors.accent[600]]}
                      style={styles.buttonGradient}>
                      <Text style={styles.buttonText}>Stop Speaking</Text>
                    </LinearGradient>
                  </TouchableOpacity>
                )}
                
                <View style={styles.voiceStatusCard}>
                  <Text style={styles.voiceStatusText}>
                    {isListening ? 'Listening...' : isSpeaking ? 'Speaking...' : 'Ready to listen'}
                  </Text>
                  <Text style={styles.voiceStatusSubtext}>
                    {isListening ? 'Speak now...' : isSpeaking ? 'AI is responding...' : 'Click to start'}
                  </Text>
                </View>
              </View>
            </View>

            {/* Chat Toggle */}
            <View style={styles.sectionCard}>
              <Text style={styles.sectionTitle}>Chat Display</Text>
              <TouchableOpacity
                onPress={() => {
                  setShowChat(!showChat);
                  setShowSidebar(false);
                }}
                style={styles.voiceButton}>
                <LinearGradient
                  colors={[colors.dark[500], colors.dark[600]]}
                  style={styles.buttonGradient}>
                  <Text style={styles.buttonText}>
                    {showChat ? 'Hide Chat' : 'Show Chat'}
                  </Text>
                </LinearGradient>
              </TouchableOpacity>
            </View>

            {/* Voice Sessions */}
            <View style={styles.sectionCard}>
              <Text style={styles.sectionTitle}>Mindful Voice</Text>
              <TouchableOpacity 
                onPress={() => {
                  handleNewChat();
                  setShowSidebar(false);
                }}
                style={styles.actionButton}>
                <Text style={styles.actionText}>New Voice Session</Text>
              </TouchableOpacity>
              
              {sessions.length > 0 && (
                <View style={styles.sessionsList}>
                  <Text style={styles.sessionsLabel}>Past Sessions:</Text>
                  {sessions.map((session) => {
                    const id = session.session_id || session;
                    return (
                      <TouchableOpacity
                        key={id}
                        onPress={async () => {
                          setShowSidebar(false);
                          setSelectedSession(id);
                          navigation.replace('VoiceChat', {userId, sessionId: id});
                          await loadSessionChat(id);
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
              <View style={styles.infoCard}>
                <Text style={styles.infoText}>Voice conversations are saved automatically</Text>
              </View>
            </View>

            {/* Voice Settings */}
            <View style={styles.sectionCard}>
              <Text style={styles.sectionTitle}>Voice Settings</Text>
              <View style={styles.insightCard}>
                <View style={styles.insightRow}>
                  <View style={[styles.indicator, {backgroundColor: colors.secondary[500]}]} />
                  <Text style={styles.insightTitle}>Auto-playback</Text>
                </View>
                <Text style={styles.insightSubtext}>AI responses play automatically</Text>
              </View>
              <View style={styles.insightCard}>
                <View style={styles.insightRow}>
                  <View style={styles.indicator} />
                  <Text style={styles.insightTitle}>Voice Recognition</Text>
                </View>
                <Text style={styles.insightSubtext}>High accuracy mode enabled</Text>
              </View>
            </View>

            {/* Quick Actions */}
            <View style={styles.sectionCard}>
              <Text style={styles.sectionTitle}>Quick Actions</Text>
              <TouchableOpacity 
                onPress={() => {
                  handleCheckEmails();
                  setShowSidebar(false);
                }}
                style={styles.actionButton}>
                <Text style={styles.actionText}>Check Emails</Text>
              </TouchableOpacity>
              <TouchableOpacity 
                onPress={() => {
                  handleSend('Show my calendar events');
                  setShowSidebar(false);
                }}
                style={styles.actionButton}>
                <Text style={styles.actionText}>Calendar Events</Text>
              </TouchableOpacity>
              <TouchableOpacity 
                onPress={() => setShowSidebar(false)}
                style={styles.actionButton}>
                <Text style={styles.actionText}>Compose Email</Text>
              </TouchableOpacity>
            </View>

            {/* Smart Insights */}
            <View style={styles.sectionCard}>
              <Text style={styles.sectionTitle}>Smart Insights</Text>
              <View style={styles.insightCard}>
                <View style={styles.insightRow}>
                  <View style={[styles.indicator, {backgroundColor: colors.secondary[500]}]} />
                  <Text style={styles.insightTitle}>Voice Session Active</Text>
                </View>
                <Text style={styles.insightSubtext}>{chat.length} messages in current session</Text>
              </View>
              <View style={styles.insightCard}>
                <View style={styles.insightRow}>
                  <View style={styles.indicator} />
                  <Text style={styles.insightTitle}>Voice Mode</Text>
                </View>
                <Text style={styles.insightSubtext}>
                  {isSupported ? 'Fully supported' : 'Limited support'}
                </Text>
              </View>
              <View style={styles.insightCard}>
                <View style={styles.insightRow}>
                  <View style={[styles.indicator, {backgroundColor: colors.dark[500]}]} />
                  <Text style={styles.insightTitle}>Sessions</Text>
                </View>
                <Text style={styles.insightSubtext}>{sessions.length} conversations saved</Text>
              </View>
            </View>

            {/* Status */}
            <View style={styles.sectionCard}>
              <Text style={styles.sectionTitle}>Status</Text>
              <View style={styles.statsRow}>
                <Text style={styles.statsLabel}>Chat:</Text>
                <Text style={[styles.statsValue, {color: showChat ? colors.secondary[600] : colors.primary[900] + '60'}]}>
                  {showChat ? 'Visible' : 'Hidden'}
                </Text>
              </View>
              <View style={styles.statsRow}>
                <Text style={styles.statsLabel}>Speaking:</Text>
                <Text style={[styles.statsValue, {color: isSpeaking ? colors.secondary[600] : colors.primary[900] + '60'}]}>
                  {isSpeaking ? 'Yes' : 'No'}
                </Text>
              </View>
              <View style={styles.statsRow}>
                <Text style={styles.statsLabel}>Listening:</Text>
                <Text style={[styles.statsValue, {color: isListening ? colors.secondary[600] : colors.primary[900] + '60'}]}>
                  {isListening ? 'Yes' : 'No'}
                </Text>
              </View>
              {!isSupported && (
                <View style={styles.warningCard}>
                  <Text style={styles.warningText}>Voice features not supported</Text>
                </View>
              )}
            </View>
          </ScrollView>
        </Animated.View>

        {/* Main Chat Area */}
        <View style={styles.chatArea}>
          {/* Header */}
          <View style={styles.chatHeader}>
            <View style={styles.chatHeaderContent}>
              <TouchableOpacity
                onPress={() => setShowSidebar(true)}
                style={styles.menuButton}>
                <Text style={styles.menuIcon}>☰</Text>
              </TouchableOpacity>
              <View>
                <Text style={styles.chatTitle}>Voice Chat</Text>
                <Text style={styles.chatSubtitle}>Session: {sessionId?.slice(-8) || 'New'}</Text>
              </View>
            </View>
          </View>

          {/* Chat Messages */}
          {showChat && (
            <MessageList
              chat={chat}
              loading={loading}
              onEmailSelect={handleEmailSelect}
            />
          )}

          {/* AI Speaking Animation (when chat is hidden) */}
          {!showChat && isSpeaking && (
            <View style={styles.voiceStatus}>
              <View style={styles.statusContent}>
                <View style={styles.speakingIndicator} />
                <Text style={styles.statusText}>AI is speaking...</Text>
              </View>
            </View>
          )}

          {/* Placeholder when chat is hidden and AI is not speaking */}
          {!showChat && !isSpeaking && (
            <View style={styles.voiceStatus}>
              <View style={styles.statusContent}>
                <View style={styles.placeholderCircle} />
                <Text style={styles.placeholderText}>Click to start speaking</Text>
                
                {/* Microphone Section */}
                <View style={styles.micSection}>
                  <TouchableOpacity
                    onPress={isListening ? stopListening : startListening}
                    disabled={!isSupported}
                    style={[
                      styles.micButton,
                      isListening && styles.micButtonActive,
                      !isSupported && styles.micButtonDisabled,
                    ]}>
                    <LinearGradient
                      colors={
                        isListening
                          ? [colors.primary[50], colors.primary[100]]
                          : [colors.secondary[500], colors.secondary[600]]
                      }
                      style={styles.micButtonGradient}>
                      <Svg width="24" height="24" viewBox="0 0 24 24" fill={isListening ? colors.secondary[600] : colors.primary[50]}>
                        <Path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z"/>
                        <Path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/>
                      </Svg>
                    </LinearGradient>
                  </TouchableOpacity>
                </View>
              </View>
            </View>
          )}

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
    padding: 16,
  },
  profileCard: {
    ...commonStyles.glassEffectStrong,
    padding: 16,
    marginBottom: 16,
    borderRadius: 12,
  },
  profileHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    marginBottom: 16,
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
    fontSize: 18,
    fontWeight: 'bold',
  },
  profileInfo: {
    flex: 1,
  },
  profileName: {
    fontSize: 18,
    fontWeight: '600',
    color: colors.primary[900],
    marginBottom: 2,
  },
  profileSubtext: {
    fontSize: 12,
    color: colors.primary[900] + '60',
  },
  profileButtons: {
    width: '100%',
    gap: 8,
  },
  profileButton: {
    borderRadius: 12,
    overflow: 'hidden',
    ...commonStyles.shadowSm,
  },
  buttonGradient: {
    paddingVertical: 12,
    paddingHorizontal: 16,
    alignItems: 'center',
  },
  buttonText: {
    color: colors.primary[50],
    fontSize: 16,
    fontWeight: '600',
  },
  sectionCard: {
    ...commonStyles.glassEffectStrong,
    padding: 16,
    marginBottom: 16,
    borderRadius: 12,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: colors.primary[900],
    marginBottom: 12,
  },
  voiceControlsContainer: {
    gap: 12,
  },
  voiceButton: {
    borderRadius: 12,
    overflow: 'hidden',
    ...commonStyles.shadowSm,
  },
  voiceButtonActive: {
    opacity: 0.9,
  },
  voiceButtonDisabled: {
    opacity: 0.5,
  },
  voiceStatusCard: {
    backgroundColor: colors.secondary[500] + '30',
    borderRadius: 8,
    padding: 12,
    borderWidth: 1,
    borderColor: colors.dark[500] + '10',
  },
  voiceStatusText: {
    fontSize: 14,
    fontWeight: '500',
    color: colors.primary[900],
    textAlign: 'center',
    marginBottom: 4,
  },
  voiceStatusSubtext: {
    fontSize: 12,
    color: colors.primary[900] + '60',
    textAlign: 'center',
  },
  actionButton: {
    backgroundColor: colors.accent[500] + '30',
    paddingVertical: 12,
    paddingHorizontal: 16,
    borderRadius: 8,
    marginBottom: 8,
  },
  actionText: {
    color: colors.accent[700],
    fontSize: 16,
    fontWeight: '500',
  },
  chatArea: {
    flex: 1,
    ...commonStyles.glassEffectStrong,
    margin: 8,
    borderRadius: 16,
    overflow: 'hidden',
  },
  chatHeader: {
    padding: 16,
    backgroundColor: colors.primary[50],
  },
  chatHeaderContent: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  menuButton: {
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
    marginBottom: 2,
  },
  chatSubtitle: {
    fontSize: 12,
    color: colors.primary[900] + '70',
  },
  voiceStatus: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 400,
  },
  statusContent: {
    alignItems: 'center',
    gap: 24,
  },
  speakingIndicator: {
    width: 128,
    height: 128,
    borderRadius: 64,
    backgroundColor: colors.dark[500] + '60',
    alignItems: 'center',
    justifyContent: 'center',
  },
  statusText: {
    fontSize: 18,
    fontWeight: '500',
    color: colors.primary[900] + '80',
    textAlign: 'center',
  },
  placeholderCircle: {
    width: 128,
    height: 128,
    borderRadius: 64,
    backgroundColor: colors.accent[500] + '30',
    alignItems: 'center',
    justifyContent: 'center',
  },
  placeholderText: {
    fontSize: 18,
    color: colors.primary[900] + '60',
    textAlign: 'center',
  },
  micSection: {
    alignItems: 'center',
    gap: 8,
  },
  micButton: {
    width: 64,
    height: 64,
    borderRadius: 32,
    overflow: 'hidden',
    ...commonStyles.shadowLg,
  },
  micButtonActive: {
    opacity: 0.9,
  },
  micButtonDisabled: {
    opacity: 0.5,
  },
  micButtonGradient: {
    width: '100%',
    height: '100%',
    alignItems: 'center',
    justifyContent: 'center',
  },
  sessionsList: {
    gap: 6,
    marginTop: 12,
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
    marginBottom: 6,
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
  infoCard: {
    marginTop: 12,
    padding: 10,
    backgroundColor: colors.primary[200] + '40',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.dark[500] + '10',
  },
  infoText: {
    fontSize: 11,
    color: colors.primary[900] + '60',
    textAlign: 'center',
  },
  insightCard: {
    backgroundColor: colors.accent[500] + '30',
    borderRadius: 8,
    padding: 12,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: colors.dark[500] + '10',
  },
  insightRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 4,
    gap: 8,
  },
  indicator: {
    width: 8,
    height: 8,
    borderRadius: 4,
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
    marginBottom: 8,
  },
  statsLabel: {
    fontSize: 14,
    color: colors.primary[900] + '80',
  },
  statsValue: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.secondary[600],
  },
  warningCard: {
    marginTop: 12,
    padding: 12,
    backgroundColor: colors.dark[500] + '30',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.dark[500] + '50',
  },
  warningText: {
    fontSize: 12,
    color: colors.dark[600],
    textAlign: 'center',
  },
});

