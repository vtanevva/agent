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
      if (path === '/waitlist') return 'Waitlist';
      // Always start with Login for /chat, then navigate with params in onReady
      // This ensures Chat always receives params when it mounts
    }
    return 'Login';
  };

  // Handle URL paths for web - navigate when navigation is ready
  const handleInitialNavigation = () => {
    if (Platform.OS === 'web' && typeof window !== 'undefined' && navigationRef.current) {
      const path = window.location.pathname;
      
      // Navigate to Waitlist if URL is /waitlist
      // For /chat routes, let LoginPage handle navigation (works like guest login)
      if (path === '/waitlist') {
        navigationRef.current.navigate('Waitlist');
      }
    }
  };

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
          handleInitialNavigation();
        }}
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
