import React from 'react';
import {View, Text, StyleSheet, ScrollView, TouchableOpacity} from 'react-native';
import {useRoute, useNavigation} from '@react-navigation/native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {Svg, Path} from 'react-native-svg';

import {theme} from '../styles/theme';
import TopSearchBar from '../components/TopSearchBar';
import BottomNav from '../components/BottomNav';

export default function MenuPage() {
  const route = useRoute();
  const navigation = useNavigation();
  const {userId, sessionId} = route.params || {};

  const goHome = () => {
    if (navigation.canGoBack()) navigation.goBack();
    else navigation.navigate('Home', {userId, sessionId});
  };

  const items = [
    {
      key: 'chat',
      label: 'Text Chat',
      subtitle: 'Talk to Aivis',
      icon: (
        <Path d="M20 2H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h4l4 4 4-4h4c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-2 12H6v-2h12v2zm0-3H6V9h12v2zm0-3H6V6h12v2z" />
      ),
      onPress: () => navigation.navigate('Chat', {userId, sessionId}),
    },
    {
      key: 'voice',
      label: 'Voice Chat',
      subtitle: 'Hands-free',
      icon: (
        <>
          <Path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z" />
          <Path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z" />
        </>
      ),
      onPress: () => navigation.navigate('VoiceChat', {userId, sessionId}),
    },
    {
      key: 'projects',
      label: 'Projects',
      subtitle: 'Group your work',
      icon: <Path d="M10 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z" />,
      onPress: () => navigation.navigate('Projects', {userId, sessionId}),
    },
    {
      key: 'week',
      label: 'Week schedule',
      subtitle: 'Hourly view',
      icon: (
        <Path d="M19 4h-1V2h-2v2H8V2H6v2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 16H5V10h14v10zm0-12H5V6h14v2zM7 12h5v5H7v-5z" />
      ),
      onPress: () => navigation.navigate('WeeklySchedule', {userId, sessionId}),
    },
    {
      key: 'tasks',
      label: 'Tasks',
      subtitle: 'Full list',
      icon: <Path d="M9 16.2l-3.5-3.5L4 14.2l5 5 12-12-1.4-1.4L9 16.2z" />,
      onPress: () => navigation.navigate('Tasks', {userId, sessionId}),
    },
    {
      key: 'contacts',
      label: 'Contacts',
      subtitle: 'People & relationships',
      icon: (
        <Path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z" />
      ),
      onPress: () => navigation.navigate('Contacts', {userId}),
    },
    {
      key: 'emails',
      label: 'Gmail Agent',
      subtitle: 'AI emails',
      icon: (
        <Path d="M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z" />
      ),
      onPress: () => navigation.navigate('GmailAgent', {userId, sessionId}),
    },
    {
      key: 'settings',
      label: 'Settings',
      subtitle: 'Account & app',
      icon: (
        <Path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94L14.4 2.81c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.07.62-.07.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z" />
      ),
      onPress: () => navigation.navigate('Settings', {userId, sessionId}),
    },
  ];

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <TopSearchBar leading="back" onLeadingPress={goHome} />

      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}>
        <Text style={styles.heading}>Menu</Text>

        <View style={styles.grid}>
          {items.map((it) => (
            <TouchableOpacity
              key={it.key}
              activeOpacity={0.85}
              onPress={it.onPress}
              style={styles.tile}>
              <View style={styles.iconCircle}>
                <Svg width="22" height="22" viewBox="0 0 24 24" fill={theme.colors.textPrimary}>
                  {it.icon}
                </Svg>
              </View>
              <Text style={styles.tileLabel}>{it.label}</Text>
              <Text style={styles.tileSubtitle}>{it.subtitle}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </ScrollView>

      <BottomNav
        leftIcon="home"
        centerIcon="plus"
        rightIcon="menu"
        onLeft={goHome}
        onCenter={() => navigation.navigate('QuickChat', {userId, sessionId})}
        onRight={() => {}}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {flex: 1, backgroundColor: theme.colors.bg},
  scroll: {flex: 1},
  scrollContent: {paddingHorizontal: 20, paddingBottom: 140, paddingTop: 8},
  heading: {
    ...theme.type.display,
    color: theme.colors.textPrimary,
    marginTop: 20,
    marginBottom: 16,
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    gap: 12,
  },
  tile: {
    width: '48%',
    backgroundColor: theme.colors.surface,
    borderRadius: 20,
    padding: 16,
    marginBottom: 4,
    ...theme.shadow.card,
  },
  iconCircle: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: theme.colors.surfaceMuted,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 12,
  },
  tileLabel: {
    fontSize: 15,
    fontWeight: '600',
    color: theme.colors.textPrimary,
  },
  tileSubtitle: {
    marginTop: 2,
    fontSize: 12,
    color: theme.colors.textSecondary,
  },
});
