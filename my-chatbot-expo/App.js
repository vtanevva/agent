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
  const isNavigationReady = useRef(false);

  // Helper function to get initial route based on URL
  const getInitialRoute = () => {
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      const path = window.location.pathname;
      const urlParams = new URLSearchParams(window.location.search);
      
      if (path === '/waitlist') return 'Waitlist';
      
      // If on /chat route with params, let linking handle it (don't set initial route)
      // React Navigation's linking will automatically navigate to Chat with params
      if (path === '/chat' && (urlParams.get('userId') || urlParams.get('sessionId'))) {
        return 'Login'; // Start with Login, linking will handle the deep link navigation
      }
    }
    return 'Login';
  };

  // No need for handleInitialNavigation - React Navigation's linking handles it automatically

  // Handle deep linking
  useEffect(() => {
    if (Platform.OS === 'web') {
      const handleUrlChange = () => {
        if (typeof window !== 'undefined' && navigationRef.current) {
          const path = window.location.pathname;
          const urlParams = new URLSearchParams(window.location.search);
          
          if (path === '/waitlist') {
            navigationRef.current.navigate('Waitlist');
          }
          // For /chat routes, LoginPage handles navigation (works like guest login)
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
        onReady={() => {
          isNavigationReady.current = true;
        }}
        linking={{
          enabled: true,
          prefixes: [Platform.OS === 'web' && typeof window !== 'undefined' ? window.location.origin : '', '/'],
          config: {
            screens: {
              Waitlist: 'waitlist',
              Chat: {
                path: 'chat',
                parse: {
                  userId: (userId) => userId,
                  sessionId: (sessionId) => sessionId,
                },
              },
              Login: '',
            },
          },
        }}>
        <Stack.Navigator
          initialRouteName={getInitialRoute()}
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
