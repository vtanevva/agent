import React, {useCallback, useMemo, useState} from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  Platform,
  Linking,
  Modal,
  Pressable,
  useWindowDimensions,
} from 'react-native';
import {useRoute, useNavigation} from '@react-navigation/native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {Svg, Path} from 'react-native-svg';
import {colors} from '../styles/colors';
import {commonStyles} from '../styles/commonStyles';
import {fetchSqliteProjectsOverview} from '../api/sqliteProjects';
import {fetchScheduleSources} from '../api/scheduleData';
import {useAutoRefresh} from '../hooks/useAutoRefresh';

function formatShortDate(iso) {
  if (!iso || typeof iso !== 'string') return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 10);
  return d.toLocaleDateString(undefined, {month: 'short', day: 'numeric', year: 'numeric'});
}

function normalizeForMatch(value) {
  return String(value || '')
    .toLowerCase()
    .replace(/[\u2019']/g, '')
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function inferProjectMeetings(projectName, events) {
  const projectNorm = normalizeForMatch(projectName);
  if (!projectNorm) return [];
  const out = [];
  for (const ev of events || []) {
    const summaryNorm = normalizeForMatch(ev?.summary || ev?.title || '');
    if (!summaryNorm) continue;
    if (summaryNorm.includes(projectNorm) || projectNorm.includes(summaryNorm)) {
      out.push(ev);
    }
  }
  out.sort((a, b) => new Date(a.start || 0).getTime() - new Date(b.start || 0).getTime());
  return out.slice(0, 6);
}

export default function ProjectsPage() {
  const route = useRoute();
  const navigation = useNavigation();
  const {width: windowWidth} = useWindowDimensions();
  const {userId, sessionId} = route.params || {};

  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(null);
  const [calendarEvents, setCalendarEvents] = useState([]);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    if (!userId) {
      setProjects([]);
      setError('Sign in to load your projects for this account.');
      setLoading(false);
      return;
    }
    try {
      const [rows, schedule] = await Promise.all([
        fetchSqliteProjectsOverview(40, userId),
        fetchScheduleSources(userId),
      ]);
      setProjects(rows);
      setCalendarEvents(Array.isArray(schedule?.events) ? schedule.events : []);
      setSelected((prev) => {
        if (!prev?.project?.id) return prev;
        const next = rows.find((r) => r.id === prev.project.id);
        if (!next) return null;
        return {
          project: next,
          meetings: inferProjectMeetings(next.name, Array.isArray(schedule?.events) ? schedule.events : []),
        };
      });
    } catch (e) {
      setError(e?.message || 'Failed to load projects');
      setProjects([]);
      setSelected(null);
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useAutoRefresh(load);

  const gridLayout = useMemo(() => {
    const scrollPad = 16;
    const cardPad = 16;
    const gap = 12;
    const totalHPadding = scrollPad * 2 + cardPad * 2;
    const usableW = Math.max(260, windowWidth - totalHPadding);
    const colCount = usableW >= 720 ? 3 : usableW >= 420 ? 2 : 1;
    const tileW = (usableW - gap * (colCount - 1)) / colCount;
    return {colCount, tileW, gap};
  }, [windowWidth]);

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}>
          <Svg width="24" height="24" viewBox="0 0 24 24" fill={colors.primary[900]}>
            <Path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z" />
          </Svg>
        </TouchableOpacity>
        <View style={styles.headerCenter}>
          <Text style={styles.title}>Projects</Text>
          <Text style={styles.subtitle}>
            {userId ? `Workspace ${userId}` : 'SQLite overview'}
            {sessionId ? ` • …${sessionId.slice(-6)}` : ''}
          </Text>
        </View>
        <TouchableOpacity onPress={load} style={styles.refreshBtn} disabled={loading}>
          <Text style={styles.refreshBtnText}>{loading ? '…' : 'Refresh'}</Text>
        </TouchableOpacity>
      </View>

      <ScrollView style={styles.scroll} contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Active workstreams</Text>
          <Text style={styles.cardHint}>
            Tap a tile to open full details: project memory, recent tasks, and calendar meetings inferred from titles.
          </Text>

          {error ? (
            <View style={styles.bannerError}>
              <Text style={styles.bannerErrorText}>{error}</Text>
            </View>
          ) : null}

          {loading && projects.length === 0 ? (
            <View style={styles.loadingRow}>
              <ActivityIndicator color={colors.secondary[600]} />
              <Text style={styles.loadingText}>Loading projects…</Text>
            </View>
          ) : null}

          {!loading && projects.length === 0 && !error ? (
            <Text style={styles.empty}>No projects yet. They appear as messages are classified per client.</Text>
          ) : null}

          <View style={styles.grid}>
            {projects.map((p, idx) => {
              const meetings = inferProjectMeetings(p.name, calendarEvents);
              const isEndOfRow = (idx + 1) % gridLayout.colCount === 0;
              return (
                <View
                  key={String(p.id)}
                  style={{
                    width: gridLayout.tileW,
                    marginRight: isEndOfRow ? 0 : gridLayout.gap,
                    marginBottom: gridLayout.gap,
                  }}>
                  <ProjectGridTile
                    project={p}
                    meetings={meetings}
                    onPress={() => setSelected({project: p, meetings})}
                  />
                </View>
              );
            })}
          </View>
        </View>
      </ScrollView>

      <ProjectDetailModal
        visible={!!selected}
        project={selected?.project}
        meetings={selected?.meetings || []}
        onClose={() => setSelected(null)}
      />
    </SafeAreaView>
  );
}

function ProjectGridTile({project, meetings, onPress}) {
  const tasks = project.tasks || [];
  const status = (project.status || '—').replace(/_/g, ' ');
  const priority = project.priority || '—';
  const client = project.client_name || 'Client';
  const deadline = project.deadline ? formatShortDate(project.deadline) : '—';

  return (
    <TouchableOpacity
      onPress={onPress}
      activeOpacity={0.88}
      style={[styles.tileOuter, Platform.OS === 'web' ? {cursor: 'pointer'} : null]}>
      <View style={styles.tileHeader}>
        <Text style={styles.tileName} numberOfLines={3}>
          {project.name}
        </Text>
      </View>
      <Text style={styles.tileClient} numberOfLines={1}>
        {client}
      </Text>
      <View style={styles.tileMetaRow}>
        <Text style={styles.tileMetaLine} numberOfLines={1}>
          {status} · {priority}
        </Text>
        <Text style={styles.tileMetaLine} numberOfLines={1}>
          Due {deadline}
        </Text>
      </View>
      <View style={styles.tileFooter}>
        <Text style={styles.tileBadge}>{tasks.length} tasks</Text>
        <Text style={styles.tileBadge}>{meetings.length} meetings</Text>
      </View>
      <Text style={styles.tileHint}>View details</Text>
    </TouchableOpacity>
  );
}

function ProjectDetailModal({visible, project, meetings, onClose}) {
  if (!project) return null;

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <View style={styles.modalRoot}>
        <Pressable style={styles.modalBackdrop} onPress={onClose} accessibilityRole="button" accessibilityLabel="Close" />
        <View style={styles.modalCardWrap}>
          <View style={styles.modalCard}>
            <View style={styles.modalHeader}>
              <View style={styles.modalHeaderText}>
                <Text style={styles.modalTitle} numberOfLines={3}>
                  {project.name}
                </Text>
                <Text style={styles.modalSubtitle} numberOfLines={1}>
                  {project.client_name || 'Client'}
                </Text>
              </View>
              <TouchableOpacity onPress={onClose} style={styles.modalCloseBtn} hitSlop={{top: 12, bottom: 12, left: 12, right: 12}}>
                <Text style={styles.modalCloseText}>✕</Text>
              </TouchableOpacity>
            </View>
            <ScrollView style={styles.modalScroll} contentContainerStyle={styles.modalScrollContent} showsVerticalScrollIndicator>
              <View style={styles.badgeRow}>
                <MetaChip label="Status" value={(project.status || '—').replace(/_/g, ' ')} />
                <MetaChip label="Priority" value={project.priority || '—'} />
                <MetaChip label="Deadline" value={project.deadline ? formatShortDate(project.deadline) : '—'} />
              </View>
              <ProjectDetailBody project={project} meetings={meetings} />
            </ScrollView>
          </View>
        </View>
      </View>
    </Modal>
  );
}

function ProjectDetailBody({project, meetings}) {
  const ctx = project.context;
  const tasks = project.tasks || [];

  return (
    <View style={styles.projectBody}>
      {!!project.description && (
        <View style={styles.block}>
          <Text style={styles.blockTitle}>Description</Text>
          <Text style={styles.blockBody}>{project.description}</Text>
        </View>
      )}

      {ctx ? (
        <View style={styles.contextBox}>
          <Text style={styles.contextTitle}>Project memory</Text>
          <ContextLine label="Summary" text={ctx.summary} />
          <ContextLine label="Current status" text={ctx.current_status} />
          <ContextLine label="Priorities" text={ctx.current_priorities} />
          <ContextLine label="Blockers" text={ctx.blockers} />
          <ContextLine label="Next steps" text={ctx.next_steps} />
          {Array.isArray(ctx.key_contacts_json) && ctx.key_contacts_json.length > 0 ? (
            <Text style={styles.contextFooter}>{ctx.key_contacts_json.length} key contacts on file</Text>
          ) : null}
          {Array.isArray(ctx.important_links_json) && ctx.important_links_json.length > 0 ? (
            <Text style={styles.contextFooter}>{ctx.important_links_json.length} important links on file</Text>
          ) : null}
        </View>
      ) : (
        <Text style={styles.noContext}>No project context row yet — it fills in as the assistant updates memory.</Text>
      )}

      <View style={styles.tasksHeader}>
        <Text style={styles.tasksTitle}>Recent tasks</Text>
        <Text style={styles.tasksCount}>{tasks.length}</Text>
      </View>
      {tasks.length === 0 ? (
        <Text style={styles.noTasks}>No tasks linked to this project in SQLite.</Text>
      ) : (
        tasks.map((t) => (
          <View key={String(t.id)} style={styles.taskRow}>
            <Text style={styles.taskTitle} numberOfLines={3}>
              {t.title}
            </Text>
            <Text style={styles.taskMeta} numberOfLines={1}>
              {t.source || '—'} · {t.classification_type || '—'} · {formatShortDate(t.created_at)}
            </Text>
          </View>
        ))
      )}

      <View style={styles.tasksHeader}>
        <Text style={styles.tasksTitle}>Meetings</Text>
        <Text style={styles.tasksCount}>{meetings.length}</Text>
      </View>
      {meetings.length === 0 ? (
        <Text style={styles.noTasks}>No meetings linked to this project yet.</Text>
      ) : (
        meetings.map((m, idx) => {
          const openLink = m.html_link || m.hangout_link || '';
          const startText = formatShortDate(m.start);
          return (
            <View key={String(m.id || `${project.id}-meeting-${idx}`)} style={styles.taskRow}>
              <Text style={styles.taskTitle} numberOfLines={2}>
                {m.summary || '(Untitled meeting)'}
              </Text>
              <Text style={styles.taskMeta} numberOfLines={1}>
                {startText} · {m.provider || 'calendar'}
              </Text>
              {openLink ? (
                <TouchableOpacity onPress={() => Linking.openURL(openLink)} style={styles.linkBtn}>
                  <Text style={styles.linkBtnText}>Open meeting link</Text>
                </TouchableOpacity>
              ) : (
                <Text style={styles.noMeetingLink}>No meeting link saved</Text>
              )}
            </View>
          );
        })
      )}
    </View>
  );
}

function MetaChip({label, value}) {
  return (
    <View style={styles.metaChip}>
      <Text style={styles.metaChipLabel}>{label}</Text>
      <Text style={styles.metaChipValue} numberOfLines={1}>
        {value}
      </Text>
    </View>
  );
}

function ContextLine({label, text}) {
  const t = (text || '').trim();
  if (!t) return null;
  return (
    <View style={styles.ctxLine}>
      <Text style={styles.ctxLabel}>{label}</Text>
      <Text style={styles.ctxText}>{t}</Text>
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
  refreshBtn: {
    paddingVertical: 8,
    paddingHorizontal: 10,
  },
  refreshBtnText: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.secondary[600],
  },
  scroll: {flex: 1},
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
  loadingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingVertical: 12,
  },
  loadingText: {
    fontSize: 13,
    color: colors.primary[900] + '80',
    fontWeight: '600',
  },
  empty: {
    fontSize: 13,
    color: colors.primary[900] + '70',
    textAlign: 'center',
    paddingVertical: 16,
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'stretch',
  },
  tileOuter: {
    borderWidth: 1,
    borderColor: colors.dark[500] + '14',
    borderRadius: 14,
    backgroundColor: colors.primary[50],
    paddingHorizontal: 14,
    paddingVertical: 14,
    minHeight: 148,
    ...Platform.select({
      web: {
        boxShadow: '0 2px 10px rgba(15, 23, 42, 0.06)',
      },
      default: {
        shadowColor: colors.primary[900],
        shadowOffset: {width: 0, height: 2},
        shadowOpacity: 0.06,
        shadowRadius: 6,
        elevation: 2,
      },
    }),
  },
  tileHeader: {
    minHeight: 44,
    justifyContent: 'flex-start',
  },
  tileName: {
    fontSize: 15,
    fontWeight: '800',
    color: colors.primary[900],
    lineHeight: 20,
  },
  tileClient: {
    marginTop: 6,
    fontSize: 12,
    fontWeight: '600',
    color: colors.secondary[700],
  },
  tileMetaRow: {
    marginTop: 10,
    gap: 4,
  },
  tileMetaLine: {
    fontSize: 11,
    fontWeight: '600',
    color: colors.primary[900] + '72',
  },
  tileFooter: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginTop: 12,
  },
  tileBadge: {
    fontSize: 11,
    fontWeight: '700',
    color: colors.secondary[700],
    backgroundColor: colors.secondary[500] + '18',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 999,
    overflow: 'hidden',
  },
  tileHint: {
    marginTop: 10,
    fontSize: 11,
    fontWeight: '700',
    color: colors.secondary[600],
  },
  modalRoot: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 16,
  },
  modalBackdrop: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: colors.primary[900] + '55',
  },
  modalCardWrap: {
    width: '100%',
    maxWidth: 560,
    maxHeight: '88%',
    zIndex: 1,
  },
  modalCard: {
    ...commonStyles.glassEffectStrong,
    borderRadius: 16,
    overflow: 'hidden',
    maxHeight: '100%',
  },
  modalHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingTop: 16,
    paddingBottom: 10,
    borderBottomWidth: 1,
    borderBottomColor: colors.dark[500] + '10',
    backgroundColor: colors.primary[100] + '80',
  },
  modalHeaderText: {
    flex: 1,
    paddingRight: 10,
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: '800',
    color: colors.primary[900],
  },
  modalSubtitle: {
    marginTop: 4,
    fontSize: 13,
    fontWeight: '600',
    color: colors.secondary[700],
  },
  modalCloseBtn: {
    padding: 6,
    borderRadius: 10,
    backgroundColor: colors.primary[50],
    borderWidth: 1,
    borderColor: colors.dark[500] + '12',
  },
  modalCloseText: {
    fontSize: 16,
    fontWeight: '700',
    color: colors.primary[900],
    lineHeight: 18,
  },
  modalScroll: {
    maxHeight: 520,
  },
  modalScrollContent: {
    paddingBottom: 20,
  },
  badgeRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: colors.dark[500] + '08',
  },
  metaChip: {
    backgroundColor: colors.primary[100],
    borderRadius: 10,
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderWidth: 1,
    borderColor: colors.dark[500] + '10',
    minWidth: '28%',
    flexGrow: 1,
  },
  metaChipLabel: {
    fontSize: 10,
    fontWeight: '700',
    color: colors.primary[900] + '55',
    textTransform: 'uppercase',
    letterSpacing: 0.4,
  },
  metaChipValue: {
    marginTop: 2,
    fontSize: 12,
    fontWeight: '700',
    color: colors.primary[900],
  },
  projectBody: {
    paddingHorizontal: 14,
    paddingBottom: 14,
    paddingTop: 10,
  },
  block: {
    marginBottom: 12,
  },
  blockTitle: {
    fontSize: 11,
    fontWeight: '800',
    color: colors.primary[900] + '55',
    textTransform: 'uppercase',
    marginBottom: 4,
  },
  blockBody: {
    fontSize: 13,
    lineHeight: 19,
    color: colors.primary[900],
    fontWeight: '500',
  },
  contextBox: {
    backgroundColor: colors.secondary[500] + '0c',
    borderRadius: 12,
    padding: 12,
    borderWidth: 1,
    borderColor: colors.secondary[500] + '22',
    marginBottom: 12,
  },
  contextTitle: {
    fontSize: 14,
    fontWeight: '800',
    color: colors.primary[900],
    marginBottom: 8,
  },
  ctxLine: {
    marginBottom: 8,
  },
  ctxLabel: {
    fontSize: 11,
    fontWeight: '800',
    color: colors.secondary[700],
    marginBottom: 2,
  },
  ctxText: {
    fontSize: 13,
    lineHeight: 18,
    color: colors.primary[900],
    fontWeight: '500',
  },
  contextFooter: {
    marginTop: 4,
    fontSize: 11,
    fontWeight: '600',
    color: colors.primary[900] + '65',
  },
  noContext: {
    fontSize: 12,
    fontStyle: 'italic',
    color: colors.primary[900] + '60',
    marginBottom: 12,
  },
  tasksHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  tasksTitle: {
    fontSize: 14,
    fontWeight: '800',
    color: colors.primary[900],
  },
  tasksCount: {
    fontSize: 12,
    fontWeight: '800',
    color: colors.secondary[600],
  },
  noTasks: {
    fontSize: 12,
    color: colors.primary[900] + '55',
  },
  taskRow: {
    backgroundColor: colors.accent[500] + '10',
    borderWidth: 1,
    borderColor: colors.accent[500] + '18',
    borderRadius: 10,
    paddingVertical: 10,
    paddingHorizontal: 10,
    marginBottom: 8,
  },
  taskTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.primary[900],
  },
  taskMeta: {
    marginTop: 4,
    fontSize: 11,
    fontWeight: '600',
    color: colors.primary[900] + '70',
  },
  linkBtn: {
    marginTop: 7,
    alignSelf: 'flex-start',
  },
  linkBtnText: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.secondary[700],
  },
  noMeetingLink: {
    marginTop: 7,
    fontSize: 11,
    fontStyle: 'italic',
    color: colors.primary[900] + '65',
  },
});
