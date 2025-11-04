import React from 'react';
import {View, TextInput, TouchableOpacity, StyleSheet, Text} from 'react-native';
import {LinearGradient} from 'expo-linear-gradient';
import {colors} from '../styles/colors';
import {commonStyles} from '../styles/commonStyles';

export default function InputBar({input, setInput, loading, onSend, showConnectButton, onConnect}) {
  return (
    <View style={styles.container}>
      <View style={styles.inputContainer}>
        <TextInput
          value={input}
          onChangeText={setInput}
          placeholder="Share your thoughts, feelings, or ask me anything..."
          placeholderTextColor={colors.primary[900] + '60'}
          style={styles.input}
          multiline
          maxLength={1000}
          editable={!loading}
        />

        <TouchableOpacity
          onPress={() => {
            console.log('[InputBar] Send button clicked');
            console.log('[InputBar] onSend function:', typeof onSend);
            onSend();
          }}
          disabled={loading || !input.trim()}
          style={[
            styles.sendButton,
            (!input.trim() || loading) && styles.sendButtonDisabled,
          ]}>
          <LinearGradient
            colors={[colors.accent[500], colors.accent[600]]}
            style={styles.sendButtonGradient}>
            {loading ? (
              <Text style={styles.sendButtonText}>Sending...</Text>
            ) : (
              <Text style={styles.sendButtonText}>Send</Text>
            )}
          </LinearGradient>
        </TouchableOpacity>

        {showConnectButton && (
          <TouchableOpacity onPress={onConnect} style={styles.connectButton}>
            <LinearGradient
              colors={[colors.secondary[500], colors.secondary[600]]}
              style={styles.connectButtonGradient}>
              <Text style={styles.connectButtonText}>Connect</Text>
            </LinearGradient>
          </TouchableOpacity>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    padding: 12,
    borderTopWidth: 1,
    borderTopColor: colors.dark[500] + '20',
    backgroundColor: colors.primary[50],
  },
  inputContainer: {
    flexDirection: 'row',
    gap: 10,
    alignItems: 'flex-end',
  },
  input: {
    flex: 1,
    ...commonStyles.input,
    minHeight: 44,
    maxHeight: 100,
    paddingTop: 10,
    paddingBottom: 10,
  },
  sendButton: {
    borderRadius: 10,
    overflow: 'hidden',
    ...commonStyles.shadowMd,
  },
  sendButtonGradient: {
    paddingHorizontal: 20,
    paddingVertical: 12,
    minWidth: 90,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendButtonDisabled: {
    opacity: 0.5,
  },
  sendButtonText: {
    ...commonStyles.buttonText,
    fontSize: 16,
  },
  connectButton: {
    borderRadius: 12,
    overflow: 'hidden',
    ...commonStyles.shadowMd,
  },
  connectButtonGradient: {
    paddingHorizontal: 20,
    paddingVertical: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  connectButtonText: {
    ...commonStyles.buttonText,
    fontSize: 16,
  },
});

