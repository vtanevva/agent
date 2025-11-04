import {StyleSheet, Platform} from 'react-native';
import {colors} from './colors';

export const commonStyles = StyleSheet.create({
  // Container styles
  container: {
    flex: 1,
    backgroundColor: colors.primary[50],
  },
  safeArea: {
    flex: 1,
    backgroundColor: 'transparent',
  },
  
  // Glass effect (simulated)
  glassEffect: {
    backgroundColor: 'rgba(253, 255, 252, 0.92)',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: 'rgba(50, 22, 31, 0.2)',
    shadowColor: '#000',
    shadowOffset: {width: 0, height: 4},
    shadowOpacity: 0.1,
    shadowRadius: 12,
    elevation: 5,
  },
  glassEffectStrong: {
    backgroundColor: 'rgba(253, 255, 252, 0.98)',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: 'rgba(50, 22, 31, 0.25)',
    shadowColor: '#000',
    shadowOffset: {width: 0, height: 4},
    shadowOpacity: 0.15,
    shadowRadius: 16,
    elevation: 8,
  },
  
  // Text styles
  textPrimary: {
    color: colors.primary[900],
    fontSize: 16,
  },
  textSecondary: {
    color: colors.primary[900],
    opacity: 0.6,
    fontSize: 14,
  },
  textHeading: {
    color: colors.primary[900],
    fontSize: 24,
    fontWeight: 'bold',
  },
  textSubheading: {
    color: colors.primary[900],
    fontSize: 18,
    fontWeight: '600',
  },
  
  // Button styles
  button: {
    paddingHorizontal: 24,
    paddingVertical: 12,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#000',
    shadowOffset: {width: 0, height: 4},
    shadowOpacity: 0.2,
    shadowRadius: 8,
    elevation: 5,
  },
  buttonPrimary: {
    backgroundColor: colors.accent[500],
  },
  buttonSecondary: {
    backgroundColor: colors.secondary[500],
  },
  buttonText: {
    color: colors.primary[50],
    fontSize: 16,
    fontWeight: '600',
  },
  
  // Input styles
  input: {
    backgroundColor: colors.primary[100],
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 12,
    fontSize: 16,
    color: colors.primary[900],
    borderWidth: 0,
  },
  
  // Card styles
  card: {
    backgroundColor: colors.primary[50],
    borderRadius: 16,
    padding: 16,
    marginVertical: 8,
    shadowColor: '#000',
    shadowOffset: {width: 0, height: 2},
    shadowOpacity: 0.1,
    shadowRadius: 8,
    elevation: 3,
  },
  
  // Message bubble styles
  messageBubble: {
    maxWidth: '80%',
    padding: 12,
    borderRadius: 16,
    marginVertical: 4,
  },
  messageBubbleUser: {
    backgroundColor: colors.accent[500],
    borderBottomRightRadius: 4,
    alignSelf: 'flex-end',
  },
  messageBubbleAssistant: {
    backgroundColor: colors.secondary[500],
    borderBottomLeftRadius: 4,
    alignSelf: 'flex-start',
  },
  messageText: {
    color: colors.primary[50],
    fontSize: 15,
    lineHeight: 20,
  },
  
  // Shadow utilities
  shadowSm: {
    shadowColor: '#000',
    shadowOffset: {width: 0, height: 1},
    shadowOpacity: 0.05,
    shadowRadius: 2,
    elevation: 2,
  },
  shadowMd: {
    shadowColor: '#000',
    shadowOffset: {width: 0, height: 4},
    shadowOpacity: 0.1,
    shadowRadius: 8,
    elevation: 5,
  },
  shadowLg: {
    shadowColor: '#000',
    shadowOffset: {width: 0, height: 8},
    shadowOpacity: 0.15,
    shadowRadius: 16,
    elevation: 10,
  },
});

