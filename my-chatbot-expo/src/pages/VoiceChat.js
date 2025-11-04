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
} from 'react-native';
import {useRoute, useNavigation} from '@react-navigation/native';
import {LinearGradient} from 'expo-linear-gradient';
import {SafeAreaView} from 'react-native-safe-area-context';
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
  const [isSupported, setIsSupported] = useState(true);
  const [showChat, setShowChat] = useState(false);
  const [sessions, setSessions] = useState([]);
  const [selectedSession, setSelectedSession] = useState(sessionId);
  const [emailChoices, setEmailChoices] = useState(null);
  const [showSidebar, setShowSidebar] = useState(false);
  const lastUserMessage = useRef('');

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
      if (!isJson) {
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
        setEmailChoices(null);
        setChat((prev) => [...prev, {role: 'assistant', text: reply}]);
      }
      
      if (chat.length === 0) {
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
  const startListening = async () => {
    if (isListening) return;
    // TODO: Implement with Expo voice recognition
    Alert.alert('Voice Input', 'Voice recognition coming soon!');
  };

  const stopListening = async () => {
    // TODO: Implement with Expo voice recognition
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
        
        <View style={[styles.sidebar, showSidebar && styles.sidebarVisible]}>
          <ScrollView style={styles.sidebarContent} showsVerticalScrollIndicator={false}>
            {/* Profile */}
            <View style={styles.profileCard}>
              <LinearGradient
                colors={[colors.accent[500], colors.secondary[500], colors.dark[500]]}
                style={styles.avatar}>
                <Text style={styles.avatarText}>
                  {userId?.charAt(0)?.toUpperCase() || 'U'}
                </Text>
              </LinearGradient>
              <Text style={styles.profileName}>{userId}</Text>
              
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
              <TouchableOpacity
                onPress={isListening ? stopListening : startListening}
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
                <TouchableOpacity onPress={stopSpeaking} style={styles.voiceButton}>
                  <LinearGradient
                    colors={[colors.accent[500], colors.accent[600]]}
                    style={styles.buttonGradient}>
                    <Text style={styles.buttonText}>Stop Speaking</Text>
                  </LinearGradient>
                </TouchableOpacity>
              )}
            </View>

            {/* Chat Toggle */}
            <View style={styles.sectionCard}>
              <Text style={styles.sectionTitle}>Chat Display</Text>
              <TouchableOpacity
                onPress={() => setShowChat(!showChat)}
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

            {/* Quick Actions */}
            <View style={styles.sectionCard}>
              <Text style={styles.sectionTitle}>Quick Actions</Text>
              <TouchableOpacity onPress={handleCheckEmails} style={styles.actionButton}>
                <Text style={styles.actionText}>Check Emails</Text>
              </TouchableOpacity>
            </View>
          </ScrollView>
        </View>

        {/* Main Chat Area */}
        <View style={styles.chatArea}>
          {/* Header */}
          <View style={styles.chatHeader}>
            <TouchableOpacity
              onPress={() => setShowSidebar(true)}
              style={styles.menuButton}>
              <Text style={styles.menuIcon}>☰</Text>
            </TouchableOpacity>
            <Text style={styles.chatTitle}>Voice Chat</Text>
          </View>

          {/* Chat Messages */}
          {showChat && (
            <MessageList
              chat={chat}
              loading={loading}
              onEmailSelect={handleEmailSelect}
            />
          )}

          {/* Voice Status */}
          {!showChat && (
            <View style={styles.voiceStatus}>
              {isSpeaking ? (
                <View style={styles.statusContent}>
                  <View style={styles.speakingIndicator} />
                  <Text style={styles.statusText}>AI is speaking...</Text>
                </View>
              ) : (
                <View style={styles.statusContent}>
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
                      <Text style={styles.micIcon}>🎤</Text>
                    </LinearGradient>
                  </TouchableOpacity>
                  <Text style={styles.statusText}>
                    {isListening ? 'Listening...' : 'Click to start speaking'}
                  </Text>
                </View>
              )}
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
    width: 300,
    backgroundColor: colors.primary[50],
    borderRightWidth: 1,
    borderRightColor: colors.dark[500] + '20',
    ...commonStyles.shadowMd,
    zIndex: 2,
  },
  sidebarVisible: {
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
    alignItems: 'center',
    marginBottom: 16,
    borderRadius: 12,
  },
  avatar: {
    width: 64,
    height: 64,
    borderRadius: 32,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 12,
    ...commonStyles.shadowLg,
  },
  avatarText: {
    color: colors.primary[50],
    fontSize: 24,
    fontWeight: 'bold',
  },
  profileName: {
    fontSize: 18,
    fontWeight: '600',
    color: colors.primary[900],
    marginBottom: 16,
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
  voiceButton: {
    borderRadius: 12,
    overflow: 'hidden',
    marginBottom: 8,
    ...commonStyles.shadowSm,
  },
  voiceButtonActive: {
    opacity: 0.9,
  },
  voiceButtonDisabled: {
    opacity: 0.5,
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
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: colors.dark[500] + '20',
    backgroundColor: colors.primary[50],
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
  voiceStatus: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 32,
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
    color: colors.primary[900] + '80',
    textAlign: 'center',
  },
  micButton: {
    width: 96,
    height: 96,
    borderRadius: 48,
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
  micIcon: {
    fontSize: 48,
  },
});

