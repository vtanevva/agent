import React, {useState, useEffect} from 'react';
import {Modal, View, Text, TextInput, TouchableOpacity, StyleSheet, Platform, KeyboardAvoidingView} from 'react-native';
import {LinearGradient} from 'expo-linear-gradient';
import {colors} from '../styles/colors';
import {commonStyles} from '../styles/commonStyles';
import {API_BASE_URL} from '../config/api';

export default function EditContactModal({visible, onClose, userId, contact}) {
  const [name, setName] = useState(contact?.name || '');
  const [nickname, setNickname] = useState(contact?.nickname || '');
  const [groups, setGroups] = useState((contact?.groups || []).join(', '));
  const [saving, setSaving] = useState(false);
  const email = contact?.email || '';

  useEffect(() => {
    if (!visible) return;
    setName(contact?.name || '');
    setNickname(contact?.nickname || '');
    setGroups((contact?.groups || []).join(', '));
    setSaving(false);
  }, [visible, contact]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const parsedGroups = groups
        .split(',')
        .map((g) => g.trim())
        .filter((g) => g.length > 0);
      const r = await fetch(`${API_BASE_URL}/api/contacts/update`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId, email, name, nickname, groups: parsedGroups}),
      });
      const data = await r.json();
      if (data?.success) {
        onClose(true, data.contact);
      } else {
        onClose(false);
      }
    } catch {
      onClose(false);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={() => onClose(false)}>
      <View style={styles.overlay}>
        <KeyboardAvoidingView
          style={{width: '100%'}}
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
          keyboardVerticalOffset={Platform.select({ios: 12, android: 24, default: 0})}
        >
          <View style={styles.container}>
            <View style={styles.headerRow}>
              <Text style={styles.headerTitle}>Edit Contact</Text>
              <TouchableOpacity onPress={() => onClose(false)} style={styles.iconBtn}>
                <Text style={styles.iconBtnText}>✕</Text>
              </TouchableOpacity>
            </View>
            <Text style={styles.email}>{email}</Text>
            <View style={styles.field}>
              <Text style={styles.label}>Name</Text>
              <TextInput value={name} onChangeText={setName} style={styles.input} placeholder="(optional)" placeholderTextColor={colors.primary[900] + '60'} />
            </View>
            <View style={styles.field}>
              <Text style={styles.label}>Nickname</Text>
              <TextInput value={nickname} onChangeText={setNickname} style={styles.input} placeholder="e.g., Dee" placeholderTextColor={colors.primary[900] + '60'} />
            </View>
            <View style={styles.field}>
              <Text style={styles.label}>Groups (comma separated)</Text>
              <TextInput value={groups} onChangeText={setGroups} style={styles.input} placeholder="friends, clients" placeholderTextColor={colors.primary[900] + '60'} />
            </View>
            <View style={styles.actions}>
              <TouchableOpacity onPress={() => onClose(false)} style={styles.cancelButton}>
                <Text style={styles.cancelText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity disabled={saving} onPress={handleSave} style={styles.saveWrapper}>
                <LinearGradient colors={[colors.accent[500], colors.accent[600]]} style={styles.saveButton}>
                  <Text style={styles.saveText}>{saving ? 'Saving…' : 'Save'}</Text>
                </LinearGradient>
              </TouchableOpacity>
            </View>
          </View>
        </KeyboardAvoidingView>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', alignItems: 'center', justifyContent: 'center', padding: 16 },
  container: { width: '100%', maxWidth: 620, backgroundColor: '#fff', borderRadius: 16, padding: 14, ...commonStyles.shadowLg },
  headerRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 },
  headerTitle: { fontSize: 16, fontWeight: '700', color: colors.primary[900] },
  iconBtn: { width: 28, height: 28, borderRadius: 14, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primary[200] + '40' },
  iconBtnText: { color: colors.primary[900], fontSize: 14, lineHeight: 14 },
  email: { fontSize: 12, color: colors.primary[900] + '80', marginBottom: 8 },
  field: { marginBottom: 8 },
  label: { fontSize: 12, color: colors.primary[900] + '80', marginBottom: 4 },
  input: { backgroundColor: colors.primary[200] + '30', borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, color: colors.primary[900], borderWidth: 1, borderColor: colors.dark[500] + '10' },
  actions: { marginTop: 12, flexDirection: 'row', justifyContent: 'flex-end', gap: 8 },
  cancelButton: { paddingVertical: 10, paddingHorizontal: 14, borderRadius: 10, backgroundColor: colors.dark[500] + '20' },
  cancelText: { color: colors.dark[600], fontWeight: '500' },
  saveWrapper: { borderRadius: 10, overflow: 'hidden' },
  saveButton: { paddingVertical: 10, paddingHorizontal: 16 },
  saveText: { color: '#fff', fontWeight: '600' },
});


