import React, {useEffect, useMemo, useState} from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Modal,
  TouchableOpacity,
  Platform,
  Linking,
  Alert,
} from 'react-native';
import {useRoute, useNavigation} from '@react-navigation/native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {Svg, Path} from 'react-native-svg';
import {LinearGradient} from 'expo-linear-gradient';
import {colors} from '../styles/colors';
import {commonStyles} from '../styles/commonStyles';
import {API_BASE_URL} from '../config/api';
import CalendarEvent from '../components/CalendarEvent';

function toDateSafe(value) {
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}

function formatDayLabel(date) {
  return date.toLocaleDateString('en-US', {weekday: 'long', month: 'short', day: 'numeric'});
}

function formatTimeLabel(date) {
  return date.toLocaleTimeString('en-US', {hour: 'numeric', minute: '2-digit'});
}

function startOfMonth(date) {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function sameDay(a, b) {
  return a && b && a.toDateString() === b.toDateString();
}

function getDaysInMonthGrid(monthDate) {
  const year = monthDate.getFullYear();
  const month = monthDate.getMonth();
  const firstDay = new Date(year, month, 1);
  const lastDay = new Date(year, month + 1, 0);
  const daysInMonth = lastDay.getDate();
  const startingDay = firstDay.getDay(); // 0=Sun

  const days = [];
  for (let i = 0; i < startingDay; i++) days.push(null);
  for (let d = 1; d <= daysInMonth; d++) days.push(new Date(year, month, d));
  return days;
}

export default function SchedulerPage() {
  const route = useRoute();
  const navigation = useNavigation();
  const {userId, sessionId} = route.params || {};

  const [events, setEvents] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [unscheduledTasks, setUnscheduledTasks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [connectUrl, setConnectUrl] = useState('');

  const [monthDate, setMonthDate] = useState(() => startOfMonth(new Date()));
  const [selectedDate, setSelectedDate] = useState(() => new Date());
  const [showDayModal, setShowDayModal] = useState(false);

  const loadAll = async () => {
    if (!userId) return;
    setLoading(true);
    setError('');
    setConnectUrl('');
    try {
      const [eventsRes, tasksRes] = await Promise.all([loadCalendarEvents(userId), loadTasks(userId)]);
      setEvents(eventsRes.events);
      setConnectUrl(eventsRes.connectUrl);
      setTasks(tasksRes.tasks);
      setUnscheduledTasks(tasksRes.unscheduled);
    } catch (e) {
      setError(e?.message || 'Failed to load schedule');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (userId) loadAll();
  }, [userId]);

  const scheduleItems = useMemo(() => {
    const items = [];

    for (const ev of events || []) {
      const start = toDateSafe(ev.start);
      if (!start) continue;
      items.push({
        kind: 'event',
        start,
        end: toDateSafe(ev.end) || start,
        summary: ev.summary || '(Untitled event)',
        location: ev.location || '',
        description: ev.description || '',
        provider: ev.provider || '',
        html_link: ev.html_link || '',
        _raw: ev,
      });
    }

    for (const t of tasks || []) {
      const start = toDateSafe(t.due_datetime);
      if (!start) continue;
      const end = new Date(start.getTime() + 30 * 60 * 1000);
      items.push({
        kind: 'task',
        start,
        end,
        task_id: t._id,
        summary: t.title || '(Untitled task)',
        priority: t.priority || 'LATER',
        priority_score: t.priority_score || 0,
        reason: t.reason || '',
        source: t.source || '',
        _raw: t,
      });
    }

    items.sort((a, b) => a.start.getTime() - b.start.getTime());
    return items;
  }, [events, tasks]);

  const itemsByDayKey = useMemo(() => {
    const map = new Map();
    for (const it of scheduleItems) {
      const key = it.start.toDateString();
      map.set(key, (map.get(key) || 0) + 1);
    }
    return map;
  }, [scheduleItems]);

  const selectedDayItems = useMemo(() => {
    const dayKey = selectedDate.toDateString();
    return scheduleItems.filter((it) => it.start.toDateString() === dayKey);
  }, [scheduleItems, selectedDate]);

  const monthName = useMemo(() => {
    return monthDate.toLocaleDateString('en-US', {month: 'long', year: 'numeric'});
  }, [monthDate]);

  const monthGridDays = useMemo(() => getDaysInMonthGrid(monthDate), [monthDate]);
  const today = useMemo(() => new Date(), []);

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
      Alert.alert('Failed to complete task', String(e?.message || e));
    }
  };

  const addTaskToCalendar = async (task) => {
    if (!userId || !task) return;
    const start = toDateSafe(task?.due_datetime);
    if (!start) {
      Alert.alert('Missing due date', 'Set a due date first so we know when to schedule it.');
      return;
    }
    const end = new Date(start.getTime() + 60 * 60 * 1000);
    try {
      const r = await fetch(`${API_BASE_URL}/api/calendar/create`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          user_id: userId,
          summary: task.title || 'Task',
          start_time: start.toISOString(),
          end_time: end.toISOString(),
          description: task.reason || '',
        }),
      });
      const data = await r.json();
      if (data?.action === 'connect_google' && data?.connect_url) {
        setConnectUrl(data.connect_url);
        Alert.alert('Connect Google', 'Please connect Google Calendar to create events.');
        return;
      }
      if (!r.ok || !data?.success) throw new Error(data?.error || `HTTP ${r.status}`);
      Alert.alert('Added to calendar', data?.summary ? `"${data.summary}" created.` : 'Event created.');
      await loadAll();
    } catch (e) {
      Alert.alert('Failed to create calendar event', String(e?.message || e));
    }
  };

  const prevMonth = () => {
    const next = startOfMonth(new Date(monthDate.getFullYear(), monthDate.getMonth() - 1, 1));
    setMonthDate(next);
    setSelectedDate(new Date(next.getFullYear(), next.getMonth(), 1));
  };

  const nextMonth = () => {
    const next = startOfMonth(new Date(monthDate.getFullYear(), monthDate.getMonth() + 1, 1));
    setMonthDate(next);
    setSelectedDate(new Date(next.getFullYear(), next.getMonth(), 1));
  };

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}>
          <Svg width="24" height="24" viewBox="0 0 24 24" fill={colors.primary[900]}>
            <Path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z" />
          </Svg>
        </TouchableOpacity>
        <View style={styles.headerCenter}>
          <Text style={styles.title}>Scheduler</Text>
          <Text style={styles.subtitle}>
            {userId ? `for ${userId}` : 'Your schedule'}{sessionId ? ` • ${sessionId.slice(-6)}` : ''}
          </Text>
        </View>
        <TouchableOpacity
          onPress={loadAll}
          disabled={!userId || loading}
          style={[styles.refreshButton, (!userId || loading) && styles.buttonDisabled]}>
          <Text style={styles.refreshText}>{loading ? '…' : '↻'}</Text>
        </TouchableOpacity>
      </View>

      <ScrollView style={styles.scroll} contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
        {!userId ? (
          <View style={styles.banner}>
            <Text style={styles.bannerText}>Missing userId — open Scheduler from an active session.</Text>
          </View>
        ) : null}

        {!!error ? (
          <View style={styles.bannerError}>
            <Text style={styles.bannerErrorText}>{error}</Text>
          </View>
        ) : null}

        {!!connectUrl ? (
          <View style={styles.connectCard}>
            <Text style={styles.cardTitle}>Connect Google Calendar</Text>
            <Text style={styles.cardHint}>To load and create calendar events, connect your Google account.</Text>
            <TouchableOpacity onPress={openConnect} style={styles.connectButton}>
              <LinearGradient colors={[colors.accent[500], colors.secondary[600]]} style={styles.connectButtonGradient}>
                <Text style={styles.connectButtonText}>Connect Google</Text>
              </LinearGradient>
            </TouchableOpacity>
          </View>
        ) : null}

        <View style={styles.card}>
          <Text style={styles.cardTitle}>📅 Schedule</Text>
          <Text style={styles.cardHint}>Switch months, tap a date to see what’s scheduled.</Text>

          <LinearGradient colors={[colors.accent[500], colors.secondary[600]]} style={styles.monthHeader}>
            <TouchableOpacity onPress={prevMonth} style={styles.monthNavBtn}>
              <Text style={styles.monthNavText}>←</Text>
            </TouchableOpacity>
            <Text style={styles.monthTitle}>{monthName}</Text>
            <TouchableOpacity onPress={nextMonth} style={styles.monthNavBtn}>
              <Text style={styles.monthNavText}>→</Text>
            </TouchableOpacity>
          </LinearGradient>

          <View style={styles.calendarGrid}>
            <View style={styles.dayHeaders}>
              {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((d) => (
                <View key={d} style={styles.dayHeader}>
                  <Text style={styles.dayHeaderText}>{d}</Text>
                </View>
              ))}
            </View>

            <View style={styles.daysGrid}>
              {monthGridDays.map((day, idx) => {
                const isEmpty = !day;
                const isToday = day ? sameDay(day, today) : false;
                const isSelected = day ? sameDay(day, selectedDate) : false;
                const count = day ? itemsByDayKey.get(day.toDateString()) || 0 : 0;

                return (
                  <TouchableOpacity
                    key={`${idx}-${day ? day.toISOString() : 'empty'}`}
                    onPress={() => {
                      if (!day) return;
                      setSelectedDate(day);
                      setShowDayModal(true);
                    }}
                    disabled={isEmpty}
                    style={[
                      styles.dayCell,
                      isEmpty && styles.dayCellEmpty,
                      isToday && styles.dayCellToday,
                      isSelected && styles.dayCellSelected,
                    ]}>
                    {day ? (
                      <>
                        <Text
                          style={[
                            styles.dayNumber,
                            isToday && styles.dayNumberToday,
                            isSelected && styles.dayNumberSelected,
                          ]}>
                          {day.getDate()}
                        </Text>
                        {count > 0 ? (
                          <View style={styles.dayCountPill}>
                            <Text style={styles.dayCountText}>{count}</Text>
                          </View>
                        ) : null}
                      </>
                    ) : null}
                  </TouchableOpacity>
                );
              })}
            </View>
          </View>

          <View style={styles.selectedPanel}>
            <Text style={styles.selectedTitle}>Items for {formatDayLabel(selectedDate)}</Text>

            {selectedDayItems.length === 0 ? (
              <View style={styles.emptyInline}>
                <Text style={styles.emptyInlineText}>No items scheduled for this day.</Text>
              </View>
            ) : (
              selectedDayItems.map((it, idx) => {
                if (it.kind === 'event') {
                  return (
                    <CalendarEvent
                      key={`ev-${idx}-${it.start.toISOString()}`}
                      event={{
                        summary: it.summary,
                        start: it.start.toISOString(),
                        end: it.end.toISOString(),
                        location: it.location,
                        description: it.description,
                        attendees: it?._raw?.attendees || [],
                      }}
                      onEventClick={() => {
                        Alert.alert(it.summary, it.location ? `Location: ${it.location}` : 'Calendar event');
                      }}
                    />
                  );
                }

                return (
                  <TaskScheduleCard
                    key={`task-${it.task_id}`}
                    item={it}
                    onMarkDone={() => markDone(it.task_id)}
                    onAddToCalendar={() => addTaskToCalendar(it._raw)}
                  />
                );
              })
            )}
          </View>
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>🧩 Unscheduled tasks</Text>
          <Text style={styles.cardHint}>Tasks without a due date won’t appear in the timeline.</Text>

          {unscheduledTasks.length === 0 ? (
            <Text style={styles.smallEmpty}>No unscheduled tasks.</Text>
          ) : (
            unscheduledTasks.slice(0, 20).map((t) => (
              <View key={t._id} style={styles.unscheduledRow}>
                <Text style={styles.unscheduledTitle} numberOfLines={2}>
                  {t.title || '(Untitled task)'}
                </Text>
                <Text style={styles.unscheduledMeta} numberOfLines={1}>
                  {t.priority || 'LATER'}
                </Text>
              </View>
            ))
          )}
        </View>
      </ScrollView>

      <Modal
        visible={showDayModal}
        transparent
        animationType="fade"
        onRequestClose={() => setShowDayModal(false)}>
        <View style={styles.modalOverlay}>
          <View style={styles.modalContainer}>
            <LinearGradient colors={[colors.accent[500], colors.secondary[600]]} style={styles.modalHeader}>
              <Text style={styles.modalTitle}>{formatDayLabel(selectedDate)}</Text>
              <TouchableOpacity onPress={() => setShowDayModal(false)} style={styles.modalCloseBtn}>
                <Text style={styles.modalCloseText}>✕</Text>
              </TouchableOpacity>
            </LinearGradient>

            <ScrollView style={styles.modalBody} contentContainerStyle={styles.modalBodyContent} showsVerticalScrollIndicator={false}>
              {selectedDayItems.length === 0 ? (
                <View style={styles.modalEmpty}>
                  <Text style={styles.modalEmptyEmoji}>🗓️</Text>
                  <Text style={styles.modalEmptyText}>No items scheduled.</Text>
                </View>
              ) : (
                selectedDayItems.map((it, idx) => {
                  if (it.kind === 'event') {
                    return (
                      <CalendarEvent
                        key={`m-ev-${idx}-${it.start.toISOString()}`}
                        event={{
                          summary: it.summary,
                          start: it.start.toISOString(),
                          end: it.end.toISOString(),
                          location: it.location,
                          description: it.description,
                          attendees: it?._raw?.attendees || [],
                        }}
                        onEventClick={() => {
                          Alert.alert(it.summary, it.location ? `Location: ${it.location}` : 'Calendar event');
                        }}
                      />
                    );
                  }
                  return (
                    <TaskScheduleCard
                      key={`m-task-${it.task_id}`}
                      item={it}
                      onMarkDone={() => markDone(it.task_id)}
                      onAddToCalendar={() => addTaskToCalendar(it._raw)}
                    />
                  );
                })
              )}
            </ScrollView>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

async function loadCalendarEvents(userId) {
  const r = await fetch(`${API_BASE_URL}/api/calendar/events`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({user_id: userId, max_results: 50}),
  });
  const data = await r.json();
  if (data?.action === 'connect_google' && data?.connect_url) {
    return {events: [], connectUrl: data.connect_url};
  }
  if (!r.ok || !data?.success) {
    throw new Error(data?.error || `HTTP ${r.status}`);
  }
  return {events: data.events || [], connectUrl: ''};
}

async function loadTasks(userId) {
  const r = await fetch(`${API_BASE_URL}/api/tasks?user_id=${encodeURIComponent(userId)}&limit=200`, {
    method: 'GET',
    headers: {'Content-Type': 'application/json'},
  });
  const data = await r.json();
  if (!r.ok || !data?.success) throw new Error(data?.error || `HTTP ${r.status}`);

  const all = data.tasks || [];
  const withDue = [];
  const withoutDue = [];
  for (const t of all) {
    if (t?.due_datetime) withDue.push(t);
    else withoutDue.push(t);
  }
  return {tasks: withDue, unscheduled: withoutDue};
}

function TaskScheduleCard({item, onMarkDone, onAddToCalendar}) {
  const startLabel = `${formatTimeLabel(item.start)}`;
  const priorityColor =
    item.priority === 'NOW' ? '#EF4444' : item.priority === 'SOON' ? '#F59E0B' : colors.dark[600];

  return (
    <View style={styles.taskCard}>
      <View style={styles.taskHeader}>
        <View style={styles.taskHeaderLeft}>
          <LinearGradient colors={[colors.secondary[500], colors.accent[600]]} style={styles.taskIcon}>
            <Text style={styles.taskIconText}>✅</Text>
          </LinearGradient>
          <View style={{flex: 1}}>
            <Text style={styles.taskTitle} numberOfLines={2}>
              {item.summary}
            </Text>
            <Text style={styles.taskMeta} numberOfLines={1}>
              ⏰ {startLabel} • {item.priority} • score {item.priority_score}
            </Text>
          </View>
        </View>
        <View style={[styles.priorityPill, {backgroundColor: priorityColor + '20'}]}>
          <Text style={[styles.priorityPillText, {color: priorityColor}]}>{item.priority}</Text>
        </View>
      </View>

      {!!item.reason ? (
        <View style={styles.taskReasonBox}>
          <Text style={styles.taskReason} numberOfLines={3}>
            💡 {item.reason}
          </Text>
        </View>
      ) : null}

      <View style={styles.taskActions}>
        <TouchableOpacity onPress={onMarkDone} style={styles.taskAction}>
          <LinearGradient colors={[colors.accent[500], colors.accent[600]]} style={styles.taskActionGrad}>
            <Text style={styles.taskActionText}>Mark done</Text>
          </LinearGradient>
        </TouchableOpacity>
        <TouchableOpacity onPress={onAddToCalendar} style={[styles.taskAction, styles.taskActionSecondary]}>
          <Text style={styles.taskActionTextSecondary}>Add to calendar</Text>
        </TouchableOpacity>
      </View>
    </View>
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
  buttonDisabled: {opacity: 0.6},
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
    ...commonStyles.glassEffectStrong,
    padding: 16,
    borderRadius: 14,
    marginBottom: 14,
    borderWidth: 1,
    borderColor: colors.accent[500] + '30',
  },
  connectButton: {borderRadius: 12, overflow: 'hidden', ...commonStyles.shadowSm},
  connectButtonGradient: {paddingVertical: 12, alignItems: 'center'},
  connectButtonText: {color: colors.primary[50], fontWeight: '800'},
  empty: {alignItems: 'center', paddingVertical: 18},
  emptyEmoji: {fontSize: 42, marginBottom: 10},
  emptyText: {fontSize: 13, fontWeight: '700', color: colors.primary[900] + '70'},
  daySection: {marginTop: 4, marginBottom: 8},
  dayTitle: {fontSize: 14, fontWeight: '800', color: colors.primary[900], marginBottom: 8},

  monthHeader: {
    marginTop: 10,
    borderRadius: 14,
    paddingVertical: 14,
    paddingHorizontal: 12,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  monthTitle: {fontSize: 18, fontWeight: '800', color: colors.primary[50]},
  monthNavBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(255,255,255,0.2)',
  },
  monthNavText: {fontSize: 20, fontWeight: '900', color: colors.primary[50]},
  calendarGrid: {
    marginTop: 12,
    backgroundColor: colors.primary[50],
    borderRadius: 14,
    borderWidth: 1,
    borderColor: colors.dark[500] + '12',
    padding: 12,
  },
  dayHeaders: {flexDirection: 'row', marginBottom: 8},
  dayHeader: {flex: 1, alignItems: 'center', paddingVertical: 6},
  dayHeaderText: {fontSize: 12, fontWeight: '800', color: colors.primary[900] + '70'},
  daysGrid: {flexDirection: 'row', flexWrap: 'wrap'},
  dayCell: {
    width: '14.28%',
    aspectRatio: 1,
    padding: 6,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.dark[500] + '12',
    backgroundColor: colors.primary[50],
    marginBottom: 6,
  },
  dayCellEmpty: {
    backgroundColor: colors.primary[100] + '50',
    borderColor: 'transparent',
  },
  dayCellToday: {
    borderColor: colors.accent[500],
    borderWidth: 2,
    backgroundColor: colors.accent[500] + '12',
  },
  dayCellSelected: {
    borderColor: colors.secondary[500],
    borderWidth: 2,
    backgroundColor: colors.secondary[500] + '12',
  },
  dayNumber: {fontSize: 14, fontWeight: '900', color: colors.primary[900]},
  dayNumberToday: {color: colors.accent[600]},
  dayNumberSelected: {color: colors.secondary[600]},
  dayCountPill: {
    marginTop: 6,
    alignSelf: 'flex-start',
    backgroundColor: colors.secondary[500] + '20',
    borderRadius: 999,
    paddingHorizontal: 8,
    paddingVertical: 2,
  },
  dayCountText: {fontSize: 11, fontWeight: '900', color: colors.secondary[700]},
  selectedPanel: {marginTop: 14},
  selectedTitle: {fontSize: 14, fontWeight: '900', color: colors.primary[900], marginBottom: 10},
  emptyInline: {
    backgroundColor: colors.primary[100] + '80',
    borderRadius: 12,
    padding: 12,
    borderWidth: 1,
    borderColor: colors.dark[500] + '10',
  },
  emptyInlineText: {textAlign: 'center', color: colors.primary[900] + '70', fontWeight: '700', fontSize: 12},

  taskCard: {
    ...commonStyles.glassEffect,
    padding: 14,
    marginBottom: 12,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.dark[500] + '20',
  },
  taskHeader: {flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10},
  taskHeaderLeft: {flexDirection: 'row', alignItems: 'flex-start', flex: 1, gap: 12},
  taskIcon: {width: 40, height: 40, borderRadius: 10, alignItems: 'center', justifyContent: 'center'},
  taskIconText: {fontSize: 18},
  taskTitle: {fontSize: 16, fontWeight: '700', color: colors.primary[900]},
  taskMeta: {marginTop: 4, fontSize: 12, fontWeight: '600', color: colors.primary[900] + '70'},
  priorityPill: {paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999},
  priorityPillText: {fontSize: 12, fontWeight: '800'},
  taskReasonBox: {
    marginTop: 10,
    backgroundColor: colors.primary[100] + '80',
    padding: 10,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: colors.dark[500] + '10',
  },
  taskReason: {fontSize: 12, fontWeight: '600', color: colors.secondary[700], lineHeight: 16},
  taskActions: {flexDirection: 'row', gap: 10, marginTop: 12},
  taskAction: {flex: 1, borderRadius: 10, overflow: 'hidden', ...commonStyles.shadowSm},
  taskActionGrad: {paddingVertical: 10, alignItems: 'center'},
  taskActionText: {color: colors.primary[50], fontSize: 13, fontWeight: '800'},
  taskActionSecondary: {
    backgroundColor: colors.primary[100] + '80',
    borderWidth: 1,
    borderColor: colors.dark[500] + '20',
    justifyContent: 'center',
  },
  taskActionTextSecondary: {color: colors.primary[900] + '75', fontSize: 13, fontWeight: '800', textAlign: 'center'},

  smallEmpty: {color: colors.primary[900] + '60', fontSize: 12, fontWeight: '700', textAlign: 'center'},
  unscheduledRow: {
    backgroundColor: colors.primary[50],
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.dark[500] + '10',
    padding: 12,
    marginBottom: 10,
  },
  unscheduledTitle: {fontSize: 13, fontWeight: '800', color: colors.primary[900]},
  unscheduledMeta: {marginTop: 6, fontSize: 11, fontWeight: '700', color: colors.primary[900] + '70'},

  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.45)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 16,
  },
  modalContainer: {
    width: '100%',
    maxWidth: 820,
    maxHeight: '90%',
    backgroundColor: colors.primary[50],
    borderRadius: 16,
    overflow: 'hidden',
    ...commonStyles.shadowLg,
  },
  modalHeader: {
    paddingVertical: 16,
    paddingHorizontal: 16,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  modalTitle: {
    color: colors.primary[50],
    fontSize: 18,
    fontWeight: '900',
  },
  modalCloseBtn: {
    width: 40,
    height: 40,
    borderRadius: 12,
    backgroundColor: 'rgba(255,255,255,0.22)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  modalCloseText: {
    color: colors.primary[50],
    fontSize: 18,
    fontWeight: '900',
  },
  modalBody: {flex: 1},
  modalBodyContent: {padding: 16, paddingBottom: 20},
  modalEmpty: {alignItems: 'center', paddingVertical: 26},
  modalEmptyEmoji: {fontSize: 48, marginBottom: 10},
  modalEmptyText: {fontSize: 13, fontWeight: '800', color: colors.primary[900] + '70'},
});

