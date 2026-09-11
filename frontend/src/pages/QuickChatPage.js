import React, {useCallback, useEffect, useRef, useState} from 'react';
import {
  View,
  Text,
  TextInput,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
  Alert,
  Share,
  Linking,
} from 'react-native';
import {useRoute, useNavigation} from '@react-navigation/native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {Svg, Line, Path} from 'react-native-svg';

import {theme} from '../styles/theme';
import {API_BASE_URL, CORE_BACKEND_URL} from '../config/api';
import {extractEmailAddress} from '../utils/emailParse';
import {buildChatMetadata} from '../utils/chatClientMetadata';
import {emitDataChange} from '../utils/dataEvents';
import {useVoiceCapture} from '../hooks/useVoiceCapture';

/** Keep GET URL under a safe length; Gmail compose uses query params. */
const GMAIL_COMPOSE_URL_MAX = 7200;

/**
 * Opens Gmail web compose with pre-filled reply (user taps Send in Gmail).
 * Avoids server-side ``messages.send``; threading is best-effort via ``th`` when a thread id exists.
 */
function buildGmailComposeDeepLink({to, subject, body, threadId}) {
  const subjRaw = (subject || '').trim();
  const su = /^re:/i.test(subjRaw) ? subjRaw : subjRaw ? `Re: ${subjRaw}` : 'Re:';
  let bodyText = body || '';
  const th = (threadId || '').trim();
  const thParam = th ? `&th=${encodeURIComponent(th)}` : '';
  const prefix = `https://mail.google.com/mail/u/0/?view=cm&fs=1&tf=cm&to=${encodeURIComponent(
    (to || '').trim(),
  )}&su=${encodeURIComponent(su)}&body=`;
  while (prefix.length + encodeURIComponent(bodyText).length + thParam.length > GMAIL_COMPOSE_URL_MAX && bodyText.length > 120) {
    bodyText = bodyText.slice(0, Math.floor(bodyText.length * 0.88));
  }
  if (prefix.length + encodeURIComponent(bodyText).length + thParam.length > GMAIL_COMPOSE_URL_MAX) {
    bodyText = bodyText.slice(0, 80);
  }
  return prefix + encodeURIComponent(bodyText) + thParam;
}

/**
 * Figma-styled "quick" chat — opened from Home's + button and from
 * "Generate answer" on an action item. Uses the same backend as the
 * legacy ChatPage (POST /api/chat) but with the new soft UI:
 *   - Rounded bubble conversation
 *   - Bottom pill input "Schedule or add new task..." with an X icon
 *     (clear-if-filled, close-if-empty)
 *   - No email/calendar panels — this is a focused surface.
 */
export default function QuickChatPage() {
  const route = useRoute();
  const navigation = useNavigation();
  const {userId, sessionId, seedPrompt, replyDraft} = route.params || {};

  const [input, setInput] = useState('');
  const [messages, setMessages] = useState([]); // [{role:'user'|'assistant', text}]
  const [loading, setLoading] = useState(false);
  const [editableDraft, setEditableDraft] = useState('');
  const [showReplyComposer, setShowReplyComposer] = useState(false);
  const [sendReplyError, setSendReplyError] = useState('');
  /** Gmail: idle → sending → opened_gmail (compose opened in browser/app; user sends there). */
  const [gmailReplyBtn, setGmailReplyBtn] = useState('idle');
  const [rewriteAsInstruction, setRewriteAsInstruction] = useState('');
  const [polishLoading, setPolishLoading] = useState(false);
  const scrollRef = useRef(null);
  const sendHandlerRef = useRef(async () => {});
  const seedConsumed = useRef(false);
  const replyDraftRef = useRef(null);
  const replyDraftAttachedRef = useRef(false);
  const pendingReplyDraftSendRef = useRef(false);

  // Persist reply-draft payload for the first /api/chat call only (full excerpt for the model).
  useEffect(() => {
    if (replyDraft && typeof replyDraft === 'object') {
      replyDraftRef.current = replyDraft;
      replyDraftAttachedRef.current = false;
      pendingReplyDraftSendRef.current = false;
      setGmailReplyBtn('idle');
      setRewriteAsInstruction('');
    }
    try {
      if (replyDraft) navigation.setParams({replyDraft: undefined});
    } catch {
      // no-op
    }
  }, [replyDraft, navigation]);

  useEffect(() => {
    const unsub = navigation.addListener('beforeRemove', () => {
      replyDraftRef.current = null;
      replyDraftAttachedRef.current = false;
      pendingReplyDraftSendRef.current = false;
      setShowReplyComposer(false);
      setEditableDraft('');
      setGmailReplyBtn('idle');
      setRewriteAsInstruction('');
      setPolishLoading(false);
    });
    return unsub;
  }, [navigation]);

  // Consume a seeded prompt (e.g. from Home "Generate answer")
  useEffect(() => {
    if (!seedPrompt || seedConsumed.current) return;
    seedConsumed.current = true;
    setInput(String(seedPrompt));
    try {
      navigation.setParams({seedPrompt: undefined});
    } catch {
      // no-op
    }
  }, [seedPrompt, navigation]);

  const scrollToBottom = () => {
    requestAnimationFrame(() => {
      scrollRef.current?.scrollToEnd?.({animated: true});
    });
  };

  const goBack = () => {
    if (navigation.canGoBack()) navigation.goBack();
    else navigation.navigate('Home', {userId, sessionId});
  };

  const onTrailingPress = () => {
    if (input.trim().length > 0) send();
    else goBack();
  };

  const send = useCallback(async (messageOverride) => {
    const text =
      messageOverride !== undefined && messageOverride !== null
        ? String(messageOverride).trim()
        : input.trim();
    if (!text || loading) return;

    const attachDraft =
      replyDraftRef.current &&
      !replyDraftAttachedRef.current &&
      (replyDraftRef.current.snippet || replyDraftRef.current.subject || replyDraftRef.current.from_header);

    if (attachDraft) {
      pendingReplyDraftSendRef.current = true;
    }

    setMessages((prev) => [...prev, {role: 'user', text}]);
    setInput('');
    setLoading(true);
    scrollToBottom();

    try {
      const body = {
        message: text,
        user_id: userId,
        session_id: sessionId,
      };
      const meta = buildChatMetadata();
      if (meta) body.metadata = meta;
      if (attachDraft) {
        body.reply_draft = replyDraftRef.current;
      }

      const r = await fetch(`${API_BASE_URL}/api/chat`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data?.error || `HTTP ${r.status}`);

      if (attachDraft) {
        replyDraftAttachedRef.current = true;
      }

      let reply = data?.reply || '';
      if (typeof reply !== 'string') {
        try {
          reply = JSON.stringify(reply);
        } catch {
          reply = String(reply);
        }
      }

      const singleDraftUi =
        pendingReplyDraftSendRef.current && replyDraftRef.current;
      if (singleDraftUi) {
        pendingReplyDraftSendRef.current = false;
        setEditableDraft((reply || '').trim());
        const src = String(replyDraftRef.current.source || '').toLowerCase();
        setShowReplyComposer(src === 'gmail' || src === 'slack');
        setGmailReplyBtn('idle');
        // Draft appears only in the composer (same bg as screen) — no assistant bubble.
      } else {
        setMessages((prev) => [...prev, {role: 'assistant', text: reply || '…'}]);
      }

      // A chat turn may have spawned a task, project, or meeting server-side
      // (see ``handle_chat_turn`` in the backend). Poke every subscribed page
      // so the new row shows up without a manual refresh.
      emitDataChange('chat:turn');
    } catch (e) {
      pendingReplyDraftSendRef.current = false;
      setMessages((prev) => [
        ...prev,
        {role: 'assistant', text: `Sorry — ${String(e?.message || e)}`},
      ]);
    } finally {
      setLoading(false);
      scrollToBottom();
    }
  }, [input, loading, userId, sessionId]);

  const sendGmailReply = useCallback(async () => {
    const rd = replyDraftRef.current;
    const bodyText = (editableDraft || '').trim();
    const threadId = rd?.thread_id != null ? String(rd.thread_id).trim() : '';
    const toRaw =
      (rd?.reply_to_email && String(rd.reply_to_email).trim()) ||
      extractEmailAddress(String(rd?.from_header || ''));
    const to = (toRaw || '').trim();
    setSendReplyError('');
    if (!bodyText) { setSendReplyError('Draft is empty.'); return; }
    if (!to) { setSendReplyError('Could not detect recipient email.'); return; }
    setGmailReplyBtn('sending');
    try {
      const r = await fetch(`${CORE_BACKEND_URL}/api/gmail/reply`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({thread_id: threadId, to, body: bodyText}),
      });
      const data = await r.json().catch(() => ({}));
      if (data?.action === 'connect_google') {
        setGmailReplyBtn('idle');
        setSendReplyError('Gmail not connected. Please reconnect Google.');
        return;
      }
      if (!data?.success) throw new Error(data?.error || data?.message || `HTTP ${r.status}`);
      setGmailReplyBtn('opened_gmail');
    } catch (e) {
      setGmailReplyBtn('idle');
      setSendReplyError(String(e?.message || e));
    }
  }, [editableDraft]);

  const polishDraftWithAi = useCallback(async () => {
    const draft = (editableDraft || '').trim();
    if (!draft) {
      Alert.alert('No draft', 'Write or generate a draft first.');
      return;
    }
    const instruction = (rewriteAsInstruction || '').trim() || 'Polish for clarity and a professional tone.';
    setPolishLoading(true);
    try {
      const r = await fetch(`${API_BASE_URL}/api/chat`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          message: 'Polish email draft.',
          user_id: userId,
          session_id: sessionId,
          draft_polish: {
            instruction,
            draft,
          },
        }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data?.error || `HTTP ${r.status}`);
      let reply = data?.reply || '';
      if (typeof reply !== 'string') {
        try {
          reply = JSON.stringify(reply);
        } catch {
          reply = String(reply);
        }
      }
      setEditableDraft((reply || '').trim());
    } catch (e) {
      Alert.alert('Polish failed', String(e?.message || e));
    } finally {
      setPolishLoading(false);
    }
  }, [editableDraft, rewriteAsInstruction, userId, sessionId]);

  const shareSlackDraft = useCallback(async () => {
    const t = (editableDraft || '').trim();
    if (!t) {
      Alert.alert('Nothing to share', 'Add text to your draft first.');
      return;
    }
    try {
      await Share.share({message: t});
    } catch (e) {
      Alert.alert('Share', String(e?.message || e));
    }
  }, [editableDraft]);

  sendHandlerRef.current = send;

  const {
    isSupported: voiceSupported,
    isListening,
    transcribing,
    startListening,
    stopListening,
  } = useVoiceCapture({
    apiBaseUrl: API_BASE_URL,
    transcriptHandlerRef: sendHandlerRef,
    languageCode: 'en-US',
  });

  const toggleQuickVoice = async () => {
    if (isListening) await stopListening();
    else await startListening();
  };

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={{flex: 1}}>
        <View style={styles.topBar}>
          <View style={{width: 40}} />
          <Text style={styles.brand}>Aivis</Text>
          <TouchableOpacity
            onPress={goBack}
            style={styles.topCloseBtn}
            activeOpacity={0.85}
            hitSlop={{top: 8, bottom: 8, left: 8, right: 8}}>
            <CloseIcon size={16} />
          </TouchableOpacity>
        </View>

        <ScrollView
          ref={scrollRef}
          style={styles.scroll}
          contentContainerStyle={styles.scrollContent}
          showsVerticalScrollIndicator={false}
          onContentSizeChange={scrollToBottom}>
          {messages.length === 0 ? (
            <View style={styles.emptyWrap}>
              <Text style={styles.emptyTitle}>What can I help with?</Text>
              <Text style={styles.emptyHint}>
                Ask me anything, or type a task and I'll schedule it.
              </Text>
            </View>
          ) : (
            messages.map((m, i) => <Bubble key={`${i}-${m.role}`} role={m.role} text={m.text} />)
          )}

          {loading ? (
            <View style={styles.loadingRow}>
              <ActivityIndicator color={theme.colors.textSecondary} size="small" />
            </View>
          ) : null}
        </ScrollView>

        {showReplyComposer && replyDraftRef.current ? (
          <View style={styles.replyComposer}>
            <Text style={styles.replyComposerTitle}>You can edit your reply</Text>
            <Text style={styles.replyComposerHint}>
              {String(replyDraftRef.current.source || '').toLowerCase() === 'gmail'
                ? gmailReplyBtn === 'opened_gmail'
                  ? 'Reply sent successfully.'
                  : 'Review your draft and hit Send Reply.'
                : 'Share or paste into Slack when ready.'}
            </Text>
            <TextInput
              value={editableDraft}
              onChangeText={setEditableDraft}
              multiline
              editable={gmailReplyBtn !== 'opened_gmail'}
              placeholder="Your draft…"
              placeholderTextColor={theme.colors.textSecondary}
              style={[
                styles.replyComposerInput,
                Platform.OS === 'web' && {outline: 'none', outlineWidth: 0},
              ]}
            />
            {gmailReplyBtn !== 'opened_gmail' ? (
              <View style={styles.rewriteBlock}>
                <Text style={styles.rewriteLabel}>Rewrite email as</Text>
                <TextInput
                  value={rewriteAsInstruction}
                  onChangeText={setRewriteAsInstruction}
                  multiline
                  placeholder="e.g. shorter, warmer, push back politely, add thanks…"
                  placeholderTextColor={theme.colors.textSecondary}
                  style={[
                    styles.rewriteInput,
                    Platform.OS === 'web' && {outline: 'none', outlineWidth: 0},
                  ]}
                />
                <TouchableOpacity
                  onPress={polishDraftWithAi}
                  disabled={polishLoading || !(editableDraft || '').trim()}
                  style={[
                    styles.polishBtn,
                    (polishLoading || !(editableDraft || '').trim()) && styles.polishBtnDisabled,
                  ]}
                  activeOpacity={0.85}>
                  {polishLoading ? (
                    <ActivityIndicator color={theme.colors.textPrimary} size="small" />
                  ) : (
                    <Text style={styles.polishBtnText}>Polish with AI</Text>
                  )}
                </TouchableOpacity>
              </View>
            ) : null}
            <View style={styles.replyComposerActions}>
              {String(replyDraftRef.current.source || '').toLowerCase() === 'gmail' ? (
                <TouchableOpacity
                  onPress={sendGmailReply}
                  disabled={
                    gmailReplyBtn === 'sending' ||
                    gmailReplyBtn === 'opened_gmail' ||
                    !(editableDraft || '').trim()
                  }
                  style={[
                    styles.sendReplyBtn,
                    gmailReplyBtn === 'idle' && !(editableDraft || '').trim() && styles.sendReplyBtnDisabled,
                    gmailReplyBtn === 'sending' && styles.sendReplyBtnDisabled,
                    gmailReplyBtn === 'opened_gmail' && styles.sendReplyBtnSent,
                  ]}
                  activeOpacity={0.85}>
                  <Text style={styles.sendReplyBtnText}>
                    {gmailReplyBtn === 'sending'
                      ? 'Sending…'
                      : gmailReplyBtn === 'opened_gmail'
                        ? 'Sent'
                        : 'Send Reply'}
                  </Text>
                </TouchableOpacity>
              ) : (
                <TouchableOpacity onPress={shareSlackDraft} style={styles.sendReplyBtn} activeOpacity={0.85}>
                  <Text style={styles.sendReplyBtnText}>Share draft</Text>
                </TouchableOpacity>
              )}
            </View>
          </View>
        ) : null}

        <View style={styles.inputRow}>
          <TouchableOpacity
            onPress={() => {
              void toggleQuickVoice();
            }}
            disabled={!voiceSupported || loading || transcribing}
            style={[
              styles.micPillBtn,
              isListening && styles.micPillBtnActive,
              (!voiceSupported || loading || transcribing) && styles.micPillBtnDisabled,
            ]}
            activeOpacity={0.85}
            accessibilityLabel={isListening ? 'Stop recording' : 'Speak'}>
            <Svg
              width={20}
              height={20}
              viewBox="0 0 24 24"
              fill={isListening ? theme.colors.textOnDark : theme.colors.textSecondary}>
              <Path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z" />
              <Path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z" />
            </Svg>
          </TouchableOpacity>
          <View style={styles.pill}>
            <TextInput
              value={input}
              onChangeText={setInput}
              onSubmitEditing={() => send()}
              placeholder={
                transcribing
                  ? 'Transcribing…'
                  : isListening
                    ? 'Listening…'
                    : 'Schedule or add new task...'
              }
              placeholderTextColor={theme.colors.textSecondary}
              style={[
                styles.input,
                Platform.OS === 'web' && {outline: 'none', outlineWidth: 0, boxShadow: 'none'},
              ]}
              returnKeyType="send"
              blurOnSubmit={false}
              multiline={false}
              editable={!isListening && !transcribing}
            />
            <TouchableOpacity
              onPress={onTrailingPress}
              style={styles.trailingBtn}
              activeOpacity={0.85}
              hitSlop={{top: 8, bottom: 8, left: 8, right: 8}}>
              <ArrowUpIcon size={16} />
            </TouchableOpacity>
          </View>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function Bubble({role, text}) {
  const isUser = role === 'user';
  return (
    <View style={[styles.bubbleRow, isUser ? styles.rowUser : styles.rowAssistant]}>
      <View
        style={[
          styles.bubble,
          isUser ? styles.bubbleUser : styles.bubbleAssistant,
        ]}>
        <Text style={[styles.bubbleText, isUser && styles.bubbleTextUser]}>{text}</Text>
      </View>
    </View>
  );
}

function CloseIcon({size = 16}) {
  const s = size;
  return (
    <Svg width={s} height={s} viewBox="0 0 24 24" fill="none">
      <Line
        x1="6"
        y1="6"
        x2="18"
        y2="18"
        stroke={theme.colors.textSecondary}
        strokeWidth={1.8}
        strokeLinecap="round"
      />
      <Line
        x1="18"
        y1="6"
        x2="6"
        y2="18"
        stroke={theme.colors.textSecondary}
        strokeWidth={1.8}
        strokeLinecap="round"
      />
    </Svg>
  );
}

function ArrowUpIcon({size = 16}) {
  const s = size;
  return (
    <Svg width={s} height={s} viewBox="0 0 24 24" fill="none">
      <Path
        d="M12 19V5"
        stroke={theme.colors.textSecondary}
        strokeWidth={1.8}
        strokeLinecap="round"
      />
      <Path
        d="M5.5 11.5L12 5l6.5 6.5"
        stroke={theme.colors.textSecondary}
        strokeWidth={1.8}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Svg>
  );
}

const styles = StyleSheet.create({
  container: {flex: 1, backgroundColor: theme.colors.bg},

  topBar: {
    height: 48,
    paddingHorizontal: 16,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  brand: {
    ...theme.type.sectionHeader,
    color: theme.colors.textPrimary,
  },
  topCloseBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: theme.colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
    ...theme.shadow.card,
  },

  scroll: {flex: 1},
  scrollContent: {
    paddingHorizontal: 20,
    paddingVertical: 12,
    paddingBottom: 8,
    flexGrow: 1,
  },

  emptyWrap: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: 80,
  },
  emptyTitle: {
    ...theme.type.display,
    color: theme.colors.textPrimary,
    fontSize: 22,
    textAlign: 'center',
  },
  emptyHint: {
    marginTop: 8,
    ...theme.type.cardSubtitle,
    color: theme.colors.textSecondary,
    textAlign: 'center',
    maxWidth: 280,
  },

  bubbleRow: {
    width: '100%',
    flexDirection: 'row',
    marginBottom: 8,
  },
  rowUser: {justifyContent: 'flex-end'},
  rowAssistant: {justifyContent: 'flex-start'},

  bubble: {
    maxWidth: '82%',
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 18,
    ...theme.shadow.card,
  },
  bubbleUser: {
    backgroundColor: theme.colors.textPrimary,
    borderBottomRightRadius: 6,
  },
  bubbleAssistant: {
    backgroundColor: theme.colors.surface,
    borderBottomLeftRadius: 6,
  },
  bubbleText: {
    fontFamily: theme.fonts.regular,
    fontSize: 14,
    lineHeight: 20,
    color: theme.colors.textPrimary,
  },
  bubbleTextUser: {
    color: theme.colors.textOnDark,
  },

  loadingRow: {
    paddingVertical: 10,
    paddingHorizontal: 4,
    alignItems: 'flex-start',
  },

  replyComposer: {
    paddingHorizontal: 20,
    paddingTop: 4,
    paddingBottom: 8,
    borderTopWidth: 1,
    borderTopColor: theme.colors.border,
    backgroundColor: theme.colors.bg,
  },
  replyComposerTitle: {
    ...theme.type.cardSubtitle,
    color: theme.colors.textPrimary,
    fontWeight: '700',
    marginBottom: 4,
  },
  replyComposerHint: {
    ...theme.type.cardSubtitle,
    color: theme.colors.textSecondary,
    fontSize: 12,
    marginBottom: 8,
  },
  rewriteBlock: {
    marginTop: 14,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: theme.colors.border,
  },
  rewriteLabel: {
    ...theme.type.cardSubtitle,
    color: theme.colors.textPrimary,
    fontWeight: '700',
    marginBottom: 6,
  },
  rewriteInput: {
    minHeight: 56,
    maxHeight: 100,
    borderRadius: 0,
    paddingHorizontal: 4,
    paddingVertical: 8,
    marginBottom: 10,
    backgroundColor: theme.colors.bg,
    color: theme.colors.textPrimary,
    fontSize: 13,
    lineHeight: 18,
    borderWidth: 0,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.border,
    textAlignVertical: 'top',
  },
  polishBtn: {
    alignSelf: 'flex-start',
    paddingVertical: 10,
    paddingHorizontal: 16,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: theme.colors.borderStrong,
    backgroundColor: theme.colors.bg,
  },
  polishBtnDisabled: {
    opacity: 0.45,
  },
  polishBtnText: {
    ...theme.type.cardSubtitle,
    color: theme.colors.textPrimary,
    fontWeight: '700',
    fontSize: 13,
  },

  replyComposerInput: {
    minHeight: 100,
    maxHeight: 200,
    borderRadius: 0,
    paddingHorizontal: 4,
    paddingVertical: 8,
    backgroundColor: theme.colors.bg,
    color: theme.colors.textPrimary,
    fontSize: 14,
    lineHeight: 22,
    borderWidth: 0,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.border,
    textAlignVertical: 'top',
  },
  replyComposerActions: {
    marginTop: 10,
    flexDirection: 'row',
    justifyContent: 'flex-end',
  },
  sendReplyBtn: {
    backgroundColor: theme.colors.textPrimary,
    paddingVertical: 10,
    paddingHorizontal: 20,
    borderRadius: 12,
  },
  sendReplyBtnDisabled: {
    opacity: 0.45,
  },
  sendReplyBtnSent: {
    backgroundColor: theme.colors.schedule.emailTaskBorder,
    opacity: 1,
  },
  sendReplyBtnText: {
    color: theme.colors.textOnDark,
    fontWeight: '700',
    fontSize: 14,
  },

  inputRow: {
    paddingHorizontal: 20,
    paddingTop: 8,
    paddingBottom: 14,
    flexDirection: 'row',
    alignItems: 'center',
  },
  micPillBtn: {
    width: 48,
    height: 48,
    borderRadius: 24,
    marginRight: 10,
    backgroundColor: theme.colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
    ...theme.shadow.card,
  },
  micPillBtnActive: {
    backgroundColor: theme.colors.textPrimary,
  },
  micPillBtnDisabled: {
    opacity: 0.4,
  },
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radius.pill,
    paddingLeft: 20,
    paddingRight: 6,
    height: 52,
    ...theme.shadow.card,
  },
  input: {
    flex: 1,
    ...theme.type.searchPlaceholder,
    color: theme.colors.textPrimary,
    paddingVertical: 0,
    borderWidth: 0,
  },
  trailingBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: theme.colors.surfaceMuted,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
