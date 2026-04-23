import React, {useCallback, useEffect, useMemo, useState} from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Platform,
  Linking,
  Alert,
  Dimensions,
} from 'react-native';
import {useRoute, useNavigation} from '@react-navigation/native';
import {SafeAreaView} from 'react-native-safe-area-context';

import {theme, pickEventColor} from '../styles/theme';
import {API_BASE_URL} from '../config/api';
import {buildScheduleItems, fetchScheduleSources, toDateSafe} from '../api/scheduleData';
import TopSearchBar from '../components/TopSearchBar';
import BottomNav from '../components/BottomNav';

const TIMELINE_START_HOUR = 6;
const HOUR_HEIGHT = 44;
const HOURS_SHOWN = 18;
const TIME_GUTTER_W = 52;
const DAY_MIN_W = 116;

function startOfWeekMonday(d = new Date()) {
  const date = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const day = date.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  date.setDate(date.getDate() + diff);
  date.setHours(0, 0, 0, 0);
  return date;
}

function addDays(d, n) {
  const x = new Date(d);
  x.setDate(x.getDate() + n);
  return x;
}

function formatWeekRangeLabel(weekStart) {
  const end = addDays(weekStart, 6);
  const a = weekStart.toLocaleDateString(undefined, {month: 'short', day: 'numeric'});
  const b = end.toLocaleDateString(undefined, {month: 'short', day: 'numeric', year: 'numeric'});
  return `${a} – ${b}`;
}

function formatHourRowLabel(hour24) {
  const h = String(hour24).padStart(2, '0');
  return `${h}:00`;
}

function timelineStartForDay(dayMidnight) {
  const t = new Date(dayMidnight);
  t.setHours(TIMELINE_START_HOUR, 0, 0, 0);
  return t;
}

function timelineEndForDay(dayMidnight) {
  const t = new Date(dayMidnight);
  t.setDate(t.getDate() + 1);
  t.setHours(0, 0, 0, 0);
  return t;
}

function clipItemToDay(item, dayMidnight) {
  const dayStart = new Date(dayMidnight);
  dayStart.setHours(0, 0, 0, 0);
  const dayEnd = new Date(dayStart);
  dayEnd.setDate(dayEnd.getDate() + 1);

  const tlStart = timelineStartForDay(dayMidnight);
  const tlEnd = timelineEndForDay(dayMidnight);

  const s = item.start.getTime();
  const e = item.end.getTime();
  if (e <= dayStart.getTime() || s >= dayEnd.getTime()) return null;

  const clipStart = new Date(Math.max(s, tlStart.getTime()));
  const clipEnd = new Date(Math.min(e, tlEnd.getTime()));
  if (clipEnd <= clipStart) return null;
  return {...item, clipStart, clipEnd};
}

function assignLanes(dayItems) {
  const sorted = [...dayItems].sort((a, b) => a.clipStart - b.clipStart);
  const laneEnds = [];
  const placed = [];
  for (const it of sorted) {
    const t0 = it.clipStart.getTime();
    let lane = 0;
    while (lane < laneEnds.length && laneEnds[lane] > t0) lane++;
    if (lane === laneEnds.length) laneEnds.push(it.clipEnd.getTime());
    else laneEnds[lane] = Math.max(laneEnds[lane], it.clipEnd.getTime());
    placed.push({...it, lane});
  }
  const totalLanes = Math.max(1, laneEnds.length);
  return placed.map((p) => ({...p, totalLanes}));
}

function layoutBlocksForDay(dayMidnight, allItems, tlStart) {
  const clipped = [];
  for (const it of allItems) {
    const c = clipItemToDay(it, dayMidnight);
    if (c) clipped.push(c);
  }
  const withLanes = assignLanes(clipped);
  return withLanes.map((it) => {
    const hoursFromTl = (it.clipStart - tlStart) / 3600000;
    const durH = (it.clipEnd - it.clipStart) / 3600000;
    const top = hoursFromTl * HOUR_HEIGHT;
    const height = Math.max(28, durH * HOUR_HEIGHT);
    const wPct = 100 / it.totalLanes;
    const leftPct = (it.lane / it.totalLanes) * 100;
    return {...it, top, height, wPct, leftPct};
  });
}

export default function WeeklySchedulePage() {
  const route = useRoute();
  const navigation = useNavigation();
  const {userId, sessionId} = route.params || {};

  const [weekStart, setWeekStart] = useState(() => startOfWeekMonday(new Date()));
  const [events, setEvents] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [unscheduled, setUnscheduled] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [connectUrl, setConnectUrl] = useState('');
  const [query, setQuery] = useState('');

  const screenW = Dimensions.get('window').width;

  const loadAll = useCallback(async () => {
    if (!userId) return;
    setLoading(true);
    setError('');
    try {
      const ws = new Date(weekStart);
      ws.setHours(0, 0, 0, 0);
      const weekEnd = addDays(ws, 7);
      const timeMin = new Date(ws.getTime() - 2 * 86400000).toISOString();
      const timeMax = new Date(weekEnd.getTime() + 2 * 86400000).toISOString();
      const data = await fetchScheduleSources(userId, {timeMin, timeMax});
      setEvents(data.events);
      setConnectUrl(data.connectUrl);
      setTasks(data.tasks);
      setUnscheduled(data.unscheduled);
    } catch (e) {
      setError(e?.message || 'Failed to load schedule');
    } finally {
      setLoading(false);
    }
  }, [userId, weekStart]);

  useEffect(() => {
    if (userId) loadAll();
  }, [userId, weekStart, loadAll]);

  const scheduleItems = useMemo(() => buildScheduleItems(events, tasks), [events, tasks]);

  const weekDays = useMemo(() => {
    const days = [];
    for (let i = 0; i < 7; i++) days.push(addDays(weekStart, i));
    return days;
  }, [weekStart]);

  const weekFilteredItems = useMemo(() => {
    const ws = new Date(weekStart);
    ws.setHours(0, 0, 0, 0);
    const we = addDays(ws, 7);
    return scheduleItems.filter((it) => it.end > ws && it.start < we);
  }, [scheduleItems, weekStart]);

  const dayLayouts = useMemo(() => {
    return weekDays.map((day) => {
      const tlStart = timelineStartForDay(day);
      return {
        date: day,
        blocks: layoutBlocksForDay(day, weekFilteredItems, tlStart),
      };
    });
  }, [weekDays, weekFilteredItems]);

  const dayColumnWidth = Math.max(DAY_MIN_W, (screenW - TIME_GUTTER_W - 40) / 7);

  const openConnect = async () => {
    if (!connectUrl) return;
    try {
      if (Platform.OS === 'web') {
        window.open(connectUrl, '_blank', 'noopener,noreferrer');
      } else {
        await Linking.openURL(connectUrl);
      }
    } catch (e) {
      Alert.alert('Could not open link', String(e?.message || e));
    }
  };

  const markDone = async (taskId) => {
    if (!userId || !taskId) return;
    try {
      const r = await fetch(`${API_BASE_URL}/api/tasks/${taskId}/complete`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId}),
      });
      const data = await r.json();
      if (!r.ok || !data?.success) throw new Error(data?.error || `HTTP ${r.status}`);
      await loadAll();
    } catch (e) {
      if (/^\d+$/.test(String(taskId))) {
        setTasks((prev) => prev.filter((t) => String(t._id) !== String(taskId)));
        return;
      }
      Alert.alert('Failed to complete task', String(e?.message || e));
    }
  };

  const prevWeek = () => setWeekStart((w) => addDays(w, -7));
  const nextWeek = () => setWeekStart((w) => addDays(w, 7));
  const thisWeek = () => setWeekStart(startOfWeekMonday(new Date()));

  const totalGridHeight = HOURS_SHOWN * HOUR_HEIGHT;

  const goHome = () => {
    if (navigation.canGoBack()) navigation.goBack();
    else navigation.navigate('Home', {userId, sessionId});
  };

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <TopSearchBar
        value={query}
        onChangeText={setQuery}
        leading="back"
        onLeadingPress={goHome}
        placeholder="Ask Aivis or search for any..."
      />

      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}>
        {!userId ? (
          <View style={styles.banner}>
            <Text style={styles.bannerText}>
              Missing userId — open this screen from an active session.
            </Text>
          </View>
        ) : null}

        {!!error ? (
          <View style={styles.bannerError}>
            <Text style={styles.bannerErrorText}>{error}</Text>
          </View>
        ) : null}

        {!!connectUrl ? (
          <View style={styles.connectCard}>
            <Text style={styles.connectTitle}>Connect Google Calendar</Text>
            <Text style={styles.connectHint}>
              Connect Google so the app can read your primary calendar. After upgrading scopes you
              may need to sign in again once.
            </Text>
            <TouchableOpacity onPress={openConnect} style={styles.connectBtn} activeOpacity={0.85}>
              <Text style={styles.connectBtnText}>Connect Google</Text>
            </TouchableOpacity>
          </View>
        ) : null}

        <View style={styles.weekNav}>
          <TouchableOpacity onPress={prevWeek} style={styles.weekNavBtn} activeOpacity={0.85}>
            <Text style={styles.weekNavText}>←</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={thisWeek} style={styles.weekNavBtnMid} activeOpacity={0.85}>
            <Text style={styles.weekNavTextMid}>{formatWeekRangeLabel(weekStart)}</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={nextWeek} style={styles.weekNavBtn} activeOpacity={0.85}>
            <Text style={styles.weekNavText}>→</Text>
          </TouchableOpacity>
        </View>

        <ScrollView horizontal showsHorizontalScrollIndicator={false} nestedScrollEnabled>
          <View style={styles.gridWrap}>
            <View style={[styles.timeGutter, {width: TIME_GUTTER_W, height: totalGridHeight + 40}]}>
              <View style={{height: 40}} />
              {Array.from({length: HOURS_SHOWN}, (_, i) => (
                <View key={i} style={[styles.hourRow, {height: HOUR_HEIGHT}]}>
                  <Text style={styles.hourLabel}>{formatHourRowLabel(TIMELINE_START_HOUR + i)}</Text>
                </View>
              ))}
            </View>

            {dayLayouts.map(({date, blocks}) => {
              const isToday = new Date().toDateString() === date.toDateString();
              return (
                <View key={String(date.getTime())} style={[styles.dayCol, {width: dayColumnWidth}]}>
                  <View style={styles.dayHeader}>
                    <Text style={styles.dayHeaderDow}>
                      {date.toLocaleDateString(undefined, {weekday: 'short'}).toUpperCase()}
                    </Text>
                    <View style={[styles.dayDomWrap, isToday && styles.dayDomToday]}>
                      <Text style={[styles.dayHeaderDom, isToday && styles.dayHeaderDomToday]}>
                        {date.getDate()}
                      </Text>
                    </View>
                  </View>
                  <View style={[styles.dayCanvas, {height: totalGridHeight}]}>
                    {Array.from({length: HOURS_SHOWN}, (_, i) => (
                      <View
                        key={i}
                        style={[styles.hourLine, {top: i * HOUR_HEIGHT, width: '100%'}]}
                      />
                    ))}
                    {blocks.map((b, idx) => {
                      const pal = pickEventColor(`${b.kind}-${b.summary || ''}-${idx}`);
                      return (
                        <TouchableOpacity
                          key={`${b.kind}-${idx}-${b.clipStart?.toISOString?.() || idx}`}
                          activeOpacity={0.88}
                          onPress={() => {
                            const t0 = toDateSafe(b.clipStart);
                            const t1 = toDateSafe(b.clipEnd);
                            const time =
                              t0 && t1
                                ? `${t0.toLocaleTimeString(undefined, {
                                    hour: 'numeric',
                                    minute: '2-digit',
                                  })} – ${t1.toLocaleTimeString(undefined, {
                                    hour: 'numeric',
                                    minute: '2-digit',
                                  })}`
                                : '';
                            if (b.kind === 'task') {
                              Alert.alert(b.summary, time, [
                                {text: 'Cancel', style: 'cancel'},
                                {text: 'Mark done', onPress: () => markDone(b.task_id)},
                              ]);
                            } else {
                              Alert.alert(b.summary, [b.location, time].filter(Boolean).join('\n'));
                            }
                          }}
                          style={[
                            styles.block,
                            {
                              top: b.top + 4,
                              height: b.height - 6,
                              left: `${b.leftPct}%`,
                              width: `${b.wPct}%`,
                              backgroundColor: pal.bg,
                              borderColor: pal.border,
                            },
                          ]}>
                          <Text style={styles.blockTitle} numberOfLines={3}>
                            {b.summary}
                          </Text>
                          <Text style={styles.blockTime} numberOfLines={1}>
                            {b.clipStart.toLocaleTimeString(undefined, {
                              hour: '2-digit',
                              minute: '2-digit',
                              hour12: false,
                            })}
                          </Text>
                        </TouchableOpacity>
                      );
                    })}
                  </View>
                </View>
              );
            })}
          </View>
        </ScrollView>

        {unscheduled.length > 0 && (
          <View style={styles.unCard}>
            <Text style={styles.unCardTitle}>Unscheduled</Text>
            <Text style={styles.unCardHint}>Tasks without a due time stay here.</Text>
            {unscheduled.slice(0, 24).map((t) => (
              <View key={String(t._id)} style={styles.unRow}>
                <Text style={styles.unTitle} numberOfLines={2}>
                  {t.title || '(Untitled)'}
                </Text>
                <Text style={styles.unMeta}>{t.priority || 'LATER'}</Text>
              </View>
            ))}
          </View>
        )}
      </ScrollView>

      <BottomNav
        leftIcon="home"
        centerIcon="plus"
        rightIcon="menu"
        onLeft={goHome}
        onCenter={() => navigation.navigate('Chat', {userId, sessionId})}
        onRight={() => navigation.navigate('Menu', {userId, sessionId})}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {flex: 1, backgroundColor: theme.colors.bg},
  scroll: {flex: 1},
  scrollContent: {paddingHorizontal: 20, paddingTop: 8, paddingBottom: 140},

  banner: {
    backgroundColor: theme.colors.surfaceMuted,
    borderRadius: 12,
    padding: 12,
    marginBottom: 12,
  },
  bannerText: {
    color: theme.colors.textSecondary,
    fontSize: 12,
    fontWeight: '600',
    textAlign: 'center',
  },
  bannerError: {
    backgroundColor: '#F6E0E0',
    borderRadius: 12,
    padding: 12,
    marginBottom: 12,
  },
  bannerErrorText: {color: '#8A2C2C', fontSize: 12, fontWeight: '700', textAlign: 'center'},

  connectCard: {
    padding: 14,
    borderRadius: 16,
    marginBottom: 12,
    backgroundColor: theme.colors.surface,
    ...theme.shadow.card,
  },
  connectTitle: {fontSize: 15, fontWeight: '700', color: theme.colors.textPrimary},
  connectHint: {marginTop: 4, fontSize: 12, color: theme.colors.textSecondary},
  connectBtn: {
    marginTop: 10,
    alignSelf: 'flex-start',
    borderRadius: theme.radius.pill,
    paddingVertical: 10,
    paddingHorizontal: 18,
    backgroundColor: theme.colors.textPrimary,
  },
  connectBtnText: {color: theme.colors.textOnDark, fontSize: 13, fontWeight: '700'},

  weekNav: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginVertical: 12,
    gap: 10,
  },
  weekNavBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: theme.colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
    ...theme.shadow.card,
  },
  weekNavBtnMid: {
    flex: 1,
    height: 40,
    borderRadius: theme.radius.pill,
    backgroundColor: theme.colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
    ...theme.shadow.card,
  },
  weekNavText: {fontSize: 18, fontWeight: '700', color: theme.colors.textPrimary},
  weekNavTextMid: {fontSize: 13, fontWeight: '700', color: theme.colors.textPrimary},

  gridWrap: {flexDirection: 'row', alignItems: 'flex-start'},
  timeGutter: {paddingRight: 6},
  hourRow: {justifyContent: 'flex-start', paddingTop: 0},
  hourLabel: {
    ...theme.type.hourLabel,
    color: theme.colors.textSecondary,
    textAlign: 'right',
  },
  dayCol: {marginLeft: 6},
  dayHeader: {
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 0,
  },
  dayHeaderDow: {
    fontSize: 10,
    fontWeight: '700',
    color: theme.colors.textSecondary,
    letterSpacing: 0.6,
  },
  dayDomWrap: {
    marginTop: 2,
    width: 24,
    height: 24,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  dayDomToday: {
    backgroundColor: theme.colors.textPrimary,
  },
  dayHeaderDom: {fontSize: 13, fontWeight: '700', color: theme.colors.textPrimary},
  dayHeaderDomToday: {color: theme.colors.textOnDark},

  dayCanvas: {
    position: 'relative',
    marginTop: 0,
    backgroundColor: 'transparent',
  },
  hourLine: {
    position: 'absolute',
    left: 0,
    borderTopWidth: 1,
    borderTopColor: theme.colors.border,
    height: 1,
  },
  block: {
    position: 'absolute',
    borderRadius: 14,
    borderWidth: 1,
    paddingHorizontal: 8,
    paddingVertical: 6,
    overflow: 'hidden',
  },
  blockTitle: {...theme.type.eventTitle, color: theme.colors.textPrimary},
  blockTime: {
    marginTop: 2,
    fontSize: 10,
    fontWeight: '500',
    color: theme.colors.textSecondary,
  },

  unCard: {
    marginTop: 16,
    padding: 16,
    borderRadius: 18,
    backgroundColor: theme.colors.surface,
    ...theme.shadow.card,
  },
  unCardTitle: {fontSize: 15, fontWeight: '700', color: theme.colors.textPrimary},
  unCardHint: {marginTop: 4, marginBottom: 10, fontSize: 12, color: theme.colors.textSecondary},
  unRow: {
    padding: 10,
    borderRadius: 12,
    backgroundColor: theme.colors.surfaceAlt,
    marginBottom: 8,
  },
  unTitle: {fontSize: 13, fontWeight: '600', color: theme.colors.textPrimary},
  unMeta: {marginTop: 4, fontSize: 11, fontWeight: '600', color: theme.colors.textSecondary},
});
