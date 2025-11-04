import React, {useEffect, useRef} from 'react';
import {View, Text, ScrollView, StyleSheet} from 'react-native';
import {LinearGradient} from 'expo-linear-gradient';
import {Svg, Path, Circle} from 'react-native-svg';
import {colors} from '../styles/colors';
import {commonStyles} from '../styles/commonStyles';
import TypingIndicator from './TypingIndicator';
import WelcomeMessage from './WelcomeMessage';
import EmailList from './EmailList';

export default function MessageList({chat, loading, onEmailSelect}) {
  const scrollViewRef = useRef(null);

  // Auto-scroll to bottom when new messages are added or when AI finishes responding
  useEffect(() => {
    if (scrollViewRef.current && chat.length > 0) {
      // Small delay to ensure content is rendered
      setTimeout(() => {
        scrollViewRef.current?.scrollToEnd({animated: true});
      }, 100);
    }
  }, [chat.length, loading]);

  // Also scroll when AI finishes responding (loading becomes false)
  useEffect(() => {
    if (scrollViewRef.current && !loading && chat.length > 0) {
      // Delay to ensure the AI response is fully rendered
      setTimeout(() => {
        scrollViewRef.current?.scrollToEnd({animated: true});
      }, 200);
    }
  }, [loading, chat.length]);
  const sanitizeJson = (s) => {
    if (!s) return s;
    let out = s.replace(/,\s*(?=[}\]])/g, "");
    out = out.replace(/'(?=\s*[:,}\]])/g, '"');
    out = out.replace(/"\s*:\s*'([^']*)'/g, '" : "$1"');
    return out;
  };

  const parseMarkdownEmailList = (text) => {
    if (typeof text !== 'string') return [];
    const t = text.replace(/\r\n/g, '\n');
    const items = [];
    const re = /\n?\s*\d+\.\s+\*\*From:\*\*\s*([\s\S]*?)\n\s*\*\*Subject:\*\*\s*([\s\S]*?)\n\s*\*\*Snippet:\*\*\s*([\s\S]*?)(?=\n\s*\d+\.\s|$)/g;
    let m;
    let idx = 1;
    while ((m = re.exec(t)) !== null) {
      const from = m[1].trim();
      const subject = m[2].trim();
      const snippet = m[3].trim();
      items.push({idx, from, subject, snippet, threadId: `md-${idx}`});
      idx += 1;
    }
    return items;
  };

  const parseEmailJson = (text) => {
    if (typeof text !== 'string') return null;
    const noFences = text.replace(/```[a-zA-Z]*\r?\n?|```/g, '').trim();
    // Try full parse
    try {
      const parsed = JSON.parse(noFences);
      if (Array.isArray(parsed) && (parsed[0]?.threadId || parsed.find?.(e => e?.threadId))) return parsed;
    } catch {}
    // Try to extract the first balanced JSON array
    const start = noFences.indexOf('[');
    if (start !== -1) {
      let depth = 0;
      for (let i = start; i < noFences.length; i++) {
        const ch = noFences[i];
        if (ch === '[') depth++;
        else if (ch === ']') depth--;
        if (depth === 0) {
          let candidate = noFences.slice(start, i + 1);
          candidate = sanitizeJson(candidate);
          try {
            const parsed = JSON.parse(candidate);
            if (Array.isArray(parsed) && (parsed[0]?.threadId || parsed.find?.(e => e?.threadId))) return parsed;
          } catch {}
          break;
        }
      }
      // Fallback: from first '[' to last ']'
      const end = noFences.lastIndexOf(']');
      if (end > start) {
        let candidate = noFences.slice(start, end + 1);
        candidate = sanitizeJson(candidate);
        try {
          const parsed = JSON.parse(candidate);
          if (Array.isArray(parsed) && (parsed[0]?.threadId || parsed.find?.(e => e?.threadId))) return parsed;
        } catch {}
      }
    }
    // Last resort: sanitize entire string
    try {
      const parsed = JSON.parse(sanitizeJson(noFences));
      if (Array.isArray(parsed) && (parsed[0]?.threadId || parsed.find?.(e => e?.threadId))) return parsed;
    } catch {}
    return null;
  };

  if (chat.length === 0 && !loading) {
    return <WelcomeMessage />;
  }

  return (
    <ScrollView
      ref={scrollViewRef}
      style={styles.container}
      showsVerticalScrollIndicator={false}
      onContentSizeChange={() => {
        scrollViewRef.current?.scrollToEnd({animated: true});
      }}>
      {chat.map((msg, idx) => {
        const emailsFromJson = msg.role !== 'user' ? parseEmailJson(msg.text) : null;
        const emailsFromMd = !emailsFromJson && msg.role !== 'user' ? parseMarkdownEmailList(msg.text) : [];
        const emailsToDisplay = emailsFromJson || emailsFromMd;
        return (
          <View
            key={idx}
            style={[
              styles.messageContainer,
              msg.role === 'user' ? styles.messageRight : styles.messageLeft,
            ]}>
            <View
              style={[
                styles.messageBubble,
                msg.role === 'user' ? styles.bubbleUser : styles.bubbleAssistant,
              ]}>
              <View style={styles.messageContent}>
                <LinearGradient
                  colors={
                    msg.role === 'user'
                      ? [colors.accent[500], colors.accent[600]]
                      : [colors.secondary[500], colors.secondary[600]]
                  }
                  style={styles.avatar}>
                  {msg.role === 'user' ? (
                    <Svg width="14" height="14" viewBox="0 0 24 24" fill={colors.primary[50]}>
                      <Path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
                    </Svg>
                  ) : (
                    <Svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                      <Circle cx="12" cy="12" r="10" stroke={colors.primary[50]} strokeWidth="2" fill="none" strokeDasharray="31.416" strokeDashoffset="23.562"/>
                      <Circle cx="12" cy="12" r="6" stroke={colors.primary[50]} strokeWidth="1.5" fill="none" strokeDasharray="18.85" strokeDashoffset="14.137"/>
                    </Svg>
                  )}
                </LinearGradient>
                
                <View style={styles.messageTextContainer}>
                  <Text style={styles.messageAuthor}>
                    {msg.role === 'user' ? 'You' : 'Aivis'}
                  </Text>
                  {emailsToDisplay.length > 0 ? (
                    <EmailList emails={emailsToDisplay} onSelect={onEmailSelect} />
                  ) : (
                    <Text style={styles.messageText}>{msg.text}</Text>
                  )}
                </View>
              </View>
            </View>
          </View>
        );
      })}
      
      {loading && <TypingIndicator />}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 12,
  },
  messageContainer: {
    marginVertical: 8,
  },
  messageLeft: {
    alignItems: 'flex-start',
  },
  messageRight: {
    alignItems: 'flex-end',
  },
  messageBubble: {
    maxWidth: '80%',
    borderRadius: 16,
    padding: 12,
    ...commonStyles.shadowMd,
  },
  bubbleUser: {
    borderBottomRightRadius: 4,
    backgroundColor: colors.accent[500],
  },
  bubbleAssistant: {
    borderBottomLeftRadius: 4,
    backgroundColor: colors.secondary[500],
  },
  messageContent: {
    flexDirection: 'row',
    gap: 12,
    alignItems: 'flex-start',
  },
  avatar: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
    ...commonStyles.shadowMd,
  },
  avatarText: {
    color: colors.primary[50],
    fontSize: 14,
    fontWeight: '600',
  },
  messageTextContainer: {
    flex: 1,
    gap: 4,
  },
  messageAuthor: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.primary[50] + '80',
    marginBottom: 4,
  },
  messageText: {
    fontSize: 15,
    lineHeight: 20,
    color: colors.primary[50],
  },
});

