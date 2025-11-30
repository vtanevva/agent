import React, {useEffect, useState, useCallback, useRef, useMemo} from 'react';
import {View, Text, StyleSheet, TouchableOpacity, ScrollView, Platform, KeyboardAvoidingView, ActivityIndicator, Modal} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {LinearGradient} from 'expo-linear-gradient';
import {colors} from '../styles/colors';
import {commonStyles} from '../styles/commonStyles';
import EmailList from '../components/EmailList';
import EmailReplyModal from '../components/EmailReplyModal';
import {API_BASE_URL} from '../config/api';
import {useRoute, useNavigation} from '@react-navigation/native';
import {Svg, Path} from 'react-native-svg';

const CATEGORIES = [
  {key: 'urgent', label: 'Urgent', color: colors.dark[600], icon: '⚡'},
  {key: 'waiting_for_reply', label: 'Waiting', color: colors.accent[600], icon: '⏳'},
  {key: 'action_items', label: 'Action Items', color: colors.secondary[600], icon: '✓'},
  {key: 'clients', label: 'Clients', color: colors.primary[700], icon: '👤'},
  {key: 'invoices', label: 'Invoices', color: colors.accent[500], icon: '💰'},
  {key: 'newsletters', label: 'Newsletters', color: colors.primary[600], icon: '📰'},
  {key: 'normal', label: 'Other', color: colors.primary[500], icon: '📧'},
];

export default function GmailAgentPage() {
  const route = useRoute();
  const navigation = useNavigation();
  const {userId} = route.params || {};
  const [selectedCategory, setSelectedCategory] = useState(null); // null = show all
  const [triagedData, setTriagedData] = useState(null);
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

  const fetchTriagedInbox = useCallback(async (category = null, showLoading = true) => {
    if (!userId || fetchingRef.current) return;
    
    fetchingRef.current = true;
    if (showLoading) setLoading(true);
    
    try {
      // Always fetch all categories, don't filter on backend
      const r = await fetch(`${API_BASE_URL}/api/gmail/triaged-inbox`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          user_id: userId,
          max_results: emailLimit, // Use selected limit
          category: null, // Always fetch all, filter client-side
        }),
      });
      const data = await r.json();
      if (data?.success) {
        // Create a hash of the data structure to detect actual changes
        const categoryCounts = Object.keys(data.categories || {}).map(
          key => `${key}:${(data.categories[key] || []).length}`
        ).sort().join('|');
        const dataHash = `${data.total || 0}|${categoryCounts}`;
        
        // Only update if hash changed
        if (lastDataHashRef.current !== dataHash) {
          lastDataHashRef.current = dataHash;
          setTriagedData(data);
        }
        // If hash is the same, data hasn't changed, don't update state
      } else {
        setTriagedData(null);
      }
    } catch (e) {
      console.error('Error fetching triaged inbox:', e);
      // Don't clear data on error, keep what we have
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
      fetchTriagedInbox(null, true);
      
      // Trigger background classification for new emails (don't wait for response)
      fetch(`${API_BASE_URL}/api/gmail/classify-background`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          user_id: userId,
          max_emails: 20,
        }),
      }).catch(e => console.error('Background classification trigger failed:', e));
    }
  }, [userId, fetchTriagedInbox]);

  // Don't refetch when category changes - just use existing data
  // Category filtering is done client-side in getCategoryEmails()

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
      // Update local state to remove archived email instead of full refresh
      setTriagedData((prev) => {
        if (!prev) return prev;
        const updated = {...prev};
        for (const cat in updated.categories) {
          updated.categories[cat] = updated.categories[cat].filter(
            (email) => email.threadId !== threadId
          );
        }
        updated.total = Object.values(updated.categories).reduce(
          (sum, emails) => sum + emails.length, 0
        );
        return updated;
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
      // Update local state to remove handled email instead of full refresh
      setTriagedData((prev) => {
        if (!prev) return prev;
        const updated = {...prev};
        for (const cat in updated.categories) {
          updated.categories[cat] = updated.categories[cat].filter(
            (email) => email.threadId !== threadId
          );
        }
        updated.total = Object.values(updated.categories).reduce(
          (sum, emails) => sum + emails.length, 0
        );
        return updated;
      });
    } catch {
      setHiddenThreads((prev) => prev.filter((t) => t !== threadId));
    }
  };

  // Memoize category emails to prevent unnecessary re-renders
  const categoryEmails = useMemo(() => {
    if (!triagedData?.categories) return [];
    
    if (selectedCategory) {
      return triagedData.categories[selectedCategory] || [];
    }
    
    // Show all, sorted by priority
    const priorityOrder = ['urgent', 'waiting_for_reply', 'action_items', 'clients', 'invoices', 'newsletters', 'normal'];
    const allEmails = [];
    for (const cat of priorityOrder) {
      const emails = triagedData.categories[cat] || [];
      allEmails.push(...emails);
    }
    return allEmails;
  }, [triagedData, selectedCategory]);

  const getCategoryCount = useCallback((categoryKey) => {
    return triagedData?.categories?.[categoryKey]?.length || 0;
  }, [triagedData]);

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
              <Text style={styles.title}>Smart Inbox</Text>
              <Text style={styles.subtitle}>AI-powered email triage</Text>
            </View>
            <View style={{width: 40}} />
          </View>

          {/* Category Filter */}
          <View style={styles.categoryFilter}>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{gap: 8, paddingRight: 8}}>
              <TouchableOpacity
                onPress={() => setSelectedCategory(null)}
                style={[styles.categoryChip, selectedCategory === null && styles.categoryChipActive]}>
                <Text style={[styles.categoryChipText, selectedCategory === null && styles.categoryChipTextActive]}>
                  All ({triagedData?.total || 0})
                </Text>
              </TouchableOpacity>
              {CATEGORIES.map((cat) => {
                const count = getCategoryCount(cat.key);
                if (count === 0 && selectedCategory !== cat.key) return null;
                return (
                  <TouchableOpacity
                    key={cat.key}
                    onPress={() => setSelectedCategory(cat.key)}
                    style={[
                      styles.categoryChip,
                      selectedCategory === cat.key && styles.categoryChipActive,
                      {borderLeftColor: cat.color, borderLeftWidth: 3},
                    ]}>
                    <Text style={styles.categoryIcon}>{cat.icon}</Text>
                    <Text style={[styles.categoryChipText, selectedCategory === cat.key && styles.categoryChipTextActive]}>
                      {cat.label} ({count})
                    </Text>
                  </TouchableOpacity>
                );
              })}
              <TouchableOpacity onPress={() => setLimitModalOpen(true)} style={styles.limitBtn}>
                <Text style={styles.limitBtnText}>Limit: {emailLimit}</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={() => fetchTriagedInbox(null, true)} style={styles.reloadBtn}>
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
                      setTimeout(() => fetchTriagedInbox(null, true), 100);
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
            {loading && !triagedData ? (
              <View style={styles.loadingContainer}>
                <ActivityIndicator size="large" color={colors.secondary[500]} />
                <Text style={styles.loadingText}>Classifying emails...</Text>
              </View>
            ) : !triagedData ? (
              <View style={styles.emptyContainer}>
                <Text style={styles.emptyText}>No emails loaded</Text>
              </View>
            ) : selectedCategory ? (
              // Show single category
              <View style={styles.categorySection}>
                <View style={styles.categoryHeader}>
                  <Text style={[styles.categoryTitle, {color: CATEGORIES.find(c => c.key === selectedCategory)?.color || colors.primary[900]}]}>
                    {CATEGORIES.find(c => c.key === selectedCategory)?.icon} {CATEGORIES.find(c => c.key === selectedCategory)?.label}
                  </Text>
                  <Text style={styles.categoryCount}>
                    {getCategoryCount(selectedCategory)} emails
                  </Text>
                </View>
                <EmailList
                  emails={categoryEmails}
                  onSelect={handleSelect}
                  onArchive={archiveOptimistic}
                  onDone={handledOptimistic}
                  hiddenThreadIds={hiddenThreads}
                />
              </View>
            ) : (
              // Show all categories
              <ScrollView showsVerticalScrollIndicator={false}>
                {CATEGORIES.map((cat) => {
                  const emails = triagedData?.categories?.[cat.key] || [];
                  if (emails.length === 0) return null;
                  
                  return (
                    <View key={cat.key} style={styles.categorySection}>
                      <View style={styles.categoryHeader}>
                        <Text style={[styles.categoryTitle, {color: cat.color}]}>
                          {cat.icon} {cat.label}
                        </Text>
                        <Text style={styles.categoryCount}>{emails.length} emails</Text>
                      </View>
                      <EmailList
                        emails={emails}
                        onSelect={handleSelect}
                        onArchive={archiveOptimistic}
                        onDone={handledOptimistic}
                        hiddenThreadIds={hiddenThreads}
                      />
                    </View>
                  );
                })}
                {(!triagedData || triagedData.total === 0) && (
                  <View style={styles.emptyContainer}>
                    <Text style={styles.emptyText}>No emails found</Text>
                    <Text style={styles.emptySubtext}>Try refreshing or check your inbox</Text>
                  </View>
                )}
              </ScrollView>
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
              setTimeout(() => fetchTriagedInbox(selectedCategory, false), 500);
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
  },
  categoryChipActive: {
    backgroundColor: colors.secondary[500] + '30',
    borderColor: colors.secondary[600] + '50',
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
