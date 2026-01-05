import React, {useMemo, useState} from 'react';
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

const uid = () => Math.random().toString(36).slice(2, 10);

export default function TasksPage() {
  const route = useRoute();
  const navigation = useNavigation();
  const {userId, sessionId} = route.params || {};

  const [newTodo, setNewTodo] = useState('');
  const [todos, setTodos] = useState([
    {id: uid(), text: 'Reply to the client about the proposal', status: 'todo', impact: 4, effort: 2},
    {id: uid(), text: 'Book calendar slot for demo', status: 'todo', impact: 3, effort: 1},
    {id: uid(), text: 'Review invoice email', status: 'in_progress', impact: 3, effort: 2},
    {id: uid(), text: 'Send weekly update', status: 'done', impact: 2, effort: 1},
  ]);

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

  const addTodo = () => {
    const text = (newTodo || '').trim();
    if (!text) return;
    setTodos((prev) => [{id: uid(), text, status: 'todo', impact: 3, effort: 2}, ...prev]);
    setNewTodo('');
  };

  const cycleStatus = (id) => {
    const next = {todo: 'in_progress', in_progress: 'done', done: 'todo'};
    setTodos((prev) =>
      prev.map((t) => (t.id === id ? {...t, status: next[t.status] || 'todo'} : t)),
    );
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
            Next: we can connect this page to MongoDB-backed extracted email todos and calendar events.
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


