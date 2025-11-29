import React, { useEffect, useState, useRef } from 'react';
import { Modal, View, Text, TextInput, TouchableOpacity, StyleSheet, ScrollView, ActivityIndicator, KeyboardAvoidingView, Platform } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { colors } from '../styles/colors';
import { commonStyles } from '../styles/commonStyles';
import { API_BASE_URL } from '../config/api';

export default function EmailReplyModal({ visible, onClose, userId, threadId, to }) {
  const [loadingDraft, setLoadingDraft] = useState(false);
  const [sending, setSending] = useState(false);
  const [sentJustNow, setSentJustNow] = useState(false);
  const [error, setError] = useState(null);
  const [original, setOriginal] = useState({ subject: '', from: '', date: '', body: '' });
  const [draft, setDraft] = useState('');
  const [mode, setMode] = useState('reply'); // 'reply' or 'forward'
  const [forwardTo, setForwardTo] = useState(''); // For forward mode
  const inputRef = useRef(null);
  const [showFullOriginal, setShowFullOriginal] = useState(false);
  const displayFrom = (() => {
    if (!original.from) return '';
    // Try to extract Display Name and email
    const m = /^(.*?)\s*<([^>]+)>$/.exec(original.from);
    return m ? `${m[1]}  <${m[2]}>` : original.from;
  })();
  const avatarLetter = (original.from || to || 'U').trim().charAt(0)?.toUpperCase?.() || 'U';
  // Frontend guard: strip duplicated subject lines at top of the original body
  const cleanedOriginalBody = (() => {
    const subject = original.subject || '';
    const body = original.body || '';
    if (!subject || !body) return body;
    const normalize = (s, lax = false) => {
      let x = (s || '').replace(/\s+/g, ' ').trim().replace(/^[\[\(\{]+|[\]\)\}]+$/g, '');
      x = x.replace(/^((re|fw|fwd)\s*:)\s*/i, '').replace(/\[[^\]]+\]\s*/g, '');
      x = x.toLowerCase();
      return lax ? x.replace(/[^a-z0-9]+/g, ' ').trim() : x;
    };
    const subjStrict = normalize(subject, false);
    const subjLax = normalize(subject, true);
    const lines = body.split(/\r?\n/);
    let i = 0;
    while (i < lines.length && !lines[i].trim()) i++;
    const matchLine = (idx) => {
      const s = normalize(lines[idx], false);
      const l = normalize(lines[idx], true);
      return s === subjStrict || l === subjLax;
    };
    let drop = 0;
    if (i < lines.length && matchLine(i)) {
      drop = 1;
      if (i + 1 < lines.length && matchLine(i + 1)) drop = 2;
    }
    if (drop > 0) {
      const kept = lines.slice(0, i).concat(lines.slice(i + drop));
      return kept.join('\n').replace(/^\n+/, '');
    }
    return body;
  })();

  useEffect(() => {
    async function loadData() {
      if (!visible || !userId || !threadId) return;
      setLoadingDraft(true);
      setError(null);
      // Reset mode when modal opens (only if not already set)
      if (mode === 'reply') {
        setForwardTo('');
      }
      try {
        // 1) fetch original message
        const d = await fetch(`${API_BASE_URL}/api/gmail/thread-detail`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id: userId, thread_id: threadId }),
        });
        const detail = await d.json();
        if (detail?.success) {
          setOriginal({
            subject: detail.subject || '',
            from: detail.from || '',
            date: detail.date || '',
            body: detail.body || '',
          });
        }
        // 2) fetch draft based on mode
        if (mode === 'reply' && to) {
          const r = await fetch(`${API_BASE_URL}/api/gmail/draft-reply`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: userId, thread_id: threadId, to }),
          });
          const data = await r.json();
          if (data?.success && data.body) {
            setDraft(data.body);
          } else if (data?.action === 'connect_google') {
            setError('Google not connected. Please connect and retry.');
          } else {
            setError(data?.error || 'Failed to generate draft.');
          }
        } else if (mode === 'forward') {
          // In forward mode, start with empty draft (will be generated when 'to' is entered)
          setDraft('');
        }
      } catch (e) {
        setError(e?.message || 'Network error.');
      } finally {
        setLoadingDraft(false);
      }
    }
    loadData();
  }, [visible, userId, threadId, to]);
  
  // Separate effect to handle mode changes and generate drafts
  useEffect(() => {
    if (!visible || !userId || !threadId) return;
    
    if (mode === 'forward') {
      // Generate forward draft immediately when forward mode is opened
      setLoadingDraft(true);
      fetch(`${API_BASE_URL}/api/gmail/draft-forward`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          user_id: userId, 
          thread_id: threadId,
          to: forwardTo.trim() || '' // Optional, can be empty
        }),
      })
        .then(r => r.json())
        .then(data => {
          if (data?.success && data.body) {
            setDraft(data.body);
          } else {
            // If draft generation fails, just leave draft empty
            setDraft('');
          }
          setLoadingDraft(false);
        })
        .catch(e => {
          console.error('Failed to generate forward draft:', e);
          setDraft('');
          setLoadingDraft(false);
        });
    } else if (mode === 'reply') {
      setForwardTo('');
    }
  }, [mode, visible, userId, threadId]); // Removed forwardTo from dependencies

  // Focus draft input when visible and draft is ready
  useEffect(() => {
    if (!visible) return;
    if (loadingDraft) return;
    const t = setTimeout(() => {
      try {
        inputRef.current?.focus();
      } catch {}
    }, 50);
    return () => clearTimeout(t);
  }, [visible, loadingDraft]);

  const handleSend = async () => {
    setSending(true);
    setError(null);
    try {
      let endpoint, body;
      
      if (mode === 'forward') {
        if (!forwardTo.trim()) {
          setError('Please enter a recipient email address.');
          setSending(false);
          return;
        }
        endpoint = `${API_BASE_URL}/api/gmail/forward`;
        body = JSON.stringify({ 
          user_id: userId, 
          thread_id: threadId, 
          to: forwardTo.trim(), 
          body: draft 
        });
      } else {
        // Reply mode
        if (!to) {
          setError('Recipient email is required.');
          setSending(false);
          return;
        }
        endpoint = `${API_BASE_URL}/api/gmail/reply`;
        body = JSON.stringify({ 
          user_id: userId, 
          thread_id: threadId, 
          to, 
          body: draft 
        });
      }
      
      const r = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: body,
      });
      const data = await r.json();
      if (data?.success) {
        setSentJustNow(true);
        setDraft('');
        setForwardTo('');
        setTimeout(() => {
          setSentJustNow(false);
          onClose(true);
        }, 600);
      } else if (data?.action === 'connect_google') {
        setError('Google not connected. Please connect and retry.');
      } else {
        setError(data?.error || `Failed to ${mode === 'forward' ? 'forward' : 'send reply'}.`);
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
          {/* Header - Gmail-like */}
          <View style={styles.headerRow}>
            <View style={styles.headerLeft}>
              <View style={styles.headerText}>
                <Text style={styles.subject} numberOfLines={2}>
                  {original.subject || '(No subject)'}
                </Text>
                <Text style={styles.fromLine} numberOfLines={1}>
                  {displayFrom || to}
                </Text>
              </View>
            </View>
            <View style={styles.headerRight}>
              <TouchableOpacity onPress={() => onClose(false)} style={styles.iconBtn}>
                <Text style={styles.iconBtnText}>✕</Text>
              </TouchableOpacity>
            </View>
          </View>
          {/* Toolbar */}
          <View style={styles.toolbar}>
            <TouchableOpacity 
              style={[styles.toolbarBtn, mode === 'reply' && styles.toolbarBtnActive]}
              onPress={() => {
                setMode('reply');
                setForwardTo('');
                // Focus draft input
                setTimeout(() => inputRef.current?.focus(), 100);
              }}>
              <Text style={[styles.toolbarBtnText, mode === 'reply' && styles.toolbarBtnTextActive]}>Reply</Text>
            </TouchableOpacity>
            <TouchableOpacity 
              style={[styles.toolbarBtn, mode === 'forward' && styles.toolbarBtnActive]}
              onPress={() => {
                console.log('Forward button clicked, setting mode to forward');
                setMode('forward');
                setDraft(''); // Clear draft when switching to forward
                setForwardTo(''); // Reset forwardTo when switching
              }}>
              <Text style={[styles.toolbarBtnText, mode === 'forward' && styles.toolbarBtnTextActive]}>Forward</Text>
            </TouchableOpacity>
            <View style={{flex: 1}} />
            <Text style={styles.threadMeta}>Thread: {String(threadId || '').slice(-8)}</Text>
          </View>

          {/* Forward To field - only show in forward mode */}
          {mode === 'forward' && (
            <View style={styles.forwardToContainer}>
              <Text style={styles.forwardToTitle}>Forward Email</Text>
              <View style={styles.forwardToRow}>
                <Text style={styles.forwardToLabel}>To:</Text>
                <TextInput
                  style={styles.forwardToInput}
                  placeholder="Enter recipient email address"
                  placeholderTextColor={colors.primary[900] + '60'}
                  value={forwardTo}
                  onChangeText={(text) => {
                    console.log('ForwardTo changed:', text);
                    setForwardTo(text);
                  }}
                  keyboardType="email-address"
                  autoCapitalize="none"
                  autoCorrect={false}
                  autoFocus={true}
                />
              </View>
            </View>
          )}

          {/* Smart suggestions - only show in reply mode */}
          {mode === 'reply' && (
            <View style={styles.suggestionRow}>
              <TouchableOpacity
                style={styles.suggestionBtn}
                disabled={sending || loadingDraft}
                onPress={async () => {
                  try {
                    setDraft(''); // clear before loading
                    const r = await fetch(`${API_BASE_URL}/api/gmail/draft-reply`, {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ user_id: userId, thread_id: threadId, to, user_points: 'Agree politely, short and warm.' }),
                    });
                    const data = await r.json();
                    if (data?.success && data.body) setDraft(data.body);
                  } catch {}
                }}>
                <Text style={styles.suggestionText}>Sounds good 👍</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.suggestionBtn}
                disabled={sending || loadingDraft}
                onPress={async () => {
                  try {
                    setDraft('');
                    const r = await fetch(`${API_BASE_URL}/api/gmail/draft-reply`, {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ user_id: userId, thread_id: threadId, to, user_points: 'Propose scheduling a meeting. Provide 2 time windows.' }),
                    });
                    const data = await r.json();
                    if (data?.success && data.body) setDraft(data.body);
                  } catch {}
                }}>
                <Text style={styles.suggestionText}>Schedule a meeting</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.suggestionBtn}
                disabled={sending || loadingDraft}
                onPress={async () => {
                  try {
                    setDraft('');
                    const r = await fetch(`${API_BASE_URL}/api/gmail/draft-reply`, {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ user_id: userId, thread_id: threadId, to, user_points: 'Write a brief summary of the key points before replying.' }),
                    });
                    const data = await r.json();
                    if (data?.success && data.body) setDraft(data.body);
                  } catch {}
                }}>
                <Text style={styles.suggestionText}>Quick summary</Text>
              </TouchableOpacity>
            </View>
          )}

          {/* Original message */}
          <View style={styles.originalWrapper}>
            <View style={styles.msgHeaderRow}>
              <View style={styles.msgHeaderLeft}>
                <View style={styles.msgAvatar}>
                  <Text style={styles.msgAvatarText}>{avatarLetter}</Text>
                </View>
                <View style={styles.msgHeaderText}>
                  <Text style={styles.msgFrom} numberOfLines={1}>
                    {displayFrom || to}
                  </Text>
                  <Text style={styles.msgTo} numberOfLines={1}>
                    to me
                  </Text>
                </View>
              </View>
              <Text style={styles.msgDate}>{original.date}</Text>
            </View>
            <ScrollView style={styles.originalBody}>
              <Text
                style={styles.originalText}
                numberOfLines={showFullOriginal ? undefined : 12}
              >
                {cleanedOriginalBody}
              </Text>
            </ScrollView>
            <View style={styles.trimRow}>
              <TouchableOpacity onPress={() => setShowFullOriginal((v) => !v)}>
                <Text style={styles.trimBtn}>
                  {showFullOriginal ? 'Show less' : 'Show trimmed content'}
                </Text>
              </TouchableOpacity>
            </View>
          </View>

          {/* Draft editor */}
          <View style={styles.editor}>
            {/* Reply author header inside the message box */}
            <View style={styles.replyMsgHeader}>
              <View style={styles.replyAvatar}>
                <Text style={styles.replyAvatarText}>{(userId || 'M').trim().charAt(0).toUpperCase()}</Text>
              </View>
              <Text style={styles.replyLabel}>Me</Text>
            </View>
            {loadingDraft && mode === 'reply' ? (
              <View style={styles.loadingBox}>
                <ActivityIndicator color={colors.secondary[600]} />
                <Text style={styles.loadingText}>Preparing draft...</Text>
              </View>
            ) : (
              <TextInput
                ref={inputRef}
                multiline
                value={draft}
                onChangeText={setDraft}
                placeholder={mode === 'forward' ? "Add a message (optional)..." : "Draft will appear here..."}
                style={styles.textarea}
                placeholderTextColor={colors.primary[900] + '60'}
                autoFocus
              />
            )}
          </View>

          {error ? <Text style={styles.error}>{error}</Text> : null}

          <View style={styles.actions}>
            <TouchableOpacity onPress={() => onClose(false)} style={styles.cancelButton}>
              <Text style={styles.cancelText}>Cancel</Text>
            </TouchableOpacity>
            <TouchableOpacity 
              disabled={sending || !draft.trim() || (mode === 'forward' && !forwardTo.trim())} 
              onPress={handleSend} 
              style={styles.sendWrapper}>
              <LinearGradient colors={[colors.accent[500], colors.accent[600]]} style={styles.sendButton}>
                <Text style={styles.sendText}>
                  {sentJustNow ? 'Sent ✓' : sending ? (mode === 'forward' ? 'Forwarding...' : 'Sending...') : (mode === 'forward' ? 'Forward' : 'Send')}
                </Text>
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
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    flex: 1,
    minWidth: 0,
  },
  headerText: {
    flex: 1,
    minWidth: 0,
  },
  subject: {
    fontSize: 16,
    fontWeight: '700',
    color: colors.primary[900],
  },
  fromLine: {
    fontSize: 12,
    color: colors.primary[900] + '80',
    marginTop: 2,
  },
  headerRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  dateText: {
    fontSize: 11,
    color: colors.primary[900] + '70',
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
  avatar: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.secondary[500],
  },
  avatarText: {
    color: '#fff',
    fontWeight: '700',
  },
  toolbar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 10,
  },
  toolbarBtn: {
    borderRadius: 8,
    backgroundColor: colors.primary[200] + '40',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderWidth: 1,
    borderColor: colors.dark[500] + '10',
  },
  toolbarBtnText: {
    fontSize: 12,
    color: colors.primary[900],
    fontWeight: '500',
  },
  threadMeta: {
    fontSize: 10,
    color: colors.primary[900] + '60',
  },
  toolbarBtnActive: {
    backgroundColor: colors.accent[500] + '30',
    borderColor: colors.accent[500] + '50',
  },
  toolbarBtnTextActive: {
    color: colors.accent[700],
    fontWeight: '600',
  },
  forwardToContainer: {
    marginBottom: 12,
    marginTop: 8,
    paddingVertical: 14,
    paddingHorizontal: 14,
    backgroundColor: colors.accent[500] + '15',
    borderRadius: 12,
    borderWidth: 2,
    borderColor: colors.accent[500] + '40',
    ...commonStyles.shadowMd,
  },
  forwardToTitle: {
    fontSize: 15,
    fontWeight: '700',
    color: colors.accent[700],
    marginBottom: 10,
  },
  forwardToRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  forwardToLabel: {
    fontSize: 14,
    color: colors.primary[900],
    fontWeight: '700',
    minWidth: 35,
  },
  forwardToInput: {
    flex: 1,
    borderWidth: 1.5,
    borderColor: colors.accent[500] + '50',
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 10,
    fontSize: 15,
    color: colors.primary[900],
    backgroundColor: '#fff',
    minHeight: 44,
  },
  suggestionRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginBottom: 8,
  },
  suggestionBtn: {
    borderRadius: 8,
    backgroundColor: colors.primary[200] + '30',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderWidth: 1,
    borderColor: colors.dark[500] + '10',
  },
  suggestionText: {
    fontSize: 12,
    color: colors.primary[900],
    fontWeight: '500',
  },
  originalWrapper: {
    backgroundColor: colors.primary[200] + '30',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.dark[500] + '10',
    marginBottom: 10,
  },
  originalBody: {
    maxHeight: 120,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  originalText: {
    fontSize: 13,
    color: colors.primary[900],
    lineHeight: 18,
  },
  msgHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 10,
    paddingTop: 8,
  },
  msgHeaderLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    flex: 1,
    minWidth: 0,
  },
  msgAvatar: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.secondary[500],
  },
  msgAvatarText: {
    color: '#fff',
    fontWeight: '700',
    fontSize: 12,
  },
  msgHeaderText: {
    flex: 1,
    minWidth: 0,
  },
  msgFrom: {
    fontSize: 13,
    color: colors.primary[900],
    fontWeight: '600',
  },
  msgTo: {
    fontSize: 11,
    color: colors.primary[900] + '70',
  },
  msgDate: {
    fontSize: 11,
    color: colors.primary[900] + '60',
    marginRight: 8,
  },
  trimRow: {
    paddingHorizontal: 10,
    paddingBottom: 8,
    paddingTop: 4,
  },
  trimBtn: {
    fontSize: 12,
    color: colors.secondary[700],
    fontWeight: '500',
  },
  replyHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    marginBottom: 6,
    paddingHorizontal: 2,
  },
  replyAvatar: {
    width: 24,
    height: 24,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.accent[500],
  },
  replyAvatarText: {
    color: '#fff',
    fontWeight: '700',
    fontSize: 11,
  },
  replyLabel: {
    fontSize: 12,
    color: colors.primary[900],
    fontWeight: '600',
  },
  editor: {
    height: 180,
    borderRadius: 12,
    backgroundColor: colors.primary[100] + '60',
    borderWidth: 1,
    borderColor: colors.dark[500] + '10',
    overflow: 'hidden',
  },
  replyMsgHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: colors.dark[500] + '10',
    backgroundColor: colors.primary[200] + '25',
  },
  textarea: {
    flex: 1,
    padding: 10,
    color: colors.primary[900],
    textAlignVertical: 'top',
  },
  loadingBox: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
  },
  loadingText: {
    color: colors.secondary[700],
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


