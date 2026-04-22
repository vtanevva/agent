import React, {useEffect, useRef} from 'react';
import {View, Text, StyleSheet, Animated} from 'react-native';
import {LinearGradient} from 'expo-linear-gradient';
import {Svg, Path} from 'react-native-svg';
import {colors} from '../styles/colors';
import {commonStyles} from '../styles/commonStyles';

export default function WelcomeMessage() {
  const pulseOpacity = useRef(new Animated.Value(1)).current;

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

  return (
    <View style={styles.container}>
      <View style={styles.hero}>
        <Animated.View style={{opacity: pulseOpacity}}>
          <LinearGradient
            colors={[colors.accent[500], colors.secondary[500], colors.dark[500]]}
            style={styles.logo}>
          </LinearGradient>
        </Animated.View>
        
        <Text style={styles.title}>Welcome to Aivis</Text>
        <Text style={styles.subtitle}>
          A system that saves your time and helps you focus on what's important.
        </Text>
      </View>

      <View style={styles.features}>
        <View style={styles.featureIcon}>
          <LinearGradient
            colors={[colors.accent[500], colors.secondary[500]]}
            style={styles.iconGradient}>
            <Svg width="24" height="24" viewBox="0 0 24 24" fill="white">
              <Path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
            </Svg>
          </LinearGradient>
        </View>
        
        <View style={styles.featureIcon}>
          <LinearGradient
            colors={[colors.secondary[500], colors.dark[500]]}
            style={styles.iconGradient}>
            <Svg width="24" height="24" viewBox="0 0 24 24" fill="white">
              <Path d="M9 21c0 .55.45 1 1 1h4c.55 0 1-.45 1-1v-1H9v1zm3-19C8.14 2 5 5.14 5 9c0 2.38 1.19 4.47 3 5.74V17c0 .55.45 1 1 1h6c.55 0 1-.45 1-1v-2.26c1.81-1.27 3-3.36 3-5.74 0-3.86-3.14-7-7-7zm2.85 11.1l-.85.6V16h-4v-2.3l-.85-.6C7.8 12.16 7 10.63 7 9c0-2.76 2.24-5 5-5s5 2.24 5 5c0 1.63-.8 3.16-2.15 4.1z"/>
            </Svg>
          </LinearGradient>
        </View>
        
        <View style={styles.featureIcon}>
          <LinearGradient
            colors={[colors.dark[500], colors.accent[500]]}
            style={styles.iconGradient}>
            <Svg width="24" height="24" viewBox="0 0 24 24" fill="white">
              <Path d="M16 4c0-1.11.89-2 2-2s2 .89 2 2-.89 2-2 2-2-.89-2-2zm4 18v-6h2.5l-2.54-7.63A1.5 1.5 0 0 0 18.54 8H17c-.8 0-1.54.37-2.01.99L14 10.5l-1.5-2c-.47-.62-1.21-.99-2.01-.99H9.46c-.8 0-1.54.37-2.01.99L6 10.5l-1.5-2C4.03 7.88 3.29 7.51 2.49 7.51H1.5L4.04 15.13A1.5 1.5 0 0 0 5.5 16H7v6h2v-6h2.5l1.5 2.5L14 16h2v6h2zm-8-8c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2z"/>
            </Svg>
          </LinearGradient>
        </View>
      </View>

      <View style={styles.cta}>
        <Text style={styles.ctaText}>Ready to begin?</Text>
        <Text style={styles.ctaSubtext}>
          Start typing below to share your thoughts...
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    padding: 16,
    alignItems: 'center',
  },
  hero: {
    alignItems: 'center',
    marginBottom: 24,
  },
  logo: {
    width: 96,
    height: 96,
    borderRadius: 48,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 16,
    ...commonStyles.shadowLg,
  },
  title: {
    fontSize: 20,
    fontWeight: 'bold',
    color: colors.primary[900],
    marginBottom: 8,
    textAlign: 'center',
  },
  subtitle: {
    fontSize: 14,
    color: colors.primary[900] + '80',
    textAlign: 'center',
    maxWidth: 280,
    lineHeight: 20,
  },
  features: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 16,
    marginBottom: 24,
  },
  featureIcon: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  iconGradient: {
    width: 48,
    height: 48,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    ...commonStyles.shadowMd,
  },
  cta: {
    alignItems: 'center',
    gap: 4,
  },
  ctaText: {
    fontSize: 12,
    fontWeight: '500',
    color: colors.primary[900] + '60',
  },
  ctaSubtext: {
    fontSize: 12,
    color: colors.primary[900] + '60',
    textAlign: 'center',
  },
});

