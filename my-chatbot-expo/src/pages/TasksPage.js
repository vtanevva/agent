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
      // Use new unified tasks API
      const r = await fetch(`${API_BASE_URL}/memory/tasks?user_id=${userId}&limit=200`, {
        method: 'GET',
        headers: {'Content-Type': 'application/json'},
      });
      const data = await r.json();
      if (!r.ok || !data?.success) {
        throw new Error(data?.error || `HTTP ${r.status}`);
      }
      // Map tasks to local format
      const mapped = (data.tasks || []).map((task) => ({
        id: task._id || uid(),
        text: task.title || '',
        status: task.status === 'completed' ? 'done' : task.status === 'in_progress' ? 'in_progress' : 'todo',
        priority: task.priority || 'medium',
        impact: task.priority === 'high' ? 4 : task.priority === 'medium' ? 3 : 2,
        effort: 2,
        source: task.source || 'manual',
        meta: {
          description: task.description || '',
          due_date: task.due_date || null,
          source_ref: task.source_ref || '',
          created_at: task.created_at || '',
        },
        // Store full task for API updates
        _taskData: task,
      }));
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
    setSyncing(true);
    setError('');
    try {
      // Trigger email todo extraction (this will create tasks automatically)
      const r = await fetch(`${API_BASE_URL}/api/gmail/extract-todos-recent`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId, max_threads: 5}),
      });
      const data = await r.json();
      if (!r.ok || !data?.success) {
        throw new Error(data?.error || `HTTP ${r.status}`);
      }
      // Reload tasks from unified API
      await loadTasks();
    } catch (e) {
      setError(e?.message || 'Failed to sync from Gmail');
    } finally {
      setSyncing(false);
    }
  };

  useEffect(() => {
    if (userId) loadTasks();
  }, [userId]);

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
    
    try {
      // Create task via API
      const r = await fetch(`${API_BASE_URL}/memory/tasks`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          user_id: userId,
          title: text,
          status: 'pending',
          priority: 'medium',
          source: 'manual',
        }),
      });
      const data = await r.json();
      if (!r.ok || !data?.success) {
        throw new Error(data?.error || 'Failed to create task');
      }
      
      // Reload tasks to get the new one
      await loadTasks();
      setNewTodo('');
    } catch (e) {
      setError(e?.message || 'Failed to add task');
    }
  };

  const cycleStatus = async (id) => {
    if (!userId) return;
    
    const task = todos.find((t) => t.id === id);
    if (!task || !task._taskData) return;
    
    // Map UI status to API status
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
    
    try {
      // Update task via API
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
      
      // Reload tasks to get updated status
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
        {/* Todos */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Todos</Text>
          <Text style={styles.cardHint}>Tap a task to move it: Todo → In progress → Done.</Text>

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
                <Text style={styles.controlButtonText}>{syncing ? 'Syncing…' : 'Sync from Gmail'}</Text>
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
});


