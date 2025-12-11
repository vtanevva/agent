import React, {useState} from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  ActivityIndicator,
  Alert,
  Modal,
} from 'react-native';
import {LinearGradient} from 'expo-linear-gradient';
import {API_BASE_URL} from '../config/api';
import {colors} from '../styles/colors';

const REFERRAL_OPTIONS = [
  'Social Media',
  'Friend/Colleague',
  'Search Engine',
  'Blog/Article',
  'Other',
];

export default function WaitlistPage() {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [referralSource, setReferralSource] = useState('');
  const [showDropdown, setShowDropdown] = useState(false);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [messageType, setMessageType] = useState(''); // 'success' or 'error'

  const validateEmail = (email) => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
  };

  const handleSubmit = async () => {
    // Validation
    if (!name.trim()) {
      setMessage('Please enter your name.');
      setMessageType('error');
      return;
    }

    if (!email.trim()) {
      setMessage('Please enter your email address.');
      setMessageType('error');
      return;
    }

    if (!validateEmail(email)) {
      setMessage('Please enter a valid email address.');
      setMessageType('error');
      return;
    }

    if (!referralSource) {
      setMessage('Please select how you heard about us.');
      setMessageType('error');
      return;
    }

    setLoading(true);
    setMessage('');

    try {
      const response = await fetch(`${API_BASE_URL}/api/waitlist/signup`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          name: name.trim(),
          email: email.trim().toLowerCase(),
          referral_source: referralSource,
        }),
      });

      const data = await response.json();

      if (response.ok && data.success) {
        setMessage('🎉 Successfully joined the waitlist! We\'ll be in touch soon.');
        setMessageType('success');
        setName('');
        setEmail('');
        setReferralSource('');
      } else {
        setMessage(data.error || 'Something went wrong. Please try again.');
        setMessageType('error');
      }
    } catch (error) {
      console.error('Waitlist signup error:', error);
      setMessage('Network error. Please check your connection and try again.');
      setMessageType('error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <LinearGradient
      colors={[colors.primary[50], colors.primary[100]]}
      style={styles.container}
      start={{x: 0, y: 0}}
      end={{x: 1, y: 1}}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.keyboardView}>
        <ScrollView
          contentContainerStyle={styles.scrollContent}
          keyboardShouldPersistTaps="handled">
          <View style={styles.content}>
            {/* Title Section */}
            <View style={styles.titleSection}>
              <Text style={styles.titleText}>
                Join the Aivis Beta
              </Text>
            </View>

            {/* Description */}
            <Text style={styles.description}>
              Aivis is an AI-powered productivity assistant that helps you manage your email, calendar, and tasks. Join our beta to get early access and help shape the product.
            </Text>

            {/* Message Display */}
            {message ? (
              <View
                style={[
                  styles.messageContainer,
                  messageType === 'success'
                    ? styles.messageSuccess
                    : styles.messageError,
                ]}>
                <Text
                  style={[
                    styles.messageText,
                    messageType === 'success'
                      ? styles.messageTextSuccess
                      : styles.messageTextError,
                  ]}>
                  {message}
                </Text>
              </View>
            ) : null}

            {/* Form */}
            <View style={styles.form}>
              <View style={styles.formGroup}>
                <Text style={styles.label}>
                  Full Name <Text style={styles.asterisk}>*</Text>
                </Text>
                <TextInput
                  style={styles.input}
                  placeholder="Enter your full name"
                  placeholderTextColor={colors.primary[900] + '60'}
                  value={name}
                  onChangeText={setName}
                  editable={!loading}
                  autoCapitalize="words"
                />
              </View>

              <View style={styles.formGroup}>
                <Text style={styles.label}>
                  Email <Text style={styles.asterisk}>*</Text>
                </Text>
                <TextInput
                  style={styles.input}
                  placeholder="Your Email"
                  placeholderTextColor={colors.primary[900] + '60'}
                  value={email}
                  onChangeText={setEmail}
                  editable={!loading}
                  keyboardType="email-address"
                  autoCapitalize="none"
                  autoCorrect={false}
                />
              </View>

              <View style={styles.formGroup}>
                <Text style={styles.label}>
                  How did you hear about us? <Text style={styles.asterisk}>*</Text>
                </Text>
                <TouchableOpacity
                  style={styles.dropdown}
                  onPress={() => setShowDropdown(true)}
                  disabled={loading}>
                  <Text style={[
                    styles.dropdownText,
                    !referralSource && styles.dropdownPlaceholder
                  ]}>
                    {referralSource || 'Select an option'}
                  </Text>
                  <Text style={styles.dropdownArrow}>▼</Text>
                </TouchableOpacity>

                <Modal
                  visible={showDropdown}
                  transparent
                  animationType="fade"
                  onRequestClose={() => setShowDropdown(false)}>
                  <TouchableOpacity
                    style={styles.modalOverlay}
                    activeOpacity={1}
                    onPress={() => setShowDropdown(false)}>
                    <View style={styles.dropdownOptions}>
                      {REFERRAL_OPTIONS.map((option) => (
                        <TouchableOpacity
                          key={option}
                          style={styles.dropdownOption}
                          onPress={() => {
                            setReferralSource(option);
                            setShowDropdown(false);
                          }}>
                          <Text style={styles.dropdownOptionText}>{option}</Text>
                        </TouchableOpacity>
                      ))}
                    </View>
                  </TouchableOpacity>
                </Modal>
              </View>

              <TouchableOpacity
                style={[styles.submitButton, loading && styles.submitButtonDisabled]}
                onPress={handleSubmit}
                disabled={loading}>
                <LinearGradient
                  colors={[colors.accent[500], colors.accent[600]]}
                  style={styles.submitButtonGradient}>
                  {loading ? (
                    <View style={styles.loadingContainer}>
                      <ActivityIndicator color={colors.primary[50]} size="small" style={styles.loadingSpinner} />
                      <Text style={styles.submitButtonText}>Joining...</Text>
                    </View>
                  ) : (
                    <Text style={styles.submitButtonText}>Join Waitlist</Text>
                  )}
                </LinearGradient>
              </TouchableOpacity>
            </View>

          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  keyboardView: {
    flex: 1,
  },
  scrollContent: {
    flexGrow: 1,
    justifyContent: 'center',
    padding: 20,
  },
  content: {
    backgroundColor: colors.primary[50],
    borderRadius: 25,
    padding: 30,
    maxWidth: 500,
    width: '100%',
    alignSelf: 'center',
    borderWidth: 1,
    borderColor: colors.dark[500] + '20',
    shadowColor: '#000',
    shadowOffset: {width: 0, height: 20},
    shadowOpacity: 0.1,
    shadowRadius: 60,
    elevation: 10,
  },
  titleSection: {
    alignItems: 'center',
    marginBottom: 20,
  },
  titleText: {
    fontSize: 32,
    fontWeight: '700',
    color: colors.primary[900],
    textAlign: 'center',
  },
  description: {
    textAlign: 'left',
    color: colors.primary[900] + 'CC',
    fontSize: 16,
    marginBottom: 30,
    lineHeight: 24,
  },
  messageContainer: {
    padding: 15,
    borderRadius: 12,
    marginBottom: 20,
  },
  messageSuccess: {
    backgroundColor: colors.primary[100],
    borderWidth: 1,
    borderColor: colors.accent[500] + '40',
  },
  messageError: {
    backgroundColor: colors.primary[100],
    borderWidth: 1,
    borderColor: colors.secondary[500] + '60',
  },
  messageText: {
    textAlign: 'center',
    fontWeight: '500',
    fontSize: 14,
  },
  messageTextSuccess: {
    color: colors.accent[500],
  },
  messageTextError: {
    color: colors.secondary[600],
  },
  form: {
    marginBottom: 30,
  },
  formGroup: {
    marginBottom: 20,
  },
  label: {
    fontSize: 15,
    fontWeight: '600',
    color: colors.primary[900],
    marginBottom: 8,
  },
  asterisk: {
    color: colors.secondary[600],
  },
  input: {
    width: '100%',
    padding: 15,
    borderWidth: 1,
    borderColor: colors.dark[500] + '20',
    borderRadius: 12,
    fontSize: 16,
    backgroundColor: colors.primary[100],
    color: colors.primary[900],
  },
  dropdown: {
    width: '100%',
    padding: 15,
    borderWidth: 1,
    borderColor: colors.dark[500] + '20',
    borderRadius: 12,
    backgroundColor: colors.primary[100],
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  dropdownText: {
    fontSize: 16,
    color: colors.primary[900],
    flex: 1,
  },
  dropdownPlaceholder: {
    color: colors.primary[900] + '60',
  },
  dropdownArrow: {
    fontSize: 12,
    color: colors.primary[900] + '80',
    marginLeft: 10,
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  dropdownOptions: {
    backgroundColor: colors.primary[50],
    borderRadius: 12,
    minWidth: 250,
    maxWidth: '90%',
    borderWidth: 1,
    borderColor: colors.dark[500] + '20',
    overflow: 'hidden',
    shadowColor: '#000',
    shadowOffset: {width: 0, height: 4},
    shadowOpacity: 0.1,
    shadowRadius: 8,
    elevation: 5,
  },
  dropdownOption: {
    padding: 15,
    borderBottomWidth: 1,
    borderBottomColor: colors.dark[500] + '10',
  },
  dropdownOptionLast: {
    borderBottomWidth: 0,
  },
  dropdownOptionText: {
    fontSize: 16,
    color: colors.primary[900],
  },
  submitButton: {
    width: '100%',
    borderRadius: 12,
    marginTop: 10,
    overflow: 'hidden',
    shadowColor: colors.accent[500],
    shadowOffset: {width: 0, height: 4},
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 5,
  },
  submitButtonGradient: {
    padding: 15,
    alignItems: 'center',
    justifyContent: 'center',
  },
  submitButtonDisabled: {
    opacity: 0.6,
  },
  loadingContainer: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  loadingSpinner: {
    marginRight: 10,
  },
  submitButtonText: {
    color: colors.primary[50],
    fontSize: 18,
    fontWeight: '600',
  },
});

