import React, {useEffect, useRef} from 'react';
import {Platform, Linking} from 'react-native';
import {NavigationContainer} from '@react-navigation/native';
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
import WaitlistPage from './src/pages/WaitlistPage';
import {genSession} from './src/config/api';

const Stack = createNativeStackNavigator();

export default function App() {
  const navigationRef = useRef(null);

  // Handle URL paths for web
  useEffect(() => {
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      const path = window.location.pathname;
      const urlParams = new URLSearchParams(window.location.search);
      
      // Navigate to Waitlist if URL is /waitlist
      if (path === '/waitlist' && navigationRef.current) {
        // Use setTimeout to ensure navigation is ready
        setTimeout(() => {
          if (navigationRef.current) {
            navigationRef.current.navigate('Waitlist');
          }
        }, 100);
      }
      
      // Navigate to Chat if URL is /chat with userId and sessionId parameters
      if (path === '/chat' && navigationRef.current) {
        const userId = urlParams.get('userId');
        const sessionId = urlParams.get('sessionId');
        if (userId && sessionId) {
          setTimeout(() => {
            if (navigationRef.current) {
              navigationRef.current.navigate('Chat', {userId, sessionId});
              // Clear URL params
              window.history.replaceState({}, '', '/chat');
            }
          }, 100);
        } else if (userId) {
          // Fallback: if only userId is provided, generate sessionId (backward compatibility)
          const generatedSessionId = genSession(userId);
          setTimeout(() => {
            if (navigationRef.current) {
              navigationRef.current.navigate('Chat', {userId, sessionId: generatedSessionId});
              // Clear URL params
              window.history.replaceState({}, '', '/chat');
            }
          }, 100);
        }
      }
    }
  }, []);

  // Handle deep linking
  useEffect(() => {
    if (Platform.OS === 'web') {
      const handleUrlChange = () => {
        if (typeof window !== 'undefined' && navigationRef.current) {
          const path = window.location.pathname;
          const urlParams = new URLSearchParams(window.location.search);
          
          if (path === '/waitlist') {
            navigationRef.current.navigate('Waitlist');
          } else if (path === '/chat') {
            const userId = urlParams.get('userId');
            const sessionId = urlParams.get('sessionId');
            if (userId && sessionId) {
              navigationRef.current.navigate('Chat', {userId, sessionId});
            } else if (userId) {
              // Fallback: if only userId is provided, generate sessionId (backward compatibility)
              const generatedSessionId = genSession(userId);
              navigationRef.current.navigate('Chat', {userId, sessionId: generatedSessionId});
            }
          }
        }
      };

      // Listen for popstate (back/forward navigation)
      window.addEventListener('popstate', handleUrlChange);
      
      return () => {
        window.removeEventListener('popstate', handleUrlChange);
      };
    }
  }, []);

  return (
    <SafeAreaProvider>
      <NavigationContainer
        ref={navigationRef}
        linking={{
          prefixes: ['/'],
          config: {
            screens: {
              Waitlist: 'waitlist',
              Chat: 'chat',
              Login: '',
            },
          },
        }}>
        <Stack.Navigator
          initialRouteName={Platform.OS === 'web' && typeof window !== 'undefined' && window.location.pathname === '/waitlist' ? 'Waitlist' : 'Login'}
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
          <Stack.Screen name="Waitlist" component={WaitlistPage} />
        </Stack.Navigator>
      </NavigationContainer>
    </SafeAreaProvider>
  );
}
