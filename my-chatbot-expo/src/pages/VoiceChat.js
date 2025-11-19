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
import EmailReplyModal from '../components/EmailReplyModal';

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
  const [speechRate, setSpeechRate] = useState(0.5);
  const [voiceAccent, setVoiceAccent] = useState('en-US');
  const [replyOpen, setReplyOpen] = useState(false);
  const [replyThreadId, setReplyThreadId] = useState(null);
  const [replyTo, setReplyTo] = useState(null);
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
      language: voiceAccent,
      pitch: 1.0,
      rate: speechRate,
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
    setReplyThreadId(threadId);
    setReplyTo(to);
    setReplyOpen(true);
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
                <Text style={styles.dateText}>
                  {new Date().getDate()}/{new Date().getMonth() + 1}
                </Text>
              </View>
              <Text style={styles.profileName}>{userId}</Text>
              <Text style={styles.profileSubtext}>
                Voice Session: {sessionId?.slice(-8) || 'New'}
              </Text>
              
              <View style={styles.profileButtons}>
                <TouchableOpacity
                  onPress={() => {
                    navigation.navigate('Chat', {userId, sessionId});
                    setShowSidebar(false);
                  }}
                  style={styles.iconButton}>
                  <View style={styles.iconButtonInner}>
                    <Svg width="20" height="20" viewBox="0 0 24 24" fill={colors.secondary[600]}>
                      <Path d="M20 2H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h4l4 4 4-4h4c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-2 12H6v-2h12v2zm0-3H6V9h12v2zm0-3H6V6h12v2z"/>
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

            {/* Voice Settings */}
            <View style={styles.sectionCard}>
              <Text style={styles.sectionTitle}>Voice Settings</Text>
              
              {/* Speech Rate Control */}
              <View style={styles.voiceSettingItem}>
                <View style={styles.voiceSettingHeader}>
                  <Text style={styles.voiceSettingLabel}>Speech Speed</Text>
                  <Text style={styles.voiceSettingValue}>
                    {speechRate === 0.25 ? 'Very Slow' : 
                     speechRate === 0.5 ? 'Slow' : 
                     speechRate === 0.75 ? 'Normal' : 
                     speechRate === 1.0 ? 'Fast' : 
                     speechRate === 1.5 ? 'Very Fast' : 
                     speechRate.toFixed(2)}
                  </Text>
                </View>
                <View style={styles.speedButtons}>
                  {[
                    {value: 0.25, label: 'Very Slow'},
                    {value: 0.5, label: 'Slow'},
                    {value: 0.75, label: 'Normal'},
                    {value: 1.0, label: 'Fast'},
                    {value: 1.5, label: 'Very Fast'},
                  ].map((speed) => (
                    <TouchableOpacity
                      key={speed.value}
                      onPress={() => setSpeechRate(speed.value)}
                      style={[
                        styles.speedButton,
                        speechRate === speed.value && styles.speedButtonActive,
                      ]}>
                      <Text
                        style={[
                          styles.speedButtonText,
                          speechRate === speed.value && styles.speedButtonTextActive,
                        ]}>
                        {speed.label}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </View>

              {/* Accent/Voice Control */}
              <View style={styles.voiceSettingItem}>
                <Text style={styles.voiceSettingLabel}>Voice Accent</Text>
                <View style={styles.accentButtons}>
                  {[
                    {code: 'en-US', name: 'US English'},
                    {code: 'en-GB', name: 'UK English'},
                    {code: 'en-AU', name: 'Australian'},
                    {code: 'en-IN', name: 'Indian English'},
                  ].map((accent) => (
                    <TouchableOpacity
                      key={accent.code}
                      onPress={() => setVoiceAccent(accent.code)}
                      style={[
                        styles.accentButton,
                        voiceAccent === accent.code && styles.accentButtonActive,
                      ]}>
                      <Text
                        style={[
                          styles.accentButtonText,
                          voiceAccent === accent.code && styles.accentButtonTextActive,
                        ]}>
                        {accent.name}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </View>

              <View style={styles.insightCard}>
                <View style={styles.insightRow}>
                  <View style={[styles.indicator, {backgroundColor: colors.secondary[500]}]} />
                  <Text style={styles.insightTitle}>Auto-playback</Text>
                </View>
                <Text style={styles.insightSubtext}>AI responses play automatically</Text>
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
      <EmailReplyModal
        visible={replyOpen}
        onClose={(sent) => {
          setReplyOpen(false);
          setReplyThreadId(null);
          setReplyTo(null);
          if (sent) {
            setChat((prev) => [...prev, {role: 'assistant', text: '✅ Reply sent.'}]);
          }
        }}
        userId={userId}
        threadId={replyThreadId}
        to={replyTo}
      />
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
    fontSize: 18,
    fontWeight: 'bold',
  },
  profileName: {
    fontSize: 18,
    fontWeight: '600',
    color: colors.primary[900],
    marginBottom: 4,
  },
  profileSubtext: {
    fontSize: 12,
    color: colors.primary[900] + '60',
    marginBottom: 8,
  },
  dateText: {
    fontSize: 12,
    color: colors.primary[900] + '90',
    marginLeft: 'auto',
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
  voiceSettingItem: {
    marginBottom: 16,
    paddingBottom: 12,
    borderBottomWidth: 1,
    borderBottomColor: colors.dark[500] + '10',
  },
  voiceSettingHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  voiceSettingLabel: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.primary[900],
  },
  voiceSettingValue: {
    fontSize: 12,
    color: colors.secondary[600],
    fontWeight: '500',
  },
  speedButtons: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 8,
  },
  speedButton: {
    flex: 1,
    minWidth: '30%',
    paddingVertical: 8,
    paddingHorizontal: 10,
    borderRadius: 8,
    backgroundColor: colors.primary[200] + '40',
    borderWidth: 1,
    borderColor: colors.dark[500] + '20',
    alignItems: 'center',
  },
  speedButtonActive: {
    backgroundColor: colors.secondary[500] + '30',
    borderColor: colors.secondary[600],
  },
  speedButtonText: {
    fontSize: 11,
    color: colors.primary[900] + '80',
    fontWeight: '500',
  },
  speedButtonTextActive: {
    color: colors.secondary[700],
    fontWeight: '600',
  },
  accentButtons: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginTop: 8,
  },
  accentButton: {
    flex: 1,
    minWidth: '45%',
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: 8,
    backgroundColor: colors.primary[200] + '40',
    borderWidth: 1,
    borderColor: colors.dark[500] + '20',
    alignItems: 'center',
  },
  accentButtonActive: {
    backgroundColor: colors.secondary[500] + '30',
    borderColor: colors.secondary[600],
  },
  accentButtonText: {
    fontSize: 12,
    color: colors.primary[900] + '80',
    fontWeight: '500',
  },
  accentButtonTextActive: {
    color: colors.secondary[700],
    fontWeight: '600',
  },
});

