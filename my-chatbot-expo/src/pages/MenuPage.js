import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
} from 'react-native';
import {useRoute, useNavigation} from '@react-navigation/native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {Svg, Path} from 'react-native-svg';
import {colors} from '../styles/colors';
import {commonStyles} from '../styles/commonStyles';

export default function MenuPage() {
  const route = useRoute();
  const navigation = useNavigation();
  const {userId, sessionId} = route.params || {};

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      <View style={styles.content}>
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity
            onPress={() => navigation.goBack()}
            style={styles.backButton}>
            <Svg width="24" height="24" viewBox="0 0 24 24" fill={colors.primary[900]}>
              <Path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z"/>
            </Svg>
          </TouchableOpacity>
          <Text style={styles.title}>Menu</Text>
          <View style={{width: 40}} />
        </View>

        {/* Menu Content */}
        <ScrollView style={styles.scrollContent} showsVerticalScrollIndicator={false}>
          <View style={styles.gridContainer}>
            {/* Box 1: Text Chat */}
            <TouchableOpacity 
              style={styles.gridBox}
              onPress={() => {
                navigation.navigate('Chat', {userId, sessionId});
              }}>
              <View style={[styles.gridIcon, {backgroundColor: colors.secondary[500] + '20'}]}>
                <Svg width="32" height="32" viewBox="0 0 24 24" fill={colors.secondary[600]}>
                  <Path d="M20 2H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h4l4 4 4-4h4c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-2 12H6v-2h12v2zm0-3H6V9h12v2zm0-3H6V6h12v2z"/>
                </Svg>
              </View>
              <Text style={styles.gridText}>Text Chat</Text>
            </TouchableOpacity>

            {/* Box 2: Voice Chat */}
            <TouchableOpacity 
              style={styles.gridBox}
              onPress={() => {
                navigation.navigate('VoiceChat', {userId, sessionId});
              }}>
              <View style={[styles.gridIcon, {backgroundColor: colors.accent[500] + '20'}]}>
                <Svg width="32" height="32" viewBox="0 0 24 24" fill={colors.accent[600]}>
                  <Path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z"/>
                  <Path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/>
                </Svg>
              </View>
              <Text style={styles.gridText}>Voice Chat</Text>
            </TouchableOpacity>

            {/* Contacts */}
            <TouchableOpacity 
              style={styles.gridBox}
              onPress={() => {
                navigation.navigate('Contacts', {userId});
              }}>
              <View style={[styles.gridIcon, {backgroundColor: colors.primary[200] + '30'}]}>
                <Svg width="32" height="32" viewBox="0 0 24 24" fill={colors.primary[700]}>
                  <Path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
                </Svg>
              </View>
              <Text style={styles.gridText}>Contacts</Text>
            </TouchableOpacity>

            {/* Box 3: Settings */}
            <TouchableOpacity 
              style={styles.gridBox}
              onPress={() => {
                navigation.navigate('Settings', {userId, sessionId});
              }}>
              <View style={[styles.gridIcon, {backgroundColor: colors.primary[500] + '20'}]}>
                <Svg width="32" height="32" viewBox="0 0 24 24" fill={colors.primary[600]}>
                  <Path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94L14.4 2.81c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.07.62-.07.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/>
                </Svg>
              </View>
              <Text style={styles.gridText}>AI Emails</Text> 
            </TouchableOpacity>

            {/* Box 4: Email */}
            <TouchableOpacity style={styles.gridBox}>
              <View style={[styles.gridIcon, {backgroundColor: colors.secondary[500] + '20'}]}>
                <Svg width="32" height="32" viewBox="0 0 24 24" fill={colors.secondary[600]}>
                  <Path d="M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/>
                </Svg>
              </View>
              <Text style={styles.gridText}>Schedule Meetings</Text>
            </TouchableOpacity>

            {/* Box 5: Calendar */}
            <TouchableOpacity style={styles.gridBox}>
              <View style={[styles.gridIcon, {backgroundColor: colors.accent[500] + '20'}]}>
                <Svg width="32" height="32" viewBox="0 0 24 24" fill={colors.accent[600]}>
                  <Path d="M19 3h-1V1h-2v2H8V1H6v2H5c-1.11 0-1.99.9-1.99 2L3 19c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H5V8h14v11zM7 10h5v5H7z"/>
                </Svg>
              </View>
              <Text style={styles.gridText}>AI Memory Search </Text>
            </TouchableOpacity>

            {/* Box 6: Profile */}
            <TouchableOpacity style={styles.gridBox}>
              <View style={[styles.gridIcon, {backgroundColor: colors.primary[500] + '20'}]}>
                <Svg width="32" height="32" viewBox="0 0 24 24" fill={colors.primary[600]}>
                  <Path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
                </Svg>
              </View>
              <Text style={styles.gridText}>AI Schedule x Google Calendar</Text>
            </TouchableOpacity>

            {/* Box 7: History */}
            <TouchableOpacity style={styles.gridBox}>
              <View style={[styles.gridIcon, {backgroundColor: colors.dark[500] + '20'}]}>
                <Svg width="32" height="32" viewBox="0 0 24 24" fill={colors.dark[600]}>
                  <Path d="M13 3c-4.97 0-9 4.03-9 9H1l3.89 3.89.07.14L9 12H6c0-3.87 3.13-7 7-7s7 3.13 7 7-3.13 7-7 7c-1.93 0-3.68-.79-4.94-2.06l-1.42 1.42C8.27 19.99 10.51 21 13 21c4.97 0 9-4.03 9-9s-4.03-9-9-9zm-1 5v5l4.28 2.54.72-1.21-3.5-2.08V8H12z"/>
                </Svg>
              </View>
              <Text style={styles.gridText}>Meeting Reports</Text>
            </TouchableOpacity>

            {/* Box 8: Help */}
            <TouchableOpacity style={styles.gridBox}>
              <View style={[styles.gridIcon, {backgroundColor: colors.secondary[500] + '20'}]}>
                <Svg width="32" height="32" viewBox="0 0 24 24" fill={colors.secondary[600]}>
                  <Path d="M11 18h2v-2h-2v2zm1-16C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm0-14c-2.21 0-4 1.79-4 4h2c0-1.1.9-2 2-2s2 .9 2 2c0 2-3 1.75-3 5h2c0-2.25 3-2.5 3-5 0-2.21-1.79-4-4-4z"/>
                </Svg>
              </View>
              <Text style={styles.gridText}>LinkedIn Insights</Text>
            </TouchableOpacity>
          </View>
        </ScrollView>
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
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: colors.dark[500] + '20',
    backgroundColor: colors.primary[50],
  },
  backButton: {
    padding: 8,
  },
  title: {
    fontSize: 20,
    fontWeight: 'bold',
    color: colors.primary[900],
  },
  scrollContent: {
    flex: 1,
    padding: 16,
  },
  gridContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
    justifyContent: 'space-between',
  },
  gridBox: {
    width: '47%',
    aspectRatio: 1,
    backgroundColor: colors.primary[100] + '60',
    borderRadius: 16,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 16,
    ...commonStyles.shadowMd,
  },
  gridIcon: {
    width: 64,
    height: 64,
    borderRadius: 32,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 12,
  },
  gridText: {
    fontSize: 14,
    color: colors.primary[900],
    fontWeight: '600',
    textAlign: 'center',
  },
});

