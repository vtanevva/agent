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
import {Svg, Path} from 'react-native-svg';
import {LinearGradient} from 'expo-linear-gradient';
import {colors} from '../styles/colors';
import {commonStyles} from '../styles/commonStyles';
import {API_BASE_URL} from '../config/api';
import {buildScheduleItems, fetchScheduleSources, toDateSafe} from '../api/scheduleData';

const TIMELINE_START_HOUR = 6;
const HOUR_HEIGHT = 38;
const HOURS_SHOWN = 18; // 6:00 through 23:59 (before next midnight)
const TIME_GUTTER_W = 46;
const DAY_MIN_W = 104;

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
  const d = new Date(2000, 0, 1, hour24, 0, 0);
  return d.toLocaleTimeString(undefined, {hour: 'numeric', hour12: true});
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

/** Clip schedule item to one calendar day and the visible timeline (6am–midnight). */
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
  const totalH = HOURS_SHOWN * HOUR_HEIGHT;
  return withLanes.map((it) => {
    const hoursFromTl = (it.clipStart - tlStart) / 3600000;
    const durH = (it.clipEnd - it.clipStart) / 3600000;
    const top = hoursFromTl * HOUR_HEIGHT;
    const height = Math.max(20, durH * HOUR_HEIGHT);
    const wPct = 100 / it.totalLanes;
    const leftPct = (it.lane / it.totalLanes) * 100;
    return {...it, top, height, wPct, leftPct, totalH};
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

  const screenW = Dimensions.get('window').width;

  const loadAll = useCallback(async () => {
    if (!userId) return;
    setLoading(true);
    setError('');
    try {
      const data = await fetchScheduleSources(userId);
      setEvents(data.events);
      setConnectUrl(data.connectUrl);
      setTasks(data.tasks);
      setUnscheduled(data.unscheduled);
    } catch (e) {
      setError(e?.message || 'Failed to load schedule');
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    if (userId) loadAll();
  }, [userId, loadAll]);

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

  const dayColumnWidth = Math.max(DAY_MIN_W, (screenW - TIME_GUTTER_W - 20) / 7);

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

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}>
          <Svg width="24" height="24" viewBox="0 0 24 24" fill={colors.primary[900]}>
            <Path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z" />
          </Svg>
        </TouchableOpacity>
        <View style={styles.headerCenter}>
          <Text style={styles.title}>Week schedule</Text>
          <Text style={styles.subtitle}>
            {userId ? `Hourly view • ${userId}` : 'Sign in'}
            {sessionId ? ` • …${sessionId.slice(-6)}` : ''}
          </Text>
        </View>
        <TouchableOpacity onPress={loadAll} disabled={!userId || loading} style={styles.refreshButton}>
          <Text style={styles.refreshText}>{loading ? '…' : '↻'}</Text>
        </TouchableOpacity>
      </View>

      <ScrollView style={styles.scroll} contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
        {!userId ? (
          <View style={styles.banner}>
            <Text style={styles.bannerText}>Missing userId — open this screen from an active session.</Text>
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
            <Text style={styles.connectHint}>Load meetings into the week grid.</Text>
            <TouchableOpacity onPress={openConnect} style={styles.connectBtn}>
              <LinearGradient colors={[colors.accent[500], colors.secondary[600]]} style={styles.connectBtnGrad}>
                <Text style={styles.connectBtnText}>Connect Google</Text>
              </LinearGradient>
            </TouchableOpacity>
          </View>
        ) : null}

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Weekly timeline</Text>
          <Text style={styles.cardHint}>
            Each column is one day ({formatWeekRangeLabel(weekStart)}). Rows are hours from 6:00 to midnight. Calendar
            events and tasks with a due time appear in the grid.
          </Text>

          <View style={styles.weekNav}>
            <TouchableOpacity onPress={prevWeek} style={styles.weekNavBtn}>
              <Text style={styles.weekNavText}>← Prev</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={thisWeek} style={styles.weekNavBtnMid}>
              <Text style={styles.weekNavTextMid}>This week</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={nextWeek} style={styles.weekNavBtn}>
              <Text style={styles.weekNavText}>Next →</Text>
            </TouchableOpacity>
          </View>

          <ScrollView horizontal showsHorizontalScrollIndicator nestedScrollEnabled>
            <View style={styles.gridWrap}>
              <View style={[styles.timeGutter, {width: TIME_GUTTER_W, height: totalGridHeight + 28}]}>
                <View style={{height: 28}} />
                {Array.from({length: HOURS_SHOWN}, (_, i) => (
                  <View key={i} style={[styles.hourRow, {height: HOUR_HEIGHT}]}>
                    <Text style={styles.hourLabel}>{formatHourRowLabel(TIMELINE_START_HOUR + i)}</Text>
                  </View>
                ))}
              </View>

              {dayLayouts.map(({date, blocks}) => {
                const tlStart = timelineStartForDay(date);
                const isToday = new Date().toDateString() === date.toDateString();
                return (
                  <View key={String(date.getTime())} style={[styles.dayCol, {width: dayColumnWidth}]}>
                    <View style={[styles.dayHeader, isToday && styles.dayHeaderToday]}>
                      <Text style={styles.dayHeaderDow}>{date.toLocaleDateString(undefined, {weekday: 'short'})}</Text>
                      <Text style={styles.dayHeaderDom}>{date.getDate()}</Text>
                    </View>
                    <View style={[styles.dayCanvas, {height: totalGridHeight}]}>
                      {Array.from({length: HOURS_SHOWN}, (_, i) => (
                        <View
                          key={i}
                          style={[styles.hourLine, {top: i * HOUR_HEIGHT, width: '100%'}]}
                        />
                      ))}
                      {blocks.map((b, idx) => (
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
                              top: b.top,
                              height: b.height,
                              left: `${b.leftPct}%`,
                              width: `${b.wPct}%`,
                              backgroundColor:
                                b.kind === 'event'
                                  ? colors.secondary[500] + '28'
                                  : b.priority === 'NOW'
                                    ? '#EF444428'
                                    : b.priority === 'SOON'
                                      ? '#F59E0B28'
                                      : colors.accent[500] + '28',
                              borderColor:
                                b.kind === 'event' ? colors.secondary[600] + '90' : colors.accent[600] + '80',
                            },
                          ]}>
                          <Text style={styles.blockTitle} numberOfLines={3}>
                            {b.summary}
                          </Text>
                          <Text style={styles.blockTime} numberOfLines={1}>
                            {b.clipStart.toLocaleTimeString(undefined, {
                              hour: 'numeric',
                              minute: '2-digit',
                            })}
                          </Text>
                        </TouchableOpacity>
                      ))}
                    </View>
                  </View>
                );
              })}
            </View>
          </ScrollView>
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Unscheduled tasks</Text>
          <Text style={styles.cardHint}>Tasks without a due time stay here (same as the month scheduler).</Text>
          {unscheduled.length === 0 ? (
            <Text style={styles.smallEmpty}>None</Text>
          ) : (
            unscheduled.slice(0, 24).map((t) => (
              <View key={String(t._id)} style={styles.unRow}>
                <Text style={styles.unTitle} numberOfLines={2}>
                  {t.title || '(Untitled)'}
                </Text>
                <Text style={styles.unMeta}>{t.priority || 'LATER'}</Text>
              </View>
            ))
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {flex: 1, backgroundColor: colors.primary[50]},
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: colors.dark[500] + '20',
    backgroundColor: colors.primary[50],
  },
  backButton: {padding: 8},
  headerCenter: {flex: 1, alignItems: 'center'},
  title: {fontSize: 20, fontWeight: 'bold', color: colors.primary[900]},
  subtitle: {fontSize: 12, color: colors.primary[900] + '70', marginTop: 2},
  refreshButton: {
    width: 40,
    height: 40,
    borderRadius: 12,
    backgroundColor: colors.primary[100],
    borderWidth: 1,
    borderColor: colors.dark[500] + '15',
    alignItems: 'center',
    justifyContent: 'center',
  },
  refreshText: {fontSize: 18, fontWeight: '900', color: colors.primary[900]},
  scroll: {flex: 1},
  scrollContent: {padding: 16, paddingBottom: 28},
  card: {
    ...commonStyles.glassEffectStrong,
    padding: 16,
    borderRadius: 14,
    marginBottom: 14,
  },
  cardTitle: {fontSize: 18, fontWeight: '700', color: colors.primary[900]},
  cardHint: {marginTop: 6, marginBottom: 12, fontSize: 12, color: colors.primary[900] + '70'},
  banner: {
    backgroundColor: colors.primary[100],
    borderRadius: 12,
    padding: 12,
    borderWidth: 1,
    borderColor: colors.dark[500] + '10',
    marginBottom: 12,
  },
  bannerText: {color: colors.primary[900] + '90', fontSize: 12, fontWeight: '600', textAlign: 'center'},
  bannerError: {
    backgroundColor: colors.dark[500] + '10',
    borderRadius: 12,
    padding: 12,
    borderWidth: 1,
    borderColor: colors.dark[500] + '25',
    marginBottom: 12,
  },
  bannerErrorText: {color: colors.dark[600], fontSize: 12, fontWeight: '700', textAlign: 'center'},
  connectCard: {
    padding: 14,
    borderRadius: 14,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: colors.accent[500] + '35',
    backgroundColor: colors.primary[100] + '90',
  },
  connectTitle: {fontSize: 15, fontWeight: '800', color: colors.primary[900]},
  connectHint: {marginTop: 4, fontSize: 12, color: colors.primary[900] + '70'},
  connectBtn: {marginTop: 10, borderRadius: 12, overflow: 'hidden', alignSelf: 'flex-start'},
  connectBtnGrad: {paddingVertical: 10, paddingHorizontal: 16},
  connectBtnText: {color: colors.primary[50], fontWeight: '800'},
  weekNav: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 12,
    gap: 8,
  },
  weekNavBtn: {
    paddingVertical: 8,
    paddingHorizontal: 10,
    borderRadius: 10,
    backgroundColor: colors.primary[100],
    borderWidth: 1,
    borderColor: colors.dark[500] + '12',
  },
  weekNavBtnMid: {
    flex: 1,
    paddingVertical: 8,
    borderRadius: 10,
    backgroundColor: colors.secondary[500] + '18',
    borderWidth: 1,
    borderColor: colors.secondary[500] + '35',
    alignItems: 'center',
  },
  weekNavText: {fontSize: 12, fontWeight: '800', color: colors.primary[900]},
  weekNavTextMid: {fontSize: 12, fontWeight: '900', color: colors.secondary[700]},
  gridWrap: {flexDirection: 'row', alignItems: 'flex-start'},
  timeGutter: {paddingRight: 4},
  hourRow: {justifyContent: 'flex-start', paddingTop: 0},
  hourLabel: {fontSize: 10, fontWeight: '700', color: colors.primary[900] + '65', textAlign: 'right'},
  dayCol: {marginLeft: 4},
  dayHeader: {
    height: 28,
    borderRadius: 8,
    backgroundColor: colors.primary[100],
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 0,
    borderWidth: 1,
    borderColor: colors.dark[500] + '10',
  },
  dayHeaderToday: {
    backgroundColor: colors.accent[500] + '22',
    borderColor: colors.accent[500] + '50',
  },
  dayHeaderDow: {fontSize: 10, fontWeight: '800', color: colors.primary[900] + '75'},
  dayHeaderDom: {fontSize: 13, fontWeight: '900', color: colors.primary[900]},
  dayCanvas: {
    position: 'relative',
    marginTop: 0,
    borderLeftWidth: 1,
    borderRightWidth: 1,
    borderBottomWidth: 1,
    borderColor: colors.dark[500] + '12',
    backgroundColor: colors.primary[50] + 'cc',
  },
  hourLine: {
    position: 'absolute',
    left: 0,
    borderTopWidth: 1,
    borderTopColor: colors.dark[500] + '10',
    height: 1,
  },
  block: {
    position: 'absolute',
    borderRadius: 6,
    borderWidth: 1,
    paddingHorizontal: 4,
    paddingVertical: 3,
    overflow: 'hidden',
  },
  blockTitle: {fontSize: 10, fontWeight: '800', color: colors.primary[900]},
  blockTime: {fontSize: 9, fontWeight: '700', color: colors.primary[900] + '75', marginTop: 2},
  smallEmpty: {fontSize: 12, color: colors.primary[900] + '60', fontWeight: '600'},
  unRow: {
    padding: 10,
    borderRadius: 10,
    backgroundColor: colors.primary[50],
    borderWidth: 1,
    borderColor: colors.dark[500] + '10',
    marginBottom: 8,
  },
  unTitle: {fontSize: 13, fontWeight: '700', color: colors.primary[900]},
  unMeta: {marginTop: 4, fontSize: 11, fontWeight: '700', color: colors.primary[900] + '65'},
});
