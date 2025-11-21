import React, {useEffect, useState, useCallback} from 'react';
import {View, Text, StyleSheet, TextInput, TouchableOpacity, ScrollView, Platform, KeyboardAvoidingView} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {LinearGradient} from 'expo-linear-gradient';
import {colors} from '../styles/colors';
import {commonStyles} from '../styles/commonStyles';
import EmailList from '../components/EmailList';
import EmailReplyModal from '../components/EmailReplyModal';
import {API_BASE_URL} from '../config/api';
import {useRoute} from '@react-navigation/native';

export default function GmailAgentPage() {
  const route = useRoute();
  const {userId} = route.params || {};
  const [label, setLabel] = useState('INBOX');
  const [query, setQuery] = useState('');
  const [threads, setThreads] = useState([]);
  const [loading, setLoading] = useState(false);
  const [hiddenThreads, setHiddenThreads] = useState([]);
  const [replyOpen, setReplyOpen] = useState(false);
  const [replyThreadId, setReplyThreadId] = useState(null);
  const [replyTo, setReplyTo] = useState(null);

  const fetchList = useCallback(async () => {
    if (!userId) return;
    setLoading(true);
    try {
      const r = await fetch(`${API_BASE_URL}/api/gmail/list`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId, label, max_results: 20}),
      });
      const data = await r.json();
      if (data?.success) {
        setThreads(data.threads || []);
      } else {
        setThreads([]);
      }
    } catch {
      setThreads([]);
    } finally {
      setLoading(false);
    }
  }, [userId, label]);

  const fetchSearch = useCallback(async () => {
    if (!userId || !query.trim()) return;
    setLoading(true);
    try {
      const r = await fetch(`${API_BASE_URL}/api/gmail/search`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId, query, max_results: 20}),
      });
      const data = await r.json();
      if (data?.success) {
        setThreads(data.threads || []);
      } else {
        setThreads([]);
      }
    } catch {
      setThreads([]);
    } finally {
      setLoading(false);
    }
  }, [userId, query]);

  useEffect(() => {
    fetchList();
  }, [fetchList]);

  const handleSelect = (threadId, from) => {
    const m = /<([^>]+)>/.exec(from);
    const to = m ? m[1] : from;
    setReplyThreadId(threadId);
    setReplyTo(to);
    setReplyOpen(true);
  };

  const archiveOptimistic = async (threadId) => {
    setHiddenThreads((prev) => Array.from(new Set([...prev, threadId])));
    try {
      await fetch(`${API_BASE_URL}/api/gmail/archive`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId, thread_id: threadId}),
      });
    } catch {
      setHiddenThreads((prev) => prev.filter((t) => t !== threadId));
    }
  };

  const handledOptimistic = async (threadId) => {
    setHiddenThreads((prev) => Array.from(new Set([...prev, threadId])));
    try {
      await fetch(`${API_BASE_URL}/api/gmail/mark-handled`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId, thread_id: threadId}),
      });
    } catch {
      setHiddenThreads((prev) => prev.filter((t) => t !== threadId));
    }
  };

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      <KeyboardAvoidingView
        style={{flex: 1}}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      >
      <View style={styles.content}>
        <View style={styles.header}>
          <Text style={styles.title}>Gmail Agent</Text>
          <Text style={styles.subtitle}>Search, list, and reply fast</Text>
        </View>

        <View style={styles.controls}>
          <View style={styles.row}>
            <TextInput
              value={query}
              onChangeText={setQuery}
              placeholder="Search (e.g., from:boss meeting)"
              placeholderTextColor={colors.primary[900] + '60'}
              style={styles.input}
            />
            <TouchableOpacity onPress={fetchSearch} style={styles.button}>
              <LinearGradient colors={[colors.accent[500], colors.accent[600]]} style={styles.buttonInner}>
                <Text style={styles.buttonText}>{loading ? 'Searching…' : 'Search'}</Text>
              </LinearGradient>
            </TouchableOpacity>
          </View>
          <View style={styles.row}>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{gap: 8}}>
              {['INBOX', 'STARRED', 'SENT', 'IMPORTANT', 'TRASH', 'SPAM'].map((lbl) => (
                <TouchableOpacity
                  key={lbl}
                  onPress={() => { setLabel(lbl); }}
                  style={[styles.chip, label === lbl && styles.chipActive]}
                >
                  <Text style={[styles.chipText, label === lbl && styles.chipTextActive]}>{lbl}</Text>
                </TouchableOpacity>
              ))}
              <TouchableOpacity onPress={fetchList} style={styles.reloadBtn}>
                <Text style={styles.reloadText}>{loading ? 'Loading…' : 'Reload'}</Text>
              </TouchableOpacity>
            </ScrollView>
          </View>
        </View>

        <View style={styles.listArea}>
          <EmailList
            emails={threads}
            onSelect={handleSelect}
            onArchive={archiveOptimistic}
            onDone={handledOptimistic}
            hiddenThreadIds={hiddenThreads}
          />
          {threads.length === 0 && (
            <Text style={styles.emptyHint}>
              {loading ? 'Loading…' : 'No results. Try another label or search.'}
            </Text>
          )}
        </View>
      </View>
      <EmailReplyModal
        visible={replyOpen}
        onClose={(sent) => {
          setReplyOpen(false);
          setReplyThreadId(null);
          setReplyTo(null);
        }}
        userId={userId}
        threadId={replyThreadId}
        to={replyTo}
      />
      </KeyboardAvoidingView>
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
    padding: 12,
  },
  header: {
    marginBottom: 8,
  },
  title: {
    fontSize: 20,
    fontWeight: '700',
    color: colors.primary[900],
  },
  subtitle: {
    fontSize: 12,
    color: colors.primary[900] + '80',
    marginTop: 2,
  },
  controls: {
    ...commonStyles.glassEffectStrong,
    borderRadius: 12,
    padding: 10,
    marginBottom: 10,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 8,
  },
  input: {
    flex: 1,
    backgroundColor: colors.primary[200] + '30',
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
    color: colors.primary[900],
    borderWidth: 1,
    borderColor: colors.dark[500] + '10',
  },
  button: {
    borderRadius: 10,
    overflow: 'hidden',
  },
  buttonInner: {
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  buttonText: {
    color: '#fff',
    fontWeight: '600',
  },
  chip: {
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 999,
    backgroundColor: colors.primary[200] + '30',
    borderWidth: 1,
    borderColor: colors.dark[500] + '10',
  },
  chipActive: {
    backgroundColor: colors.secondary[500] + '30',
    borderColor: colors.secondary[600] + '50',
  },
  chipText: {
    fontSize: 12,
    color: colors.primary[900] + '90',
  },
  chipTextActive: {
    color: colors.secondary[700],
    fontWeight: '600',
  },
  reloadBtn: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
    backgroundColor: colors.dark[500] + '10',
  },
  reloadText: {
    fontSize: 12,
    color: colors.primary[900],
  },
  listArea: {
    flex: 1,
    marginTop: 4,
  },
  emptyHint: {
    textAlign: 'center',
    color: colors.primary[900] + '70',
    marginTop: 10,
    fontSize: 12,
  },
});


