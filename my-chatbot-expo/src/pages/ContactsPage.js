import React, {useEffect, useState, useCallback, useRef} from 'react';
import {View, Text, StyleSheet, TextInput, TouchableOpacity, ScrollView, Platform} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {colors} from '../styles/colors';
import {commonStyles} from '../styles/commonStyles';
import {API_BASE_URL} from '../config/api';
import {useRoute} from '@react-navigation/native';
import EditContactModal from '../components/EditContactModal';
import { Svg, Path } from 'react-native-svg';

export default function ContactsPage() {
  const route = useRoute();
  const {userId} = route.params || {};
  const [contacts, setContacts] = useState([]);
  const [filter, setFilter] = useState('');
  const [loading, setLoading] = useState(false);
  const [working, setWorking] = useState(false);
  const [groups, setGroups] = useState([]);
  const [activeGroup, setActiveGroup] = useState(null);
  const [editOpen, setEditOpen] = useState(false);
  const [editContact, setEditContact] = useState(null);
  const didForceSyncRef = useRef(false);

  const loadContacts = useCallback(async () => {
    if (!userId) return;
    setLoading(true);
    try {
      const r = await fetch(`${API_BASE_URL}/api/contacts/list`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId}),
      });
      const data = await r.json();
      const have = (data?.contacts || []).length > 0;
      if (data?.success && have) {
        setContacts(data.contacts || []);
        // If contacts exist, trigger one-time background forced sync to ensure normalization/grouping, then refresh
        if (!didForceSyncRef.current) {
          didForceSyncRef.current = true;
          try {
            await fetch(`${API_BASE_URL}/api/contacts/sync`, {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({user_id: userId, force: true}),
            });
            // Reload list and groups after background sync
            const r3 = await fetch(`${API_BASE_URL}/api/contacts/list`, {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({user_id: userId}),
            });
            const d3 = await r3.json();
            if (d3?.success) {
              setContacts(d3.contacts || []);
            }
            await loadGroups();
          } catch {}
        }
      } else {
        // If nothing yet, trigger initial sync (idempotent) then reload
        try {
          await fetch(`${API_BASE_URL}/api/contacts/sync`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({user_id: userId}),
          });
          const r2 = await fetch(`${API_BASE_URL}/api/contacts/list`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({user_id: userId}),
          });
          const d2 = await r2.json();
          setContacts(d2?.contacts || []);
        } catch {
          setContacts([]);
        }
      }
    } catch {
      setContacts([]);
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    loadContacts();
  }, [loadContacts]);

  const loadGroups = useCallback(async () => {
    if (!userId) return;
    try {
      const r = await fetch(`${API_BASE_URL}/api/contacts/groups`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId}),
      });
      const data = await r.json();
      if (data?.success) setGroups(data.groups || []);
    } catch {}
  }, [userId]);

  useEffect(() => {
    loadGroups();
  }, [loadGroups, contacts.length]);

  const ALL_KEY = '__all__';
  const UNGROUPED_KEY = 'ungrouped';

  const formatGroupLabel = useCallback((key) => {
    if (!key) return '';
    const k = key.toLowerCase();
    if (k === UNGROUPED_KEY) return 'Ungrouped';
    const upper = ['hr','it','ceo','cfo','cto','coo'];
    if (upper.includes(k)) return k.toUpperCase();
    return k.split(/\s+/).filter(Boolean).map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
  }, []);

  // Build group names (normalized lower-case keys) and counts from contacts (fallback if /groups not available)
  const groupCounts = React.useMemo(() => {
    const counts = {};
    for (const c of contacts) {
      const arr = Array.isArray(c?.groups) ? c.groups : [];
      if (!arr.length) {
        counts[UNGROUPED_KEY] = (counts[UNGROUPED_KEY] || 0) + 1;
      } else {
        for (const g of arr) {
          const norm = (g || '').trim().toLowerCase();
          if (!norm) continue;
          counts[norm] = (counts[norm] || 0) + 1;
        }
      }
    }
    return counts;
  }, [contacts]);

  const allGroupNames = React.useMemo(() => {
    const names = Object.keys(groupCounts); // already normalized (lower-case)
    // prefer server-provided groups ordering if available
    const server = (groups && groups.length ? groups : []).map(g => (g || '').toLowerCase()).filter(Boolean);
    const merged = [...new Set([UNGROUPED_KEY, ...server, ...names])].filter(Boolean);
    return merged;
  }, [groupCounts, groups]);

  // Determine which groups to display as "folders" (either all or a chosen one)
  const displayGroups = React.useMemo(() => {
    if (!activeGroup) return [ALL_KEY];
    return allGroupNames.filter((g) => g.toLowerCase() === activeGroup.toLowerCase());
  }, [activeGroup, allGroupNames]);

  // Helper to get contacts for a specific group, with text filter applied
  const contactsForGroup = useCallback((groupName) => {
    const q = filter.trim().toLowerCase();
    const filtered = contacts.filter((c) => {
      const textOk =
        !q ||
        (c.name || '').toLowerCase().includes(q) ||
        (c.email || '').toLowerCase().includes(q) ||
        (c.nickname || '').toLowerCase().includes(q);
      if (!textOk) return false;
      if (groupName === ALL_KEY) return true; // no group filter in All view
      const gs = Array.isArray(c?.groups) ? c.groups : [];
      if (groupName === UNGROUPED_KEY) {
        return gs.length === 0;
      }
      return gs.some((g) => (g || '').toLowerCase() === groupName.toLowerCase());
    });
    if (groupName === ALL_KEY) {
      // de-duplicate by email so one instance per contact
      const seen = new Set();
      return filtered.filter(c => {
        const key = (c.email || '').toLowerCase();
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      });
    }
    return filtered;
  }, [contacts, filter]);

  const fixNames = async () => {
    if (!userId) return;
    setWorking(true);
    try {
      await fetch(`${API_BASE_URL}/api/contacts/normalize-names`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId}),
      });
      await loadContacts();
    } catch {}
    setWorking(false);
  };

  const archiveContact = async (email) => {
    setContacts((prev) => prev.filter((c) => c.email !== email)); // optimistic remove
    try {
      await fetch(`${API_BASE_URL}/api/contacts/archive`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId, email, archived: true}),
      });
    } catch {
      // revert on failure
      await loadContacts();
    }
  };

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      <View style={styles.header}>
        <Text style={styles.title}>Contacts</Text>
        <Text style={styles.subtitle}>Last 100 Sent recipients</Text>
      </View>
      <View style={styles.controls}>
        <TextInput
          value={filter}
          onChangeText={setFilter}
          placeholder="Search name or email"
          placeholderTextColor={colors.primary[900] + '60'}
          style={styles.input}
        />
        <TouchableOpacity onPress={loadContacts} style={styles.reloadBtn}>
          <Text style={styles.reloadText}>{loading ? 'Loading…' : 'Reload'}</Text>
        </TouchableOpacity>
        <TouchableOpacity onPress={fixNames} style={styles.reloadBtn} disabled={working}>
          <Text style={styles.reloadText}>{working ? 'Fixing…' : 'Fix names'}</Text>
        </TouchableOpacity>
      </View>
      <ScrollView style={styles.list} showsVerticalScrollIndicator={false}>
        {/* Folder-style group selector */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{gap: 8, paddingBottom: 8}}>
          <TouchableOpacity
            onPress={() => setActiveGroup(null)}
            style={[styles.folderChip, !activeGroup && styles.folderChipActive]}>
            <Svg width="16" height="16" viewBox="0 0 24 24" fill={ !activeGroup ? colors.primary[50] : colors.primary[700] }>
              <Path d="M10 4H4c-1.1 0-2 .9-2 2v10a2 2 0 0 0 2 2h16V8h-8l-2-4z"/>
            </Svg>
            <Text style={[styles.folderChipText, !activeGroup && styles.folderChipTextActive]}>All</Text>
          </TouchableOpacity>
          {allGroupNames.map((g) => (
            <TouchableOpacity
              key={g}
              onPress={() => { setActiveGroup(g); }}
              style={[styles.folderChip, activeGroup && activeGroup.toLowerCase() === g.toLowerCase() && styles.folderChipActive]}>
              <Svg width="16" height="16" viewBox="0 0 24 24" fill={ activeGroup && activeGroup.toLowerCase() === g.toLowerCase() ? colors.primary[50] : colors.primary[700] }>
                <Path d="M10 4H4c-1.1 0-2 .9-2 2v10a2 2 0 0 0 2 2h16V8h-8l-2-4z"/>
              </Svg>
              <Text style={[styles.folderChipText, activeGroup && activeGroup.toLowerCase() === g.toLowerCase() && styles.folderChipTextActive]}>
                {formatGroupLabel(g)} {!!groupCounts[g] && `(${groupCounts[g]})`}
              </Text>
            </TouchableOpacity>
          ))}
        </ScrollView>

        {/* Sectioned contacts by group (folders) */}
        {displayGroups.map((gname) => {
          const items = contactsForGroup(gname);
          if (!items.length) return null;
          return (
            <View key={`section-${gname}`} style={styles.section}>
              <View style={styles.sectionHeader}>
                <Svg width="18" height="18" viewBox="0 0 24 24" fill={colors.primary[700]}>
                  <Path d="M10 4H4c-1.1 0-2 .9-2 2v10a2 2 0 0 0 2 2h16V8h-8l-2-4z"/>
                </Svg>
                <Text style={styles.sectionTitle}>{gname === ALL_KEY ? 'All' : formatGroupLabel(gname)}</Text>
                <View style={styles.countPill}>
                  <Text style={styles.countPillText}>{items.length}</Text>
                </View>
              </View>
              {items.map((c, idx) => (
                <View key={c.email || idx} style={styles.item}>
                  <View style={styles.avatar}>
                    <Text style={styles.avatarText}>{(c.name || c.email || 'C').charAt(0).toUpperCase()}</Text>
                  </View>
                  <View style={styles.meta}>
                    <Text style={styles.name} numberOfLines={1}>{c.name || '(No name)'}</Text>
                    <Text style={styles.email} numberOfLines={1}>{c.email}</Text>
                    {!!c.nickname && <Text style={styles.nick} numberOfLines={1}>“{c.nickname}”</Text>}
                    <View style={styles.groupRow}>
                      {Array.from(new Set(((c.groups || []).map(gg => (gg || '').toLowerCase()))))
                        .filter(Boolean)
                        .map((gg, i) => (
                          <View key={`${c.email}-${gg}-${i}`} style={styles.groupPill}>
                            <Text style={styles.groupPillText}>{formatGroupLabel(gg)}</Text>
                          </View>
                        ))
                      }
                    </View>
                  </View>
                  <View style={styles.itemActions}>
                    <View style={styles.badge}>
                      <Text style={styles.badgeText}>{c.count || 1}</Text>
                    </View>
                    <TouchableOpacity onPress={() => { setEditContact(c); setEditOpen(true); }} style={styles.editBtn}>
                      <Text style={styles.editText}>Edit</Text>
                    </TouchableOpacity>
                    <TouchableOpacity onPress={() => archiveContact(c.email)} style={styles.archiveBtn}>
                      <Text style={styles.archiveText}>Archive</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              ))}
            </View>
          );
        })}

        {displayGroups.every((g) => contactsForGroup(g).length === 0) && (
          <Text style={styles.empty}>{loading ? 'Loading…' : 'No contacts found.'}</Text>
        )}
      </ScrollView>
      <EditContactModal
        visible={editOpen}
        onClose={(saved, updated) => {
          setEditOpen(false);
          if (saved && updated) {
            // merge updated contact into list
            setContacts((prev) => prev.map((x) => (x.email === updated.email ? {...x, ...updated} : x)));
            loadGroups();
          }
        }}
        userId={userId}
        contact={editContact}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.primary[50], padding: 12 },
  header: { marginBottom: 8 },
  title: { fontSize: 20, fontWeight: '700', color: colors.primary[900] },
  subtitle: { fontSize: 12, color: colors.primary[900] + '80' },
  controls: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 8,
  },
  input: {
    flex: 1,
    backgroundColor: colors.primary[200] + '30',
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
    color: colors.primary[900],
    borderWidth: 1,
    borderColor: colors.dark[500] + '10',
  },
  reloadBtn: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 8,
    backgroundColor: colors.dark[500] + '10',
  },
  reloadText: { color: colors.primary[900], fontSize: 12 },
  list: { flex: 1 },
  section: { marginBottom: 12 },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 },
  sectionTitle: { fontSize: 14, fontWeight: '700', color: colors.primary[900], flex: 0 },
  countPill: { marginLeft: 'auto', paddingHorizontal: 8, paddingVertical: 2, borderRadius: 8, backgroundColor: colors.primary[200] + '40' },
  countPillText: { fontSize: 11, color: colors.primary[900] + '80' },
  item: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    padding: 10,
    marginBottom: 8,
    borderRadius: 10,
    backgroundColor: colors.primary[200] + '20',
    borderWidth: 1,
    borderColor: colors.dark[500] + '10',
  },
  avatar: {
    width: 36, height: 36, borderRadius: 18,
    alignItems: 'center', justifyContent: 'center',
    backgroundColor: colors.secondary[500],
  },
  avatarText: { color: '#fff', fontWeight: '700' },
  meta: { flex: 1, minWidth: 0 },
  name: { fontSize: 14, fontWeight: '600', color: colors.primary[900] },
  email: { fontSize: 12, color: colors.primary[900] + '70' },
  nick: { fontSize: 12, color: colors.secondary[700] },
  groupRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 4 },
  groupPill: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 999,
    backgroundColor: colors.primary[200] + '30',
    borderWidth: 1,
    borderColor: colors.dark[500] + '10',
  },
  groupPillText: { fontSize: 10, color: colors.primary[900] + '90' },
  badge: {
    minWidth: 28, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 8,
    backgroundColor: colors.secondary[500] + '25',
  },
  badgeText: { textAlign: 'center', color: colors.secondary[700], fontWeight: '600' },
  itemActions: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  editBtn: {
    paddingHorizontal: 8,
    paddingVertical: 6,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.dark[500] + '20',
    backgroundColor: colors.primary[200] + '30',
  },
  editText: { color: colors.primary[900], fontSize: 12, fontWeight: '500' },
  archiveBtn: {
    paddingHorizontal: 8,
    paddingVertical: 6,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.dark[500] + '20',
    backgroundColor: colors.primary[200] + '30',
  },
  archiveText: { color: colors.primary[900], fontSize: 12, fontWeight: '500' },
  empty: { textAlign: 'center', color: colors.primary[900] + '70', marginTop: 16, fontSize: 12 },
  groupChip: {
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 999,
    backgroundColor: colors.primary[200] + '30',
    borderWidth: 1,
    borderColor: colors.dark[500] + '10',
  },
  groupChipActive: {
    backgroundColor: colors.secondary[500] + '30',
    borderColor: colors.secondary[600] + '50',
  },
  groupChipText: { fontSize: 12, color: colors.primary[900] + '90' },
  groupChipTextActive: { color: colors.secondary[700], fontWeight: '600' },
  folderChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 12,
    backgroundColor: colors.primary[200] + '30',
    borderWidth: 1,
    borderColor: colors.dark[500] + '10',
  },
  folderChipActive: {
    backgroundColor: colors.secondary[500] + '30',
    borderColor: colors.secondary[600] + '50',
  },
  folderChipText: { fontSize: 12, color: colors.primary[900] + '90', fontWeight: '600' },
  folderChipTextActive: { color: colors.primary[50] },
});


