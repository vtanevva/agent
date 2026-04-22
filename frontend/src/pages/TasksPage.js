import React, {useEffect, useMemo, useState} from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  TextInput,
  Platform,
} from 'react-native';
import {useRoute, useNavigation} from '@react-navigation/native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {Svg, Path} from 'react-native-svg';
import {colors} from '../styles/colors';
import {commonStyles} from '../styles/commonStyles';
import {API_BASE_URL} from '../config/api';
import {fetchSqliteTasks, mapSqliteTaskToUi} from '../api/sqliteTasks';

const uid = () => Math.random().toString(36).slice(2, 10);

export default function TasksPage() {
  const route = useRoute();
  const navigation = useNavigation();
  const {userId, sessionId} = route.params || {};

  const [newTodo, setNewTodo] = useState('');
  const [todos, setTodos] = useState([]);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState('');

  const loadTasks = async () => {
    if (!userId) return;
    setLoading(true);
    setError('');
    try {
      const rows = await fetchSqliteTasks(200);
      const mapped = rows.map((row) => mapSqliteTaskToUi(row)).filter(Boolean);
      setTodos(mapped);
    } catch (e) {
      setError(e?.message || 'Failed to load tasks');
      setTodos([]);
    } finally {
      setLoading(false);
    }
  };

  const syncFromGmail = async () => {
    if (!userId) return;
    alert(
      'Processing past/recent emails is disabled.\n\nThis app only processes new incoming emails (via Gmail watch).'
    );
  };

  useEffect(() => {
    if (userId) loadTasks();
  }, [userId]);

  // NEW: Group by pipeline priority (NOW/SOON/LATER)
  const priorityGroups = useMemo(() => {
    const groups = {NOW: [], SOON: [], LATER: []};
    for (const t of todos) {
      if (t.status !== 'done') {
        const priority = t.priority || 'LATER';
        if (groups[priority]) {
          groups[priority].push(t);
        } else {
          groups.LATER.push(t);
        }
      }
    }
    return groups;
  }, [todos]);

  const columns = useMemo(() => {
    const groups = {todo: [], in_progress: [], done: []};
    for (const t of todos) groups[t.status]?.push(t);
    return groups;
  }, [todos]);

  const prioritizationRows = useMemo(() => {
    const calcScore = (impact, effort) => {
      const i = Number(impact) || 0;
      const e = Number(effort) || 1;
      return i / Math.max(1, e);
    };
    return [...todos]
      .filter((t) => t.status !== 'done')
      .map((t) => ({
        ...t,
        score: calcScore(t.impact, t.effort),
        priority:
          calcScore(t.impact, t.effort) >= 2 ? 'High' : calcScore(t.impact, t.effort) >= 1 ? 'Med' : 'Low',
      }))
      .sort((a, b) => b.score - a.score);
  }, [todos]);

  const scheduleRows = useMemo(() => {
    // Placeholder schedule suggestions (later we can map these to Calendar events)
    return [
      {time: 'Today 10:00', task: 'Reply to proposal email', duration: '15m'},
      {time: 'Today 14:30', task: 'Book demo slot + send invite', duration: '20m'},
      {time: 'Tomorrow 09:00', task: 'Review invoice + mark handled', duration: '10m'},
    ];
  }, []);

  const addTodo = async () => {
    const text = (newTodo || '').trim();
    if (!text || !userId) return;

    const localId = `local-${uid()}`;
    const pipelineLike = {
      _id: localId,
      title: text,
      status: 'pending',
      priority: 'LATER',
      priority_score: 0,
      reason: '',
      source: 'manual',
      due_datetime: null,
      created_at: new Date().toISOString(),
      actions: [],
    };
    setTodos((prev) => [
      {
        id: localId,
        text,
        status: 'todo',
        priority: 'LATER',
        priorityScore: 0,
        reason: '',
        impact: 2,
        effort: 2,
        source: 'manual',
        meta: {
          description: '',
          due_date: null,
          source_ref: '',
          created_at: pipelineLike.created_at,
          actions: [],
        },
        _taskData: pipelineLike,
        _sqlite: false,
        _localOnly: true,
      },
      ...prev,
    ]);
    setNewTodo('');
  };

  const markTaskDone = async (id) => {
    if (!userId) return;

    const task = todos.find((t) => t.id === id);
    if (task?._sqlite || task?._localOnly || String(id).startsWith('local-')) {
      setTodos((prev) => prev.map((t) => (t.id === id ? {...t, status: 'done'} : t)));
      return;
    }

    try {
      const r = await fetch(`${API_BASE_URL}/api/tasks/${id}/complete`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId}),
      });
      const data = await r.json();
      if (!r.ok || !data?.success) {
        throw new Error(data?.error || 'Failed to complete task');
      }

      await loadTasks();
    } catch (e) {
      setError(e?.message || 'Failed to complete task');
    }
  };

  const cycleStatus = async (id) => {
    if (!userId) return;

    const task = todos.find((t) => t.id === id);
    if (!task || !task._taskData) return;

    const statusMap = {
      todo: 'pending',
      in_progress: 'in_progress',
      done: 'completed',
    };
    const nextStatusMap = {
      todo: 'in_progress',
      in_progress: 'completed',
      done: 'pending',
    };

    const currentStatus = task.status;
    const nextStatus = nextStatusMap[currentStatus] || 'pending';
    const apiStatus = statusMap[nextStatus] || 'pending';

    if (task._sqlite || task._localOnly || String(id).startsWith('local-')) {
      setTodos((prev) =>
        prev.map((t) =>
          t.id === id
            ? {
                ...t,
                status: nextStatus,
                _taskData: {...t._taskData, status: apiStatus},
              }
            : t
        )
      );
      return;
    }

    try {
      const r = await fetch(`${API_BASE_URL}/memory/tasks/${id}`, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          status: apiStatus,
        }),
      });
      const data = await r.json();
      if (!r.ok || !data?.success) {
        throw new Error(data?.error || 'Failed to update task');
      }

      await loadTasks();
    } catch (e) {
      setError(e?.message || 'Failed to update task');
    }
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
          <Text style={styles.title}>Tasks</Text>
          <Text style={styles.subtitle}>
            {userId ? `for ${userId}` : 'Organize your day'}{sessionId ? ` • ${sessionId.slice(-6)}` : ''}
          </Text>
        </View>
        <View style={{width: 40}} />
      </View>

      <ScrollView style={styles.scroll} contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
        {/* NEW: Priority Groups (NOW/SOON/LATER) */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>📋 Prioritized Tasks</Text>
          <Text style={styles.cardHint}>
            Tasks load from the core SQLite store (GET /debug/sql/tasks). New tasks and status changes stay on this device
            until the legacy task API is wired back up.
          </Text>

          {!userId ? (
            <View style={styles.banner}>
              <Text style={styles.bannerText}>Missing userId — open Tasks from an active session.</Text>
            </View>
          ) : (
            <View style={styles.controlsRow}>
              <TouchableOpacity
                onPress={syncFromGmail}
                disabled={syncing || loading}
                style={[styles.controlButton, (syncing || loading) && styles.controlButtonDisabled]}>
                <Text style={styles.controlButtonText}>{syncing ? 'Processing…' : '🚀 Process Emails'}</Text>
              </TouchableOpacity>
              <TouchableOpacity
                onPress={loadTasks}
                disabled={syncing || loading}
                style={[styles.controlButtonAlt, (syncing || loading) && styles.controlButtonDisabled]}>
                <Text style={styles.controlButtonTextAlt}>{loading ? 'Refreshing…' : 'Refresh'}</Text>
              </TouchableOpacity>
            </View>
          )}

          {error ? (
            <View style={styles.bannerError}>
              <Text style={styles.bannerErrorText}>{error}</Text>
            </View>
          ) : null}

          <View style={styles.addRow}>
            <TextInput
              value={newTodo}
              onChangeText={setNewTodo}
              placeholder="Add a task…"
              placeholderTextColor={colors.primary[900] + '60'}
              style={styles.input}
              returnKeyType="done"
              onSubmitEditing={addTodo}
            />
            <TouchableOpacity onPress={addTodo} style={styles.addButton}>
              <Text style={styles.addButtonText}>Add</Text>
            </TouchableOpacity>
          </View>

          {/* Priority Groups */}
          <View style={styles.priorityGroups}>
            <PriorityGroup
              title="🔴 NOW"
              subtitle="Urgent"
              count={priorityGroups.NOW.length}
              items={priorityGroups.NOW}
              onPressItem={markTaskDone}
              color="#EF4444"
            />
            <PriorityGroup
              title="🟡 SOON"
              subtitle="Important"
              count={priorityGroups.SOON.length}
              items={priorityGroups.SOON}
              onPressItem={markTaskDone}
              color="#F59E0B"
            />
            <PriorityGroup
              title="⚪ LATER"
              subtitle="Low priority"
              count={priorityGroups.LATER.length}
              items={priorityGroups.LATER}
              onPressItem={markTaskDone}
              color="#9CA3AF"
            />
          </View>
        </View>

        {/* Traditional Status View (Legacy) */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Status View</Text>
          <Text style={styles.cardHint}>Traditional Kanban view. Tap to move status.</Text>
          
          <View style={styles.todoColumns}>
            <TodoColumn
              title="To do"
              count={columns.todo.length}
              items={columns.todo}
              onPressItem={cycleStatus}
            />
            <TodoColumn
              title="In progress"
              count={columns.in_progress.length}
              items={columns.in_progress}
              onPressItem={cycleStatus}
            />
            <TodoColumn
              title="Done"
              count={columns.done.length}
              items={columns.done}
              onPressItem={cycleStatus}
            />
          </View>
        </View>

        {/* Prioritization */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Prioritization</Text>
          <Text style={styles.cardHint}>Auto-sorted by score = impact ÷ effort (quick win first).</Text>

          <Table
            headers={['Task', 'Priority', 'Impact', 'Effort']}
            rows={prioritizationRows.map((r) => [r.text, r.priority, String(r.impact), String(r.effort)])}
          />
        </View>

        {/* Schedule */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Schedule</Text>
          <Text style={styles.cardHint}>Suggested focus blocks (placeholder).</Text>

          <Table
            headers={['Time', 'Task', 'Duration']}
            rows={scheduleRows.map((r) => [r.time, r.task, r.duration])}
            columnFlex={[1, 2, 0.8]}
          />
        </View>

        <View style={styles.footerNote}>
          <Text style={styles.footerText}>
            Tasks are now unified across email, chat, and manual entries. All tasks are stored in MongoDB.
          </Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

function PriorityGroup({title, subtitle, count, items, onPressItem, color}) {
  return (
    <View style={styles.priorityGroup}>
      <View style={styles.priorityHeader}>
        <View>
          <Text style={styles.priorityTitle}>{title}</Text>
          <Text style={styles.prioritySubtitle}>{subtitle}</Text>
        </View>
        <View style={[styles.priorityBadge, {backgroundColor: color + '20'}]}>
          <Text style={[styles.priorityCount, {color: color}]}>{count}</Text>
        </View>
      </View>
      {items.length === 0 ? (
        <Text style={styles.todoEmpty}>No tasks</Text>
      ) : (
        items.map((t) => (
          <TouchableOpacity key={t.id} onPress={() => onPressItem(t.id)} style={[styles.priorityItem, {borderLeftColor: color}]}>
            <View style={styles.priorityItemHeader}>
              <Text style={styles.priorityItemText} numberOfLines={2}>
                {t.text}
              </Text>
              {t.priorityScore !== undefined && (
                <View style={[styles.scoreBadge, {backgroundColor: color + '15'}]}>
                  <Text style={[styles.scoreText, {color: color}]}>{t.priorityScore}</Text>
                </View>
              )}
            </View>
            {!!t.reason && (
              <Text style={styles.reasonText} numberOfLines={2}>
                💡 {t.reason}
              </Text>
            )}
            {!!t?.meta?.due_date && (
              <Text style={styles.dueText} numberOfLines={1}>
                ⏰ {new Date(t.meta.due_date).toLocaleString('en-US', {
                  month: 'short',
                  day: 'numeric',
                  hour: 'numeric',
                  minute: '2-digit',
                })}
              </Text>
            )}
            {!!t?.meta?.actions && t.meta.actions.length > 0 && (
              <Text style={styles.actionsText} numberOfLines={1}>
                Actions: {t.meta.actions.join(', ')}
              </Text>
            )}
          </TouchableOpacity>
        ))
      )}
    </View>
  );
}

function TodoColumn({title, count, items, onPressItem}) {
  return (
    <View style={styles.todoColumn}>
      <View style={styles.todoColumnHeader}>
        <Text style={styles.todoColumnTitle}>{title}</Text>
        <Text style={styles.todoCount}>{count}</Text>
      </View>
      {items.length === 0 ? (
        <Text style={styles.todoEmpty}>—</Text>
      ) : (
        items.map((t) => (
          <TouchableOpacity key={t.id} onPress={() => onPressItem(t.id)} style={styles.todoItem}>
            <Text style={styles.todoItemText} numberOfLines={2}>
              {t.text}
            </Text>
            {!!t?.meta?.description && (
              <Text style={styles.todoMeta} numberOfLines={1}>
                {t.meta.description}
              </Text>
            )}
            {!!t?.source && t.source !== 'manual' && (
              <Text style={styles.todoMetaSecondary} numberOfLines={1}>
                From: {t.source}
              </Text>
            )}
            {!!t?.meta?.due_date && (
              <Text style={styles.todoMetaSecondary} numberOfLines={1}>
                Due: {new Date(t.meta.due_date).toLocaleDateString()}
              </Text>
            )}
            {!!t?.priority && (
              <Text style={styles.todoMetaSecondary} numberOfLines={1}>
                Priority: {t.priority}
              </Text>
            )}
          </TouchableOpacity>
        ))
      )}
    </View>
  );
}

function Table({headers, rows, columnFlex}) {
  const flexes = columnFlex || headers.map(() => 1);
  return (
    <View style={styles.table}>
      <View style={[styles.tableRow, styles.tableHeaderRow]}>
        {headers.map((h, idx) => (
          <Text key={h} style={[styles.tableHeaderCell, {flex: flexes[idx] || 1}]}>
            {h}
          </Text>
        ))}
      </View>
      {rows.length === 0 ? (
        <View style={styles.tableRow}>
          <Text style={styles.tableEmpty}>No items yet.</Text>
        </View>
      ) : (
        rows.map((r, i) => (
          <View
            key={`${i}-${r[0]}`}
            style={[
              styles.tableRow,
              i % 2 === 0 ? styles.tableRowAlt : null,
              Platform.OS === 'web' ? {cursor: 'default'} : null,
            ]}>
            {r.map((cell, idx) => (
              <Text
                key={`${i}-${idx}`}
                style={[styles.tableCell, {flex: flexes[idx] || 1}]}
                numberOfLines={2}>
                {cell}
              </Text>
            ))}
          </View>
        ))
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.primary[50],
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: colors.dark[500] + '20',
    backgroundColor: colors.primary[50],
  },
  backButton: {
    padding: 8,
  },
  headerCenter: {
    flex: 1,
    alignItems: 'center',
  },
  title: {
    fontSize: 20,
    fontWeight: 'bold',
    color: colors.primary[900],
  },
  subtitle: {
    fontSize: 12,
    color: colors.primary[900] + '70',
    marginTop: 2,
  },
  scroll: {
    flex: 1,
  },
  scrollContent: {
    padding: 16,
    paddingBottom: 28,
  },
  card: {
    ...commonStyles.glassEffectStrong,
    padding: 16,
    borderRadius: 14,
    marginBottom: 14,
  },
  cardTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: colors.primary[900],
  },
  cardHint: {
    marginTop: 6,
    marginBottom: 12,
    fontSize: 12,
    color: colors.primary[900] + '70',
  },
  controlsRow: {
    flexDirection: 'row',
    gap: 10,
    marginBottom: 12,
  },
  controlButton: {
    flex: 1,
    backgroundColor: colors.secondary[500],
    paddingVertical: 12,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    ...commonStyles.shadowSm,
  },
  controlButtonAlt: {
    width: 110,
    backgroundColor: colors.primary[100],
    paddingVertical: 12,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.dark[500] + '15',
  },
  controlButtonDisabled: {
    opacity: 0.6,
  },
  controlButtonText: {
    color: colors.primary[50],
    fontWeight: '800',
    fontSize: 13,
  },
  controlButtonTextAlt: {
    color: colors.primary[900],
    fontWeight: '800',
    fontSize: 13,
  },
  banner: {
    backgroundColor: colors.primary[100],
    borderRadius: 12,
    padding: 12,
    borderWidth: 1,
    borderColor: colors.dark[500] + '10',
    marginBottom: 12,
  },
  bannerText: {
    color: colors.primary[900] + '90',
    fontSize: 12,
    fontWeight: '600',
    textAlign: 'center',
  },
  bannerError: {
    backgroundColor: colors.dark[500] + '10',
    borderRadius: 12,
    padding: 12,
    borderWidth: 1,
    borderColor: colors.dark[500] + '25',
    marginBottom: 12,
  },
  bannerErrorText: {
    color: colors.dark[600],
    fontSize: 12,
    fontWeight: '700',
    textAlign: 'center',
  },
  addRow: {
    flexDirection: 'row',
    gap: 10,
    marginBottom: 12,
  },
  input: {
    flex: 1,
    backgroundColor: colors.primary[100],
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 10,
    fontSize: 14,
    color: colors.primary[900],
    borderWidth: 1,
    borderColor: colors.dark[500] + '10',
  },
  addButton: {
    backgroundColor: colors.accent[500],
    paddingHorizontal: 14,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    ...commonStyles.shadowSm,
  },
  addButtonText: {
    color: colors.primary[50],
    fontWeight: '700',
    fontSize: 14,
  },
  todoColumns: {
    flexDirection: 'row',
    gap: 10,
  },
  todoColumn: {
    flex: 1,
    backgroundColor: colors.primary[50],
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.dark[500] + '10',
    padding: 10,
  },
  todoColumnHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  todoColumnTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.primary[900],
  },
  todoCount: {
    fontSize: 12,
    color: colors.secondary[600],
    fontWeight: '700',
  },
  todoEmpty: {
    color: colors.primary[900] + '40',
    textAlign: 'center',
    marginTop: 10,
  },
  todoItem: {
    backgroundColor: colors.accent[500] + '12',
    borderWidth: 1,
    borderColor: colors.accent[500] + '20',
    paddingVertical: 10,
    paddingHorizontal: 10,
    borderRadius: 10,
    marginBottom: 8,
  },
  todoItemText: {
    color: colors.primary[900],
    fontSize: 12,
    fontWeight: '600',
  },
  todoMeta: {
    marginTop: 6,
    fontSize: 11,
    fontWeight: '700',
    color: colors.secondary[700],
  },
  todoMetaSecondary: {
    marginTop: 2,
    fontSize: 10,
    fontWeight: '600',
    color: colors.primary[900] + '80',
  },
  table: {
    borderWidth: 1,
    borderColor: colors.dark[500] + '15',
    borderRadius: 12,
    overflow: 'hidden',
  },
  tableRow: {
    flexDirection: 'row',
    paddingVertical: 10,
    paddingHorizontal: 12,
    backgroundColor: colors.primary[50],
    borderBottomWidth: 1,
    borderBottomColor: colors.dark[500] + '10',
  },
  tableHeaderRow: {
    backgroundColor: colors.primary[100],
  },
  tableRowAlt: {
    backgroundColor: colors.primary[100] + '80',
  },
  tableHeaderCell: {
    fontSize: 12,
    fontWeight: '800',
    color: colors.primary[900],
  },
  tableCell: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.primary[900],
    paddingRight: 8,
  },
  tableEmpty: {
    fontSize: 12,
    color: colors.primary[900] + '70',
  },
  footerNote: {
    paddingTop: 4,
  },
  footerText: {
    fontSize: 12,
    color: colors.primary[900] + '70',
    textAlign: 'center',
  },
  // NEW: Priority Groups Styles
  priorityGroups: {
    gap: 12,
  },
  priorityGroup: {
    backgroundColor: colors.primary[50],
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.dark[500] + '10',
    padding: 12,
    marginBottom: 12,
  },
  priorityHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 12,
  },
  priorityTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: colors.primary[900],
  },
  prioritySubtitle: {
    fontSize: 11,
    fontWeight: '600',
    color: colors.primary[900] + '60',
    marginTop: 2,
  },
  priorityBadge: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
  },
  priorityCount: {
    fontSize: 14,
    fontWeight: '800',
  },
  priorityItem: {
    backgroundColor: colors.primary[100] + '40',
    borderLeftWidth: 3,
    paddingVertical: 12,
    paddingHorizontal: 12,
    borderRadius: 10,
    marginBottom: 8,
  },
  priorityItemHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    marginBottom: 6,
  },
  priorityItemText: {
    flex: 1,
    color: colors.primary[900],
    fontSize: 14,
    fontWeight: '700',
    marginRight: 8,
  },
  scoreBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 8,
    minWidth: 28,
    alignItems: 'center',
  },
  scoreText: {
    fontSize: 12,
    fontWeight: '800',
  },
  reasonText: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.secondary[700],
    marginBottom: 4,
    lineHeight: 16,
  },
  dueText: {
    fontSize: 11,
    fontWeight: '600',
    color: colors.primary[900] + '70',
    marginTop: 4,
  },
  actionsText: {
    fontSize: 10,
    fontWeight: '600',
    color: colors.accent[600],
    marginTop: 4,
  },
});


