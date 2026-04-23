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

import {theme, pickDotColor} from '../styles/theme';
import {
  fetchActionItems,
  mapActionItemToUi,
  markActionItemDone,
} from '../api/actionItems';
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

  const visibleItems = useMemo(
    () => items.filter((it) => !hiddenIds.has(it.id)),
    [items, hiddenIds]
  );

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
    navigation.navigate('Chat', {
      userId,
      sessionId,
      seedPrompt: seed,
      seedThreadId: item.threadId || null,
    });
  };

  const openCenter = () => {
    navigation.navigate('Chat', {userId, sessionId});
  };

  const openMenu = () => {
    navigation.navigate('Menu', {userId, sessionId});
  };

  const openWeek = () => {
    navigation.navigate('WeeklySchedule', {userId, sessionId});
  };

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <TopSearchBar value={query} onChangeText={setQuery} />

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
            <Text style={styles.sectionHeaderCount}>({visibleItems.length})</Text>
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
        ) : (
          visibleItems.map((item) => (
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

const CARD_RADIUS = 22;

const styles = StyleSheet.create({
  container: {flex: 1, backgroundColor: theme.colors.bg},
  scroll: {flex: 1},
  scrollContent: {paddingHorizontal: 20, paddingBottom: 140},
  hero: {
    marginTop: 24,
    marginBottom: 20,
  },
  greeting: {
    ...theme.type.display,
    color: theme.colors.textPrimary,
  },
  sectionHeader: {marginBottom: 10, marginTop: 4},
  sectionHeaderText: {
    ...theme.type.sectionHeader,
    color: theme.colors.textPrimary,
  },
  sectionHeaderCount: {
    color: theme.colors.textSecondary,
    fontWeight: '500',
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
    alignItems: 'flex-start',
    marginBottom: 10,
    flexWrap: 'wrap',
  },
  taskCard: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: theme.colors.surface,
    borderRadius: CARD_RADIUS,
    paddingVertical: 14,
    paddingHorizontal: 14,
    marginRight: 10,
    ...theme.shadow.card,
  },
  taskDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginTop: 6,
    marginRight: 10,
  },
  taskBody: {flex: 1},
  taskTitle: {
    ...theme.type.cardTitle,
    color: theme.colors.textPrimary,
  },
  taskSubtitle: {
    marginTop: 2,
    ...theme.type.cardSubtitle,
    color: theme.colors.textSecondary,
  },
  chevBtn: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: theme.colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
    ...theme.shadow.card,
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
