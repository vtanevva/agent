import React, {useEffect, useRef} from 'react';
import {Platform} from 'react-native';
import {NavigationContainer, useNavigationContainerRef} from '@react-navigation/native';
import {createNativeStackNavigator} from '@react-navigation/native-stack';
import {SafeAreaProvider} from 'react-native-safe-area-context';

import LoginPage from './src/pages/LoginPage';
import ChatPage from './src/pages/ChatPage';
import VoiceChat from './src/pages/VoiceChat';
import SettingsPage from './src/pages/SettingsPage';
import MenuPage from './src/pages/MenuPage';
import GmailAgentPage from './src/pages/GmailAgentPage';
import ContactsPage from './src/pages/ContactsPage';
import ContactDetailPage from './src/pages/ContactDetailPage';
import {genSession} from './src/config/api';

const Stack = createNativeStackNavigator();

export default function App() {
  const navigationRef = useNavigationContainerRef();
  const oauthCheckedRef = useRef(false);

  // Check for OAuth completion on app load (runs once)
  useEffect(() => {
    if (Platform.OS === 'web' && typeof window !== 'undefined' && !oauthCheckedRef.current) {
      oauthCheckedRef.current = true;
      
      // Check URL params first (legacy)
      const urlParams = new URLSearchParams(window.location.search);
      let username = urlParams.get('username');
      let email = urlParams.get('email');
      
      // If no URL params, check sessionStorage (clean redirect)
      if (!username && typeof window.sessionStorage !== 'undefined') {
        const oauthUsername = sessionStorage.getItem('oauth_username');
        const oauthEmail = sessionStorage.getItem('oauth_email');
        const oauthTimestamp = sessionStorage.getItem('oauth_timestamp');
        
        // Only use sessionStorage if it's recent (within last 5 minutes)
        if (oauthUsername && oauthTimestamp) {
          const timestamp = parseInt(oauthTimestamp, 10);
          const now = new Date().getTime();
          if (now - timestamp < 5 * 60 * 1000) { // 5 minutes
            username = oauthUsername;
            email = oauthEmail;
            // Clear sessionStorage after reading
            sessionStorage.removeItem('oauth_username');
            sessionStorage.removeItem('oauth_email');
            sessionStorage.removeItem('oauth_timestamp');
          }
        }
      }
      
      // If OAuth username found, navigate to chat after navigation is ready
      if (username && navigationRef.isReady()) {
        console.log('OAuth redirect detected in App.js, navigating to chat...', {username, email});
        const sessionId = genSession(username);
        navigationRef.navigate('Chat', {userId: username, sessionId});
        // Clear URL params if they exist
        if (urlParams.get('username')) {
          window.history.replaceState({}, '', window.location.pathname);
        }
      }
    }
  }, []);

  // Also check when navigation becomes ready
  useEffect(() => {
    if (Platform.OS === 'web' && typeof window !== 'undefined' && navigationRef.isReady()) {
      // Check sessionStorage again when navigation is ready
      if (typeof window.sessionStorage !== 'undefined') {
        const oauthUsername = sessionStorage.getItem('oauth_username');
        const oauthTimestamp = sessionStorage.getItem('oauth_timestamp');
        
        if (oauthUsername && oauthTimestamp) {
          const timestamp = parseInt(oauthTimestamp, 10);
          const now = new Date().getTime();
          if (now - timestamp < 5 * 60 * 1000) { // 5 minutes
            console.log('OAuth detected in App.js (navigation ready), navigating to chat...', {username: oauthUsername});
            const sessionId = genSession(oauthUsername);
            navigationRef.navigate('Chat', {userId: oauthUsername, sessionId});
            // Clear sessionStorage after reading
            sessionStorage.removeItem('oauth_username');
            sessionStorage.removeItem('oauth_email');
            sessionStorage.removeItem('oauth_timestamp');
          }
        }
      }
    }
  }, [navigationRef.isReady()]);

  return (
    <SafeAreaProvider>
      <NavigationContainer
        ref={navigationRef}
        onReady={() => {
          // Check for OAuth when navigation is ready
          if (Platform.OS === 'web' && typeof window !== 'undefined') {
            if (typeof window.sessionStorage !== 'undefined') {
              const oauthUsername = sessionStorage.getItem('oauth_username');
              const oauthTimestamp = sessionStorage.getItem('oauth_timestamp');
              
              if (oauthUsername && oauthTimestamp) {
                const timestamp = parseInt(oauthTimestamp, 10);
                const now = new Date().getTime();
                if (now - timestamp < 5 * 60 * 1000) { // 5 minutes
                  console.log('OAuth detected in onReady, navigating to chat...', {username: oauthUsername});
                  const sessionId = genSession(oauthUsername);
                  navigationRef.navigate('Chat', {userId: oauthUsername, sessionId});
                  // Clear sessionStorage after reading
                  sessionStorage.removeItem('oauth_username');
                  sessionStorage.removeItem('oauth_email');
                  sessionStorage.removeItem('oauth_timestamp');
                }
              }
            }
          }
        }}>
        <Stack.Navigator
          initialRouteName="Login"
          screenOptions={{
            headerShown: false,
            contentStyle: {backgroundColor: 'transparent'},
          }}>
          <Stack.Screen name="Login" component={LoginPage} />
          <Stack.Screen name="Chat" component={ChatPage} />
          <Stack.Screen name="VoiceChat" component={VoiceChat} />
          <Stack.Screen name="Settings" component={SettingsPage} />
          <Stack.Screen name="Menu" component={MenuPage} />
          <Stack.Screen name="GmailAgent" component={GmailAgentPage} />
          <Stack.Screen name="Contacts" component={ContactsPage} />
          <Stack.Screen name="ContactDetail" component={ContactDetailPage} />
        </Stack.Navigator>
      </NavigationContainer>
    </SafeAreaProvider>
  );
}
