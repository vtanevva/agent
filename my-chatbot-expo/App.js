import React from 'react';
import {NavigationContainer} from '@react-navigation/native';
import {createNativeStackNavigator} from '@react-navigation/native-stack';
import {SafeAreaProvider} from 'react-native-safe-area-context';

import LoginPage from './src/pages/LoginPage';
import ChatPage from './src/pages/ChatPage';
import VoiceChat from './src/pages/VoiceChat';
import SettingsPage from './src/pages/SettingsPage';
import MenuPage from './src/pages/MenuPage';

const Stack = createNativeStackNavigator();

export default function App() {
  return (
    <SafeAreaProvider>
      <NavigationContainer>
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
        </Stack.Navigator>
      </NavigationContainer>
    </SafeAreaProvider>
  );
}
