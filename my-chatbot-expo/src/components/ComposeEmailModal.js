import React, {useState, useRef, useEffect} from 'react';
import {Modal, View, Text, TextInput, TouchableOpacity, StyleSheet, KeyboardAvoidingView, Platform, ActivityIndicator} from 'react-native';
import {LinearGradient} from 'expo-linear-gradient';
import {colors} from '../styles/colors';
import {commonStyles} from '../styles/commonStyles';
import {API_BASE_URL} from '../config/api';

export default function ComposeEmailModal({visible, onClose, userId, initialTo, initialSubject, initialBody}) {
  const [to, setTo] = useState('');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [rewriting, setRewriting] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);
  const bodyRef = useRef(null);
  const defaultSignature = `Kind regards,\n${(userId || 'Your Name')}`;

  useEffect(() => {
    if (visible) {
      // Set initial values when modal opens
      if (initialTo) setTo(initialTo);
      if (initialSubject) setSubject(initialSubject);
      if (initialBody) setBody(initialBody);
    } else {
      setTo('');
      setSubject('');
      setBody('');
      setRewriting(false);
      setSending(false);
      setError(null);
    }
  }, [visible, initialTo, initialSubject, initialBody]);

  const handleRewrite = async () => {
    if (!body.trim()) return;
    setRewriting(true);
    setError(null);
    try {
      const r = await fetch(`${API_BASE_URL}/api/gmail/rewrite`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          user_id: userId,
          text: body,
          tone: 'polite and professional',
          include_signature: true,
          signature: defaultSignature,
          generate_subject: true,
        }),
      });
      const data = await r.json();
      if (data?.success && data.rewritten) {
        setBody(data.rewritten);
        if (data.subject && !subject.trim()) {
          setSubject(data.subject);
        }
      } else {
        setError(data?.error || 'Failed to rewrite.');
      }
    } catch (e) {
      setError(e?.message || 'Network error.');
    } finally {
      setRewriting(false);
    }
  };

  const handleSend = async () => {
    if (!to.trim() || !body.trim()) {
      setError("Please enter 'To' and 'Body'.");
      return;
    }
    setSending(true);
    setError(null);
    try {
      const r = await fetch(`${API_BASE_URL}/api/gmail/send`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId, to, subject, body}),
      });
      const data = await r.json();
      if (data?.success) {
        onClose(true);
      } else {
        setError(data?.error || 'Failed to send.');
      }
    } catch (e) {
      setError(e?.message || 'Network error.');
    } finally {
      setSending(false);
    }
  };

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={() => onClose(false)}>
      <View style={styles.overlay}>
        <KeyboardAvoidingView
          style={{width: '100%'}}
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
          keyboardVerticalOffset={Platform.select({ios: 12, android: 24, default: 0})}
        >
          <View style={styles.container}>
            <View style={styles.headerRow}>
              <Text style={styles.headerTitle}>Compose Email</Text>
              <TouchableOpacity onPress={() => onClose(false)} style={styles.iconBtn}>
                <Text style={styles.iconBtnText}>✕</Text>
              </TouchableOpacity>
            </View>

            <View style={styles.fieldRow}>
              <Text style={styles.label}>To</Text>
              <TextInput
                value={to}
                onChangeText={setTo}
                placeholder="recipient@example.com"
                placeholderTextColor={colors.primary[900] + '60'}
                style={styles.input}
                autoCapitalize="none"
                keyboardType="email-address"
              />
            </View>
            <View style={styles.fieldRow}>
              <Text style={styles.label}>Subject</Text>
              <TextInput
                value={subject}
                onChangeText={setSubject}
                placeholder="(Optional)"
                placeholderTextColor={colors.primary[900] + '60'}
                style={styles.input}
              />
            </View>
            <View style={styles.editor}>
              <View style={styles.editorHeader}>
                <Text style={styles.label}>Message</Text>
                <View style={styles.editorActions}>
                  <TouchableOpacity disabled={rewriting || !body.trim()} onPress={handleRewrite} style={styles.smallBtn}>
                    <Text style={styles.smallBtnText}>{rewriting ? 'Rewriting…' : 'Rewrite'}</Text>
                  </TouchableOpacity>
                </View>
              </View>
              <TextInput
                ref={bodyRef}
                multiline
                value={body}
                onChangeText={setBody}
                placeholder="Write your message in your own words…"
                placeholderTextColor={colors.primary[900] + '60'}
                style={styles.textarea}
                textAlignVertical="top"
              />
            </View>

            {error ? <Text style={styles.error}>{error}</Text> : null}

            <View style={styles.actions}>
              <TouchableOpacity onPress={() => onClose(false)} style={styles.cancelButton}>
                <Text style={styles.cancelText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity disabled={sending || !to.trim() || !body.trim()} onPress={handleSend} style={styles.sendWrapper}>
                <LinearGradient colors={[colors.accent[500], colors.accent[600]]} style={styles.sendButton}>
                  <Text style={styles.sendText}>{sending ? 'Sending…' : 'Send'}</Text>
                </LinearGradient>
              </TouchableOpacity>
            </View>
          </View>
        </KeyboardAvoidingView>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 16,
  },
  container: {
    width: '100%',
    maxWidth: 720,
    backgroundColor: '#fff',
    borderRadius: 16,
    padding: 14,
    ...commonStyles.shadowLg,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  headerTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: colors.primary[900],
  },
  iconBtn: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.primary[200] + '40',
  },
  iconBtnText: {
    color: colors.primary[900],
    fontSize: 14,
    lineHeight: 14,
  },
  fieldRow: {
    marginBottom: 8,
  },
  label: {
    fontSize: 12,
    color: colors.primary[900] + '80',
    marginBottom: 4,
  },
  input: {
    backgroundColor: colors.primary[200] + '30',
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
    color: colors.primary[900],
    borderWidth: 1,
    borderColor: colors.dark[500] + '10',
  },
  editor: {
    height: 220,
    borderRadius: 12,
    backgroundColor: colors.primary[100] + '60',
    borderWidth: 1,
    borderColor: colors.dark[500] + '10',
    overflow: 'hidden',
    marginTop: 4,
  },
  editorHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: colors.dark[500] + '10',
    backgroundColor: colors.primary[200] + '25',
  },
  editorActions: {
    flexDirection: 'row',
    gap: 8,
  },
  textarea: {
    flex: 1,
    padding: 10,
    color: colors.primary[900],
  },
  smallBtn: {
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.dark[500] + '20',
    backgroundColor: colors.primary[200] + '30',
  },
  smallBtnText: {
    fontSize: 12,
    color: colors.primary[900],
    fontWeight: '500',
  },
  error: {
    color: '#b00020',
    fontSize: 12,
    marginTop: 8,
  },
  actions: {
    marginTop: 12,
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 8,
  },
  cancelButton: {
    paddingVertical: 10,
    paddingHorizontal: 14,
    borderRadius: 10,
    backgroundColor: colors.dark[500] + '20',
  },
  cancelText: {
    color: colors.dark[600],
    fontWeight: '500',
  },
  sendWrapper: {
    borderRadius: 10,
    overflow: 'hidden',
  },
  sendButton: {
    paddingVertical: 10,
    paddingHorizontal: 16,
  },
  sendText: {
    color: '#fff',
    fontWeight: '600',
  },
});


