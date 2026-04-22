import React, {useEffect, useState, useCallback, useRef, useMemo} from 'react';
import {View, Text, StyleSheet, TouchableOpacity, ScrollView, Platform, KeyboardAvoidingView, ActivityIndicator, Modal, AppState} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {LinearGradient} from 'expo-linear-gradient';
import {colors} from '../styles/colors';
import {commonStyles} from '../styles/commonStyles';
import EmailList from '../components/EmailList';
import EmailReplyModal from '../components/EmailReplyModal';
import {CORE_BACKEND_URL} from '../config/api';
import {extractEmailAddress} from '../utils/emailParse';
import {useRoute, useNavigation} from '@react-navigation/native';
import {Svg, Path} from 'react-native-svg';

export default function GmailAgentPage() {
  const route = useRoute();
  const navigation = useNavigation();
  const {userId} = route.params || {};
  const [emails, setEmails] = useState([]);
  const [loading, setLoading] = useState(false);
  const [hiddenThreads, setHiddenThreads] = useState([]);
  const [replyOpen, setReplyOpen] = useState(false);
  const [replyThreadId, setReplyThreadId] = useState(null);
  const [replyTo, setReplyTo] = useState(null);
  const [emailLimit, setEmailLimit] = useState(100); // Default to 100
  const [limitModalOpen, setLimitModalOpen] = useState(false);
  const initialLoadRef = useRef(false);
  const fetchingRef = useRef(false);
  const lastDataHashRef = useRef(null);
  const pollTimerRef = useRef(null);
  const appStateRef = useRef(AppState.currentState);

  // Home screen requirement: show only emails/messages that have_action=true
  const SHOW_ONLY_ACTIONABLE = true;

  // Poll interval: keeps UI updated as backend workers ingest/classify new emails (e.g. from Pub/Sub)
  const POLL_MS = 15000;

  const hasAction = (email) => {
    if (!email || typeof email !== 'object') return false;
    const classificationType =
      (email.classification_type || email.classificationType || email.type || '').toString().toUpperCase();
    if (classificationType === 'ACTION') return true;

    const v =
      email.has_action ??
      email.hasAction ??
      email?.classification?.has_action ??
      email?.classification?.hasAction;
    return v === true || v === 1 || v === '1' || v === 'true';
  };

  const fetchActionableInbox = useCallback(async (showLoading = true) => {
    if (!userId || fetchingRef.current) return;
    
    fetchingRef.current = true;
    if (showLoading) setLoading(true);
    
    try {
      const params = new URLSearchParams({
        user_id: userId,
        limit: emailLimit.toString(),
      });

      const r = await fetch(`${CORE_BACKEND_URL}/api/action-items?${params}`, {
        method: 'GET',
        headers: {'Content-Type': 'application/json'},
      });
      const data = await r.json();
      const items = Array.isArray(data?.items) ? data.items : [];

      const actionable = SHOW_ONLY_ACTIONABLE ? items.filter(hasAction) : items;

      // Hash for cheap change detection
      const ids = actionable.map((e) => e.source_id || e.threadId || '').join('|');
      if (lastDataHashRef.current !== ids) {
        lastDataHashRef.current = ids;
        setEmails(actionable);
      }
    } catch (e) {
      console.error('Error fetching actionable inbox:', e);
    } finally {
      if (showLoading) setLoading(false);
      fetchingRef.current = false;
    }
  }, [userId, emailLimit]); // Include emailLimit in dependencies

  // Initial load only once
  useEffect(() => {
    if (userId && !initialLoadRef.current) {
      initialLoadRef.current = true;
      
      // Load cached data immediately
      fetchActionableInbox(true);
    }
  }, [userId, fetchActionableInbox]);

  // Auto-refresh: poll triaged inbox so new pushed emails show up without manual refresh.
  useEffect(() => {
    if (!userId) return;

    // Start polling
    if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    pollTimerRef.current = setInterval(() => {
      fetchActionableInbox(false);
    }, POLL_MS);

    // Refresh when app returns to foreground
    const sub = AppState.addEventListener('change', (nextAppState) => {
      const prev = appStateRef.current;
      appStateRef.current = nextAppState;
      if (prev && prev.match(/inactive|background/) && nextAppState === 'active') {
        fetchActionableInbox(false);
      }
    });

    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
      sub?.remove?.();
    };
  }, [userId, fetchActionableInbox]);

  const handleSelect = (threadId, from) => {
    const picked = (emails || []).find((e) => e.threadId === threadId);
    if (!picked || picked.source !== 'gmail') {
      return;
    }
    const addr = extractEmailAddress(from);
    setReplyThreadId(threadId);
    setReplyTo(addr || (from && String(from).trim()) || '');
    setReplyOpen(true);
  };

  const archiveOptimistic = async (threadId) => {
    setHiddenThreads((prev) => Array.from(new Set([...prev, threadId])));
    try {
      await fetch(`${CORE_BACKEND_URL}/api/action-items/archive`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId, thread_id: threadId}),
      });
      setEmails((prev) => (prev || []).filter((e) => e.threadId !== threadId));
    } catch {
      setHiddenThreads((prev) => prev.filter((t) => t !== threadId));
    }
  };

  const handledOptimistic = async (threadId) => {
    setHiddenThreads((prev) => Array.from(new Set([...prev, threadId])));
    try {
      await fetch(`${CORE_BACKEND_URL}/api/action-items/done`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId, thread_id: threadId}),
      });
      setEmails((prev) => (prev || []).filter((e) => e.threadId !== threadId));
    } catch {
      setHiddenThreads((prev) => prev.filter((t) => t !== threadId));
    }
  };

  const visibleEmails = useMemo(() => {
    const hidden = new Set(hiddenThreads || []);
    return (emails || []).filter((e) => !hidden.has(e.threadId));
  }, [emails, hiddenThreads]);

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      <KeyboardAvoidingView
        style={{flex: 1}}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      >
        <View style={styles.content}>
          <View style={styles.header}>
            <TouchableOpacity
              onPress={() => navigation.goBack()}
              style={styles.backButton}>
              <Svg width="24" height="24" viewBox="0 0 24 24" fill={colors.primary[900]}>
                <Path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z"/>
              </Svg>
            </TouchableOpacity>
            <View style={styles.headerTextContainer}>
              <Text style={styles.title}>Action Inbox</Text>
              <Text style={styles.subtitle}>Only messages that need action</Text>
            </View>
            <View style={{width: 40}} />
          </View>

          {/* Controls */}
          <View style={styles.categoryFilter}>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{gap: 8, paddingRight: 8}}>
              <TouchableOpacity onPress={() => setLimitModalOpen(true)} style={styles.limitBtn}>
                <Text style={styles.limitBtnText}>Limit: {emailLimit}</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={() => fetchActionableInbox(true)} style={styles.reloadBtn}>
                <Svg width="16" height="16" viewBox="0 0 24 24" fill={colors.primary[900]}>
                  <Path d="M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/>
                </Svg>
                <Text style={styles.reloadText}>{loading ? '...' : 'Refresh'}</Text>
              </TouchableOpacity>
            </ScrollView>
          </View>

          {/* Email Limit Modal */}
          <Modal
            visible={limitModalOpen}
            transparent={true}
            animationType="fade"
            onRequestClose={() => setLimitModalOpen(false)}>
            <TouchableOpacity
              style={styles.modalOverlay}
              activeOpacity={1}
              onPress={() => setLimitModalOpen(false)}>
              <TouchableOpacity
                style={styles.modalContent}
                activeOpacity={1}
                onPress={(e) => e.stopPropagation()}>
                <Text style={styles.modalTitle}>Select Email Limit</Text>
                <Text style={styles.modalSubtitle}>Show last N emails from your inbox</Text>
                {[100, 200, 500, 1000].map((limit) => (
                  <TouchableOpacity
                    key={limit}
                    onPress={() => {
                      setEmailLimit(limit);
                      setLimitModalOpen(false);
                      // Refetch with new limit
                      setTimeout(() => fetchActionableInbox(true), 100);
                    }}
                    style={[
                      styles.limitOption,
                      emailLimit === limit && styles.limitOptionActive,
                    ]}>
                    <Text style={[
                      styles.limitOptionText,
                      emailLimit === limit && styles.limitOptionTextActive,
                    ]}>
                      {limit} emails
                    </Text>
                    {emailLimit === limit && (
                      <Text style={styles.limitOptionCheck}>✓</Text>
                    )}
                  </TouchableOpacity>
                ))}
                <TouchableOpacity
                  onPress={() => setLimitModalOpen(false)}
                  style={styles.modalCloseBtn}>
                  <Text style={styles.modalCloseText}>Cancel</Text>
                </TouchableOpacity>
              </TouchableOpacity>
            </TouchableOpacity>
          </Modal>

          {/* Email List */}
          <View style={styles.listArea}>
            {loading && (!emails || emails.length === 0) ? (
              <View style={styles.loadingContainer}>
                <ActivityIndicator size="large" color={colors.secondary[500]} />
                <Text style={styles.loadingText}>Loading actionable emails...</Text>
              </View>
            ) : (
              <View style={styles.categorySection}>
                <View style={styles.categoryHeader}>
                  <Text style={[styles.categoryTitle, {color: colors.secondary[700]}]}>✅ Action Items</Text>
                  <Text style={styles.categoryCount}>{visibleEmails.length} emails</Text>
                </View>
                <EmailList
                  emails={visibleEmails}
                  onSelect={handleSelect}
                  onArchive={archiveOptimistic}
                  onDone={handledOptimistic}
                  hiddenThreadIds={hiddenThreads}
                />
                {(!visibleEmails || visibleEmails.length === 0) && (
                  <View style={styles.emptyContainer}>
                    <Text style={styles.emptyText}>No actionable emails found</Text>
                    <Text style={styles.emptySubtext}>You are all caught up.</Text>
                  </View>
                )}
              </View>
            )}
          </View>
        </View>
        <EmailReplyModal
          visible={replyOpen}
          onClose={(sent) => {
            setReplyOpen(false);
            setReplyThreadId(null);
            setReplyTo(null);
            if (sent) {
              setTimeout(() => fetchActionableInbox(false), 500);
            }
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
    marginBottom: 12,
  },
  title: {
    fontSize: 24,
    fontWeight: '700',
    color: colors.primary[900],
  },
  subtitle: {
    fontSize: 14,
    color: colors.primary[900] + '80',
    marginTop: 2,
  },
  categoryFilter: {
    ...commonStyles.glassEffectStrong,
    borderRadius: 12,
    padding: 10,
    marginBottom: 12,
  },
  categoryChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 12,
    backgroundColor: colors.primary[200] + '30',
    borderWidth: 1,
    borderColor: colors.dark[500] + '10',
    position: 'relative',
    overflow: 'hidden',
  },
  categoryChipActive: {
    backgroundColor: colors.secondary[500] + '30',
    borderColor: colors.secondary[600] + '50',
  },
  categoryGradientBorder: {
    position: 'absolute',
    left: 0,
    top: 0,
    bottom: 0,
    width: 3,
  },
  categorySolidBorder: {
    position: 'absolute',
    left: 0,
    top: 0,
    bottom: 0,
    width: 3,
  },
  categoryIcon: {
    fontSize: 16,
  },
  categoryChipText: {
    fontSize: 13,
    color: colors.primary[900] + '90',
    fontWeight: '500',
  },
  categoryChipTextActive: {
    color: colors.secondary[700],
    fontWeight: '700',
  },
  reloadBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 12,
    backgroundColor: colors.dark[500] + '10',
  },
  reloadText: {
    fontSize: 12,
    color: colors.primary[900],
    fontWeight: '500',
  },
  limitBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 12,
    backgroundColor: colors.primary[300] + '40',
    borderWidth: 1,
    borderColor: colors.primary[600] + '30',
  },
  limitBtnText: {
    fontSize: 12,
    color: colors.primary[900],
    fontWeight: '600',
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  modalContent: {
    backgroundColor: colors.primary[50],
    borderRadius: 16,
    padding: 24,
    width: '100%',
    maxWidth: 400,
    ...commonStyles.glassEffectStrong,
  },
  modalTitle: {
    fontSize: 20,
    fontWeight: '700',
    color: colors.primary[900],
    marginBottom: 4,
  },
  modalSubtitle: {
    fontSize: 14,
    color: colors.primary[900] + '70',
    marginBottom: 20,
  },
  limitOption: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 16,
    borderRadius: 12,
    backgroundColor: colors.primary[200] + '30',
    marginBottom: 12,
    borderWidth: 2,
    borderColor: 'transparent',
  },
  limitOptionActive: {
    backgroundColor: colors.secondary[500] + '30',
    borderColor: colors.secondary[600] + '50',
  },
  limitOptionText: {
    fontSize: 16,
    color: colors.primary[900],
    fontWeight: '500',
  },
  limitOptionTextActive: {
    color: colors.secondary[700],
    fontWeight: '700',
  },
  limitOptionCheck: {
    fontSize: 18,
    color: colors.secondary[700],
    fontWeight: '700',
  },
  modalCloseBtn: {
    marginTop: 8,
    padding: 12,
    alignItems: 'center',
  },
  modalCloseText: {
    fontSize: 14,
    color: colors.primary[900] + '80',
    fontWeight: '500',
  },
  listArea: {
    flex: 1,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: 12,
  },
  loadingText: {
    color: colors.primary[900] + '80',
    fontSize: 14,
  },
  categorySection: {
    marginBottom: 20,
  },
  categoryHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
    paddingHorizontal: 4,
  },
  categoryTitle: {
    fontSize: 18,
    fontWeight: '700',
  },
  categoryCount: {
    fontSize: 12,
    color: colors.primary[900] + '70',
    fontWeight: '500',
  },
  emptyContainer: {
    padding: 40,
    alignItems: 'center',
  },
  emptyText: {
    fontSize: 16,
    color: colors.primary[900] + '70',
    marginBottom: 4,
  },
  emptySubtext: {
    fontSize: 12,
    color: colors.primary[900] + '50',
  },
});
