import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
} from 'react-native';
import {useRoute, useNavigation} from '@react-navigation/native';
import {LinearGradient} from 'expo-linear-gradient';
import {SafeAreaView} from 'react-native-safe-area-context';
import {Svg, Path} from 'react-native-svg';
import {colors} from '../styles/colors';
import {commonStyles} from '../styles/commonStyles';

export default function SettingsPage() {
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
          <Text style={styles.title}>Settings</Text>
          <View style={{width: 40}} />
        </View>

        {/* Settings Content */}
        <ScrollView style={styles.scrollContent} showsVerticalScrollIndicator={false}>
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Account</Text>
            <View style={styles.settingItem}>
              <Text style={styles.settingLabel}>User ID</Text>
              <Text style={styles.settingValue}>{userId || 'Guest'}</Text>
            </View>
            <View style={styles.settingItem}>
              <Text style={styles.settingLabel}>Session ID</Text>
              <Text style={styles.settingValue}>{sessionId?.slice(-8) || 'New'}</Text>
            </View>
          </View>

          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Preferences</Text>
            <TouchableOpacity style={styles.settingButton}>
              <Text style={styles.settingButtonText}>Notifications</Text>
              <Svg width="20" height="20" viewBox="0 0 24 24" fill={colors.primary[900]}>
                <Path d="M10 20h4v-4h-4v4zm-6-2h2v-2H4v2zm0-4h2v-2H4v2zm0-4h2V8H4v2zm4 0h12V8H8v2zm12-4h2V4h-2v2zm0 8h2v-2h-2v2zm0-4h2v-2h-2v2zm-4 8h2v-2h-2v2z"/>
              </Svg>
            </TouchableOpacity>
            <TouchableOpacity style={styles.settingButton}>
              <Text style={styles.settingButtonText}>Privacy</Text>
              <Svg width="20" height="20" viewBox="0 0 24 24" fill={colors.primary[900]}>
                <Path d="M12,1L3,5V11C3,16.55 6.16,21.74 12,23C17.84,21.74 21,16.55 21,11V5L12,1M12,7C13.4,7 14.8,8.6 14.8,10V11.5C15.4,11.5 16,12.1 16,12.7V16.2C16,16.8 15.4,17.3 14.8,17.3H9.2C8.6,17.3 8,16.8 8,16.2V12.7C8,12.1 8.6,11.5 9.2,11.5V10C9.2,8.6 10.6,7 12,7M12,8.2C11.2,8.2 10.5,8.7 10.5,10V11.5H13.5V10C13.5,8.7 12.8,8.2 12,8.2Z"/>
              </Svg>
            </TouchableOpacity>
          </View>

          <View style={styles.section}>
            <Text style={styles.sectionTitle}>About</Text>
            <View style={styles.settingItem}>
              <Text style={styles.settingLabel}>Version</Text>
              <Text style={styles.settingValue}>1.0.0</Text>
            </View>
            <TouchableOpacity style={styles.settingButton}>
              <Text style={styles.settingButtonText}>Help & Support</Text>
              <Svg width="20" height="20" viewBox="0 0 24 24" fill={colors.primary[900]}>
                <Path d="M11 18h2v-2h-2v2zm1-16C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm0-14c-2.21 0-4 1.79-4 4h2c0-1.1.9-2 2-2s2 .9 2 2c0 2-3 1.75-3 5h2c0-2.25 3-2.5 3-5 0-2.21-1.79-4-4-4z"/>
              </Svg>
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
  section: {
    marginBottom: 24,
  },
  sectionTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.primary[900] + '80',
    marginBottom: 12,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  settingItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 12,
    paddingHorizontal: 16,
    backgroundColor: colors.primary[100] + '60',
    borderRadius: 8,
    marginBottom: 8,
  },
  settingLabel: {
    fontSize: 16,
    color: colors.primary[900],
    fontWeight: '500',
  },
  settingValue: {
    fontSize: 14,
    color: colors.primary[900] + '80',
  },
  settingButton: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 12,
    paddingHorizontal: 16,
    backgroundColor: colors.primary[100] + '60',
    borderRadius: 8,
    marginBottom: 8,
  },
  settingButtonText: {
    fontSize: 16,
    color: colors.primary[900],
    fontWeight: '500',
  },
});

