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
} from 'react-native';
import {useRoute, useNavigation} from '@react-navigation/native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {Svg, Line, Path} from 'react-native-svg';

import {theme} from '../styles/theme';
import {API_BASE_URL} from '../config/api';

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
  const {userId, sessionId, seedPrompt} = route.params || {};

  const [input, setInput] = useState('');
  const [messages, setMessages] = useState([]); // [{role:'user'|'assistant', text}]
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef(null);
  const seedConsumed = useRef(false);

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

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || loading) return;

    setMessages((prev) => [...prev, {role: 'user', text}]);
    setInput('');
    setLoading(true);
    scrollToBottom();

    try {
      const r = await fetch(`${API_BASE_URL}/api/chat`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          message: text,
          user_id: userId,
          session_id: sessionId,
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
      setMessages((prev) => [...prev, {role: 'assistant', text: reply || '…'}]);
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        {role: 'assistant', text: `Sorry — ${String(e?.message || e)}`},
      ]);
    } finally {
      setLoading(false);
      scrollToBottom();
    }
  }, [input, loading, userId, sessionId]);

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

          {loading && (
            <View style={[styles.bubble, styles.bubbleAssistant, styles.bubbleLoading]}>
              <ActivityIndicator color={theme.colors.textSecondary} size="small" />
            </View>
          )}
        </ScrollView>

        <View style={styles.inputRow}>
          <View style={styles.pill}>
            <TextInput
              value={input}
              onChangeText={setInput}
              onSubmitEditing={send}
              placeholder="Schedule or add new task..."
              placeholderTextColor={theme.colors.textSecondary}
              style={[
                styles.input,
                Platform.OS === 'web' && {outline: 'none', outlineWidth: 0, boxShadow: 'none'},
              ]}
              returnKeyType="send"
              blurOnSubmit={false}
              multiline={false}
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
  bubbleLoading: {
    alignSelf: 'flex-start',
    paddingHorizontal: 16,
    paddingVertical: 10,
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

  inputRow: {
    paddingHorizontal: 20,
    paddingTop: 8,
    paddingBottom: 14,
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
