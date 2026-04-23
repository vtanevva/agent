import React, {useCallback, useEffect, useMemo, useState} from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
} from 'react-native';
import {useRoute, useNavigation, useFocusEffect} from '@react-navigation/native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {Svg, Path} from 'react-native-svg';
import {LinearGradient} from 'expo-linear-gradient';

import {theme, pickDotColor} from '../styles/theme';
import {
  fetchActionItems,
  mapActionItemToUi,
  markActionItemDone,
} from '../api/actionItems';
import {fetchUserSearch} from '../api/userSearch';
import TopSearchBar from '../components/TopSearchBar';
import BottomNav from '../components/BottomNav';

function greeting() {
  const h = new Date().getHours();
  if (h < 12) return 'Good morning';
  if (h < 18) return 'Good afternoon';
  return 'Good evening';
}

function formatWaiting(iso) {
  if (!iso) return 'Waiting';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return 'Waiting';
  const now = new Date();
  const sameDay =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate();
  const yday = new Date(now);
  yday.setDate(yday.getDate() - 1);
  const wasYesterday =
    d.getFullYear() === yday.getFullYear() &&
    d.getMonth() === yday.getMonth() &&
    d.getDate() === yday.getDate();
  if (sameDay) return 'Waiting since today';
  if (wasYesterday) return 'Waiting since yesterday';
  const diffDays = Math.max(1, Math.floor((now - d) / 86400000));
  return `Waiting since ${diffDays}d ago`;
}

function senderShortName(from) {
  if (!from) return '';
  // Parse "Name <email>" or bare email
  const m = /^([^<]+)<[^>]+>$/.exec(from);
  if (m && m[1]) return m[1].trim().replace(/(^"|"$)/g, '');
  const at = from.indexOf('@');
  if (at > 0) return from.slice(0, at);
  return from;
}

export default function HomePage() {
  const route = useRoute();
  const navigation = useNavigation();
  const {userId, sessionId} = route.params || {};

  const [items, setItems] = useState([]);
  const [hiddenIds, setHiddenIds] = useState(() => new Set());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [expandedId, setExpandedId] = useState(null);
  const [query, setQuery] = useState('');
  const [searchHits, setSearchHits] = useState(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState('');

  const loadItems = useCallback(async () => {
    if (!userId) {
      setItems([]);
      return;
    }
    setLoading(true);
    setError('');
    try {
      const raw = await fetchActionItems(userId, 100);
      const mapped = raw.map(mapActionItemToUi).filter(Boolean);
      setItems(mapped);
    } catch (e) {
      setError(e?.message || 'Failed to load action items');
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    loadItems();
  }, [loadItems]);

  useFocusEffect(
    useCallback(() => {
      loadItems();
    }, [loadItems])
  );

  const visibleItems = useMemo(() => {
    const seen = new Set();
    const out = [];
    for (const it of items) {
      if (!it || hiddenIds.has(it.id)) continue;
      if (seen.has(it.id)) continue;
      seen.add(it.id);
      out.push(it);
    }
    return out;
  }, [items, hiddenIds]);

  const queryLc = query.trim().toLowerCase();
  const attentionItems = useMemo(() => {
    if (!queryLc) return visibleItems;
    return visibleItems.filter(
      (it) =>
        (it.title || '').toLowerCase().includes(queryLc) ||
        (it.from || '').toLowerCase().includes(queryLc) ||
        (it.snippet || '').toLowerCase().includes(queryLc),
    );
  }, [visibleItems, queryLc]);

  useEffect(() => {
    const t = query.trim();
    if (t.length < 2) {
      setSearchHits(null);
      setSearchError('');
      setSearchLoading(false);
      return undefined;
    }
    setSearchLoading(true);
    const id = setTimeout(() => {
      (async () => {
        try {
          const data = await fetchUserSearch({userId, q: t, limit: 12});
          setSearchHits(data?.hits || {});
          setSearchError('');
        } catch (e) {
          setSearchError(e?.message || 'Search failed');
          setSearchHits(null);
        } finally {
          setSearchLoading(false);
        }
      })();
    }, 320);
    return () => clearTimeout(id);
  }, [query, userId]);

  const searchTotal = useMemo(() => {
    if (!searchHits) return 0;
    return Object.values(searchHits).reduce((n, arr) => n + (Array.isArray(arr) ? arr.length : 0), 0);
  }, [searchHits]);

  const displayName = useMemo(() => {
    if (!userId) return 'there';
    const core = String(userId).split('@')[0].replace(/[._-]+/g, ' ').trim();
    if (!core) return 'there';
    return core
      .split(/\s+/)
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(' ');
  }, [userId]);

  const hideLocally = (id) => {
    setHiddenIds((prev) => {
      const next = new Set(prev);
      next.add(id);
      return next;
    });
    setExpandedId(null);
  };

  const handleDone = async (item) => {
    hideLocally(item.id);
    try {
      await markActionItemDone({
        userId,
        threadId: item.threadId || item.id,
        source: item.source,
      });
    } catch (e) {
      Alert.alert('Could not mark done', String(e?.message || e));
    }
  };

  const handlePostpone = (item) => {
    // Placeholder: the backend has no "snooze" endpoint yet — hide optimistically
    // so the UI matches the Figma interaction; it'll re-appear on next refresh
    // unless the user also marks it done.
    hideLocally(item.id);
  };

  const handleGenerate = (item) => {
    const sender = senderShortName(item.from);
    const snippet = (item.snippet || '').slice(0, 500);
    const seed =
      `Draft a concise, warm, professional reply to "${item.title}"` +
      (sender ? ` from ${sender}` : '') +
      (snippet ? `\n\n--- original message ---\n${snippet}` : '');
    navigation.navigate('QuickChat', {
      userId,
      sessionId,
      seedPrompt: seed,
      seedThreadId: item.threadId || null,
    });
  };

  const openCenter = () => {
    navigation.navigate('QuickChat', {userId, sessionId});
  };

  const openMenu = () => {
    navigation.navigate('Menu', {userId, sessionId});
  };

  const openWeek = () => {
    navigation.navigate('WeeklySchedule', {userId, sessionId});
  };

  const openSearchHit = (hit) => {
    if (!hit) return;
    const k = hit.kind;
    let seed = '';
    if (k === 'message') {
      seed =
        `I searched my data and found this message:\n` +
        `Subject: ${hit.title || ''}\n` +
        (hit.subtitle ? `From: ${hit.subtitle}\n` : '') +
        (hit.snippet ? `Details: ${hit.snippet}\n` : '') +
        `\nSummarize what matters and what I should do next.`;
    } else if (k === 'task') {
      seed =
        `I found this task in my records:\n` +
        `${hit.title || ''}\n` +
        (hit.subtitle ? `${hit.subtitle}\n` : '') +
        (hit.snippet ? `${hit.snippet}\n` : '') +
        `\nHelp me plan or complete it.`;
    } else if (k === 'project') {
      seed =
        `Project context:\n` +
        `${hit.title || ''}` +
        (hit.subtitle ? ` (${hit.subtitle})` : '') +
        `\n` +
        (hit.snippet ? `${hit.snippet}\n` : '') +
        `\nAnswer my questions about this workstream.`;
    } else if (k === 'project_note') {
      seed =
        `Notes for project "${hit.title || ''}"` +
        (hit.subtitle ? ` — client: ${hit.subtitle}` : '') +
        `:\n${hit.snippet || ''}\n\nExplain how this fits the bigger picture.`;
    } else if (k === 'calendar') {
      seed =
        `Calendar entry:\n${hit.title || ''}\n${hit.subtitle || ''}\n` +
        (hit.snippet ? `${hit.snippet}\n` : '') +
        `\nHelp me prepare or follow up.`;
    } else {
      seed = JSON.stringify(hit, null, 2);
    }
    navigation.navigate('QuickChat', {
      userId,
      sessionId,
      seedPrompt: seed,
      seedThreadId: k === 'message' ? hit.thread_id || null : null,
    });
  };

  const SEARCH_SECTIONS = [
    ['messages', 'Email & messages'],
    ['tasks', 'Tasks'],
    ['projects', 'Projects'],
    ['project_notes', 'Project notes'],
    ['calendar', 'Calendar'],
  ];

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <TopSearchBar value={query} onChangeText={setQuery} />

      {query.trim().length >= 2 ? (
        <View style={styles.searchPanel}>
          {searchLoading ? (
            <View style={styles.searchLoadingRow}>
              <ActivityIndicator color={theme.colors.textPrimary} size="small" />
              <Text style={styles.searchLoadingText}>Searching your data…</Text>
            </View>
          ) : null}
          {!!searchError ? (
            <Text style={styles.searchErrorText}>{searchError}</Text>
          ) : null}
          {!searchLoading && !searchError && searchHits && searchTotal === 0 ? (
            <Text style={styles.searchEmptyText}>
              No matches in saved email, tasks, projects, or calendar. Try different words.
            </Text>
          ) : null}
          {!searchLoading && searchHits && searchTotal > 0 ? (
            <ScrollView
              style={styles.searchScroll}
              nestedScrollEnabled
              keyboardShouldPersistTaps="handled"
              showsVerticalScrollIndicator={false}>
              {SEARCH_SECTIONS.map(([key, label]) => {
                const arr = searchHits[key] || [];
                if (!arr.length) return null;
                return (
                  <View key={key} style={styles.searchSection}>
                    <Text style={styles.searchSectionTitle}>{label}</Text>
                    {arr.map((hit, idx) => (
                      <TouchableOpacity
                        key={`${key}-${hit.id ?? hit.project_id ?? idx}`}
                        style={styles.searchHitRow}
                        activeOpacity={0.85}
                        onPress={() => openSearchHit(hit)}>
                        <Text style={styles.searchHitTitle} numberOfLines={2}>
                          {hit.title}
                        </Text>
                        {hit.subtitle ? (
                          <Text style={styles.searchHitSub} numberOfLines={1}>
                            {hit.subtitle}
                          </Text>
                        ) : null}
                        {hit.snippet ? (
                          <Text style={styles.searchHitSnip} numberOfLines={2}>
                            {hit.snippet}
                          </Text>
                        ) : null}
                      </TouchableOpacity>
                    ))}
                  </View>
                );
              })}
            </ScrollView>
          ) : null}
        </View>
      ) : null}

      <View style={styles.scrollWrap}>
        <ScrollView
          style={styles.scroll}
          contentContainerStyle={styles.scrollContent}
          showsVerticalScrollIndicator={false}>
          <View style={styles.hero}>
            <Text style={styles.greeting}>
              {greeting()}, {displayName}
            </Text>
          </View>

          <View style={styles.sectionHeader}>
            <Text style={styles.sectionHeaderText}>
              Needs your attention{' '}
              <Text style={styles.sectionHeaderCount}>
                ({queryLc ? attentionItems.length : visibleItems.length})
              </Text>
            </Text>
          </View>

          {!!error && (
            <View style={styles.errorBanner}>
              <Text style={styles.errorBannerText}>{error}</Text>
            </View>
          )}

          {loading && items.length === 0 ? (
            <View style={styles.loadingWrap}>
              <ActivityIndicator color={theme.colors.textPrimary} />
            </View>
          ) : visibleItems.length === 0 ? (
            <View style={styles.emptyCard}>
              <Text style={styles.emptyTitle}>You're all caught up</Text>
              <Text style={styles.emptyHint}>
                New action items from email and chat will show up here automatically.
              </Text>
            </View>
          ) : attentionItems.length === 0 && queryLc ? (
            <View style={styles.emptyCard}>
              <Text style={styles.emptyTitle}>No action items match</Text>
              <Text style={styles.emptyHint}>
                Your search still runs across email, tasks, projects, and calendar above.
              </Text>
            </View>
          ) : (
            attentionItems.map((item) => (
              <TaskCard
                key={item.id}
                item={item}
                expanded={expandedId === item.id}
                onToggle={() =>
                  setExpandedId((cur) => (cur === item.id ? null : item.id))
                }
                onGenerate={() => handleGenerate(item)}
                onPostpone={() => handlePostpone(item)}
                onDone={() => handleDone(item)}
              />
            ))
          )}
        </ScrollView>

        {/* Bottom fade — keeps the list scrollable but makes content near
            the BottomNav melt into the background, matching the Figma. */}
        <LinearGradient
          pointerEvents="none"
          colors={[theme.colors.bg + '00', theme.colors.bg + 'FF', theme.colors.bg + 'FF']}
          locations={[0, 0.55, 1]}
          style={styles.fade}
        />
      </View>

      <BottomNav
        leftIcon="stats"
        centerIcon="plus"
        rightIcon="menu"
        onLeft={openWeek}
        onCenter={openCenter}
        onRight={openMenu}
      />
    </SafeAreaView>
  );
}

function TaskCard({item, expanded, onToggle, onGenerate, onPostpone, onDone}) {
  const dotColor = pickDotColor(item.id || item.title || '');
  const subtitle = formatWaiting(item.createdAt);

  return (
    <View style={styles.taskOuter}>
      <TouchableOpacity
        activeOpacity={0.85}
        onPress={onToggle}
        style={styles.taskCard}>
        <View style={[styles.taskDot, {backgroundColor: dotColor}]} />
        <View style={styles.taskBody}>
          <Text style={styles.taskTitle} numberOfLines={expanded ? 3 : 2}>
            {item.title}
          </Text>
          <Text style={styles.taskSubtitle} numberOfLines={1}>
            {subtitle}
          </Text>
        </View>
      </TouchableOpacity>

      <TouchableOpacity
        activeOpacity={0.8}
        onPress={onToggle}
        style={styles.chevBtn}
        hitSlop={{top: 8, bottom: 8, left: 8, right: 8}}>
        <Svg width={18} height={18} viewBox="0 0 24 24" fill="none">
          <Path
            d={expanded ? 'M6 15l6-6 6 6' : 'M6 9l6 6 6-6'}
            stroke={theme.colors.textPrimary}
            strokeWidth={1.8}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </Svg>
      </TouchableOpacity>

      {expanded && (
        <View style={styles.actionRow}>
          <ActionChip label="Generate answer" onPress={onGenerate} />
          <ActionChip label="Postpone for tomorrow" onPress={onPostpone} />
          <ActionChip label="Mark as done" onPress={onDone} />
        </View>
      )}
    </View>
  );
}

function ActionChip({label, onPress}) {
  return (
    <TouchableOpacity activeOpacity={0.85} onPress={onPress} style={styles.chip}>
      <Text style={styles.chipText}>{label}</Text>
    </TouchableOpacity>
  );
}

const CARD_RADIUS = 20;

const styles = StyleSheet.create({
  container: {flex: 1, backgroundColor: theme.colors.bg},
  searchPanel: {
    maxHeight: 220,
    marginHorizontal: 16,
    marginBottom: 4,
    paddingBottom: 6,
  },
  searchScroll: {maxHeight: 200},
  searchLoadingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingVertical: 8,
    paddingHorizontal: 4,
  },
  searchLoadingText: {
    fontSize: 12,
    color: theme.colors.textSecondary,
    fontFamily: theme.fonts.regular,
  },
  searchErrorText: {
    fontSize: 12,
    color: '#8A2C2C',
    paddingHorizontal: 4,
    marginBottom: 4,
  },
  searchEmptyText: {
    fontSize: 12,
    color: theme.colors.textSecondary,
    paddingHorizontal: 4,
    paddingVertical: 6,
  },
  searchSection: {marginBottom: 10},
  searchSectionTitle: {
    fontSize: 11,
    fontWeight: '700',
    color: theme.colors.textSecondary,
    marginBottom: 6,
    marginTop: 4,
    letterSpacing: 0.4,
  },
  searchHitRow: {
    backgroundColor: theme.colors.surface,
    borderRadius: 14,
    padding: 12,
    marginBottom: 8,
    ...theme.shadow.card,
  },
  searchHitTitle: {
    fontFamily: theme.fonts.semibold,
    fontSize: 13,
    color: theme.colors.textPrimary,
  },
  searchHitSub: {
    marginTop: 2,
    fontSize: 11,
    color: theme.colors.textSecondary,
  },
  searchHitSnip: {
    marginTop: 4,
    fontSize: 11,
    color: theme.colors.textSecondary,
    lineHeight: 15,
  },
  scrollWrap: {flex: 1},
  scroll: {flex: 1},
  scrollContent: {paddingHorizontal: 20, paddingBottom: 260},
  hero: {
    marginTop: 56,
    marginBottom: 14,
  },
  greeting: {
    fontFamily: theme.fonts.medium,
    fontSize: 26,
    letterSpacing: -0.3,
    color: theme.colors.textPrimary,
  },
  sectionHeader: {marginBottom: 18, marginTop: 0},
  sectionHeaderText: {
    fontFamily: theme.fonts.regular,
    fontSize: 13,
    color: theme.colors.textPrimary,
  },
  sectionHeaderCount: {
    color: theme.colors.textPrimary,
    fontFamily: theme.fonts.regular,
  },
  fade: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    height: 260,
  },
  errorBanner: {
    backgroundColor: '#F6E0E0',
    borderRadius: 12,
    padding: 10,
    marginBottom: 10,
  },
  errorBannerText: {
    color: '#8A2C2C',
    fontSize: 12,
    fontWeight: '600',
    textAlign: 'center',
  },
  loadingWrap: {paddingVertical: 40, alignItems: 'center'},
  emptyCard: {
    backgroundColor: theme.colors.surface,
    borderRadius: CARD_RADIUS,
    padding: 18,
    ...theme.shadow.card,
  },
  emptyTitle: {
    ...theme.type.cardTitle,
    color: theme.colors.textPrimary,
  },
  emptyHint: {
    marginTop: 4,
    ...theme.type.cardSubtitle,
    color: theme.colors.textSecondary,
  },

  taskOuter: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 16,
    flexWrap: 'wrap',
  },
  taskCard: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: theme.colors.surface,
    borderRadius: CARD_RADIUS,
    paddingVertical: 16,
    paddingHorizontal: 16,
    marginRight: 14,
  },
  taskDot: {
    width: 7,
    height: 7,
    borderRadius: 4,
    marginTop: 7,
    marginRight: 10,
  },
  taskBody: {flex: 1},
  taskTitle: {
    fontFamily: theme.fonts.semibold,
    fontSize: 14,
    color: theme.colors.textPrimary,
  },
  taskSubtitle: {
    marginTop: 3,
    fontFamily: theme.fonts.regular,
    fontSize: 11.5,
    color: theme.colors.textSecondary,
  },
  chevBtn: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: theme.colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  actionRow: {
    width: '100%',
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginTop: 10,
    marginBottom: 6,
    paddingLeft: 4,
  },
  chip: {
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radius.pill,
    paddingHorizontal: 14,
    paddingVertical: 8,
    ...theme.shadow.card,
  },
  chipText: {
    ...theme.type.chip,
    color: theme.colors.textPrimary,
  },
});
