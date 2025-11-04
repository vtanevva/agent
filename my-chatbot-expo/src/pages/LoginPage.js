import React, {useState, useEffect, useRef} from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  Linking,
  AppState,
  Animated,
} from 'react-native';
import {useNavigation, useFocusEffect} from '@react-navigation/native';
import {LinearGradient} from 'expo-linear-gradient';
import {Svg, Path} from 'react-native-svg';
import {colors} from '../styles/colors';
import {commonStyles} from '../styles/commonStyles';
import {genSession, API_BASE_URL} from '../config/api';

export default function LoginPage() {
  const [loginName, setLoginName] = useState('');
  const navigation = useNavigation();
  const appState = useRef(AppState.currentState);
  const pendingOAuthUsername = useRef(null);
  const pulseOpacity = useRef(new Animated.Value(1)).current;

  // Pulse animation for logo (matching Tailwind's animate-pulse)
  useEffect(() => {
    const pulse = Animated.loop(
      Animated.sequence([
        Animated.timing(pulseOpacity, {
          toValue: 0.5,
          duration: 2000,
          useNativeDriver: true,
        }),
        Animated.timing(pulseOpacity, {
          toValue: 1,
          duration: 2000,
          useNativeDriver: true,
        }),
      ])
    );
    pulse.start();
    return () => pulse.stop();
  }, [pulseOpacity]);

  // Check if Google is connected for a user
  const checkGoogleConnection = async (userId) => {
    try {
      const r = await fetch(`${API_BASE_URL}/api/google-profile`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId}),
      });
      
      if (!r.ok) return false;
      
      const data = await r.json();
      return data.email != null;
    } catch (e) {
      console.error('Error checking Google connection:', e);
      return false;
    }
  };

  // Handle app state changes to detect OAuth return
  useEffect(() => {
    const subscription = AppState.addEventListener('change', async (nextAppState) => {
      if (
        appState.current.match(/inactive|background/) &&
        nextAppState === 'active' &&
        pendingOAuthUsername.current
      ) {
        // App came back to foreground after OAuth
        const username = pendingOAuthUsername.current;
        console.log('App returned from OAuth, checking connection for:', username);
        
        // Wait a bit for OAuth to complete
        setTimeout(async () => {
          const isConnected = await checkGoogleConnection(username);
          if (isConnected) {
            console.log('Google connected! Navigating to chat...');
            const sessionId = genSession(username);
            navigation.navigate('Chat', {userId: username, sessionId});
            pendingOAuthUsername.current = null;
          }
        }, 2000);
      }
      
      appState.current = nextAppState;
    });

    return () => {
      subscription?.remove();
    };
  }, [navigation]);

  // Check for OAuth redirect parameters (from URL query params)
  useEffect(() => {
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      const urlParams = new URLSearchParams(window.location.search);
      const username = urlParams.get('username');
      const email = urlParams.get('email');
      
      if (username) {
        console.log('OAuth redirect detected, navigating to chat...', {username, email});
        const sessionId = genSession(username);
        navigation.navigate('Chat', {userId: username, sessionId});
        // Clear URL params
        window.history.replaceState({}, '', window.location.pathname);
      }
    }
  }, [navigation]);

  // Also check when screen comes into focus (in case OAuth completed while app was backgrounded)
  useFocusEffect(
    React.useCallback(() => {
      if (pendingOAuthUsername.current) {
        const checkConnection = async () => {
          const username = pendingOAuthUsername.current;
          const isConnected = await checkGoogleConnection(username);
          if (isConnected) {
            console.log('Google connected! Navigating to chat...');
            const sessionId = genSession(username);
            navigation.navigate('Chat', {userId: username, sessionId});
            pendingOAuthUsername.current = null;
          }
        };
        
        // Check after a delay to ensure OAuth callback has completed
        const timer = setTimeout(checkConnection, 1500);
        return () => clearTimeout(timer);
      }
    }, [navigation])
  );

  const getGoogleAuthUrl = () => {
    const username = loginName.trim().toLowerCase();
    // Get the current Expo web URL (for web platform)
    const expoRedirect = Platform.OS === 'web' 
      ? window.location.origin 
      : 'exp://localhost:8081';
    return `${API_BASE_URL}/google/auth/${encodeURIComponent(username)}?expo_app=true&expo_redirect=${encodeURIComponent(expoRedirect)}`;
  };

  const handleGoogleAuth = async () => {
    const username = loginName.trim().toLowerCase();
    if (!username) return;
    
    // Store username for OAuth return detection
    pendingOAuthUsername.current = username;
    
    const authUrl = getGoogleAuthUrl();
    const canOpen = await Linking.canOpenURL(authUrl);
    if (canOpen) {
      await Linking.openURL(authUrl);
    }
  };

  const handleGuestLogin = () => {
    const id = loginName.trim().toLowerCase();
    const sessionId = genSession(id);
    navigation.navigate('Chat', {userId: id, sessionId});
  };

  return (
    <LinearGradient
      colors={[colors.primary[50], colors.primary[100]]}
      style={styles.container}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.keyboardView}>
        <ScrollView
          contentContainerStyle={styles.scrollContent}
          keyboardShouldPersistTaps="handled">
          <View style={styles.content}>
            {/* Logo and title */}
            <View style={styles.header}>
              <Animated.View style={{opacity: pulseOpacity}}>
                <LinearGradient
                  colors={[colors.accent[500], colors.secondary[500], colors.dark[500]]}
                  style={styles.logo}>
                </LinearGradient>
              </Animated.View>
              <Text style={styles.title}>Aivis</Text>
              <Text style={styles.subtitle}>
                Your compassionate AI companion
              </Text>
            </View>

            {/* Username input */}
            <View style={styles.inputContainer}>
              <TextInput
                value={loginName}
                onChangeText={setLoginName}
                placeholder="Choose a username"
                placeholderTextColor={colors.primary[900] + '60'}
                style={[
                  styles.input,
                  Platform.OS === 'web' && {
                    outline: 'none',
                    outlineWidth: 0,
                    boxShadow: 'none',
                  },
                ]}
                autoCapitalize="none"
                autoCorrect={false}
              />

              {/* Sign in with Google */}
              <TouchableOpacity
                disabled={!loginName.trim()}
                onPress={handleGoogleAuth}
                style={[
                  styles.button,
                  styles.googleButton,
                  !loginName.trim() && styles.buttonDisabled,
                ]}>
                <LinearGradient
                  colors={[colors.secondary[500], colors.secondary[600]]}
                  style={styles.buttonGradient}>
                  <Text style={styles.buttonText}>
                    Sign in with Google
                  </Text>
                </LinearGradient>
              </TouchableOpacity>

              <View style={styles.divider}>
                <View style={styles.dividerLine} />
                <Text style={styles.dividerText}>or</Text>
                <View style={styles.dividerLine} />
              </View>

              {/* Continue as guest */}
              <TouchableOpacity
                disabled={!loginName.trim()}
                onPress={handleGuestLogin}
                style={[
                  styles.button,
                  styles.guestButton,
                  !loginName.trim() && styles.buttonDisabled,
                ]}>
                <LinearGradient
                  colors={[colors.accent[500], colors.accent[600]]}
                  style={styles.buttonGradient}>
                  <Text style={styles.buttonText}>
                    Continue as "{loginName.trim().toLowerCase() || 'guest'}"
                  </Text>
                </LinearGradient>
              </TouchableOpacity>
            </View>

            {/* Features */}
            <View style={styles.features}>
              <View style={styles.featureItem}>
                <View style={styles.featureIcon}>
                  <Svg width="24" height="24" viewBox="0 0 24 24" fill={colors.primary[900]}>
                    <Path d="M20 2H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h4l4 4 4-4h4c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-2 12H6v-2h12v2zm0-3H6V9h12v2zm0-3H6V6h12v2z"/>
                  </Svg>
                </View>
              </View>
              <View style={styles.featureItem}>
                <View style={styles.featureIcon}>
                  <Svg width="24" height="24" viewBox="0 0 24 24" fill={colors.primary[900]}>
                    <Path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z"/>
                    <Path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/>
                  </Svg>
                </View>
              </View>
              <View style={styles.featureItem}>
                <View style={styles.featureIcon}>
                  <Svg width="24" height="24" viewBox="0 0 24 24" fill={colors.primary[900]}>
                    <Path d="M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/>
                  </Svg>
                </View>
              </View>
            </View>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  keyboardView: {
    flex: 1,
  },
  scrollContent: {
    flexGrow: 1,
    justifyContent: 'center',
    padding: 24,
  },
  content: {
    alignItems: 'center',
    width: '100%',
  },
  header: {
    alignItems: 'center',
    marginBottom: 48,
  },
  logo: {
    width: 96,
    height: 96,
    borderRadius: 48,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 24,
    ...commonStyles.shadowLg,
  },
  title: {
    fontSize: 40,
    fontWeight: 'bold',
    color: colors.primary[900],
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 16,
    color: colors.primary[900] + '80',
    textAlign: 'center',
  },
  inputContainer: {
    width: '100%',
    maxWidth: 384, // max-w-sm in Tailwind (24rem = 384px)
    gap: 16,
    alignItems: 'center',
  },
  input: {
    backgroundColor: colors.secondary[500] + '20',
    borderRadius: 12,
    paddingHorizontal: 24,
    paddingVertical: 16,
    fontSize: 16,
    color: colors.primary[900],
    textAlign: 'center',
    borderWidth: 0,
    outlineWidth: 0,
  },
  button: {
    borderRadius: 12,
    overflow: 'hidden',
    ...commonStyles.shadowMd,
  },
  buttonGradient: {
    paddingVertical: 16,
    paddingHorizontal: 24,
    alignItems: 'center',
    justifyContent: 'center',
  },
  googleButton: {},
  guestButton: {},
  buttonDisabled: {
    opacity: 0.5,
  },
  buttonText: {
    color: colors.primary[50],
    fontSize: 16,
    fontWeight: '600',
  },
  divider: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 16,
    marginVertical: 8,
  },
  dividerLine: {
    flex: 1,
    height: 1,
    backgroundColor: colors.dark[500] + '30',
  },
  dividerText: {
    color: colors.primary[900] + '60',
    fontSize: 14,
    fontWeight: '500',
  },
  features: {
    flexDirection: 'row',
    gap: 32,
    marginTop: 48,
  },
  featureItem: {
    alignItems: 'center',
  },
  featureIcon: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: colors.primary[200] + '80',
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.dark[500] + '20',
  },
});

