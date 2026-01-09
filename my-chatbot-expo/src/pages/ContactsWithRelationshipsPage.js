import React, {useEffect, useState} from 'react';
import {View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {colors} from '../styles/colors';
import {API_BASE_URL} from '../config/api';
import {useRoute, useNavigation} from '@react-navigation/native';
import {Svg, Path} from 'react-native-svg';

export default function ContactsWithRelationshipsPage() {
  const route = useRoute();
  const navigation = useNavigation();
  const {userId} = route.params || {};
  const [contacts, setContacts] = useState([]);
  const [projectContactRelationships, setProjectContactRelationships] = useState([]);
  const [loading, setLoading] = useState(true);

  const loadContactsWithRelationships = async () => {
    if (!userId) return;
    setLoading(true);
    try {
      const r = await fetch(`${API_BASE_URL}/api/contacts/with-relationships`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId}),
      });
      const data = await r.json();
      console.log('[ContactsWithRelationships] API Response:', {
        success: data?.success,
        relationshipsCount: data?.relationships_count,
        relationships: data?.project_contact_relationships?.length || 0,
        fullData: data
      });
      if (data?.success) {
        setContacts(data.contacts || []);
        const relationships = data.project_contact_relationships || [];
        console.log('[ContactsWithRelationships] Setting relationships:', relationships);
        setProjectContactRelationships(relationships);
      } else {
        setContacts([]);
        setProjectContactRelationships([]);
      }
    } catch (error) {
      console.error('Failed to load contacts:', error);
      setContacts([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadContactsWithRelationships();
  }, [userId]);

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      <View style={styles.header}>
        <TouchableOpacity
          onPress={() => navigation.goBack()}
          style={styles.backButton}>
          <Svg width="24" height="24" viewBox="0 0 24 24" fill={colors.primary[900]}>
            <Path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z"/>
          </Svg>
        </TouchableOpacity>
        <View style={styles.headerTextContainer}>
          <Text style={styles.title}>Contacts & Relationships</Text>
          <View style={styles.subtitleContainer}>
            <Text style={styles.subtitle}>Projects, Notes & Descriptions</Text>
            {projectContactRelationships.length > 0 && (
              <Text style={styles.countText}>
                {' '}(new: {projectContactRelationships.length})
              </Text>
            )}
          </View>
        </View>
        <View style={{width: 40}} />
      </View>

      {loading ? (
        <View style={styles.centerContainer}>
          <ActivityIndicator size="large" color={colors.primary[900]} />
          <Text style={styles.loadingText}>Loading relationships...</Text>
        </View>
      ) : (
        <ScrollView style={styles.list} showsVerticalScrollIndicator={false}>
          {/* Project-Contact Relationships Section */}
          {projectContactRelationships.length > 0 ? (
            <View style={styles.relationshipsSection}>
              <View style={styles.sectionHeader}>
                <Text style={styles.sectionTitle}>Project-Contact Relationships</Text>
                <View style={styles.countPill}>
                  <Text style={styles.countPillText}>{projectContactRelationships.length}</Text>
                </View>
              </View>
              {projectContactRelationships.map((rel, relIdx) => (
                <View key={relIdx} style={styles.relationshipCard}>
                  <View style={styles.relationshipHeader}>
                    <View style={styles.relationshipInfo}>
                      <Text style={styles.relationshipProject}>{rel.project}</Text>
                      <Text style={styles.relationshipContact}>{rel.contact_email}</Text>
                    </View>
                  </View>
                  {rel.description && (
                    <View style={styles.relationshipDescription}>
                      <Text style={styles.relationshipDescriptionText}>{rel.description}</Text>
                    </View>
                  )}
                  {rel.notes && rel.notes.length > 0 && (
                    <View style={styles.relationshipNotes}>
                      {rel.notes.map((note, nIdx) => (
                        <Text key={nIdx} style={styles.relationshipNoteText}>• {note}</Text>
                      ))}
                    </View>
                  )}
                  {rel.sources && rel.sources.length > 0 && (
                    <View style={styles.tagsContainer}>
                      {rel.sources.map((source, sIdx) => (
                        <View key={sIdx} style={[styles.tag, styles.sourceTag]}>
                          <Text style={styles.tagText}>{source}</Text>
                        </View>
                      ))}
                    </View>
                  )}
                </View>
              ))}
            </View>
          ) : (
            <View style={styles.centerContainer}>
              <Text style={styles.emptyText}>No project-contact relationships found.</Text>
              <TouchableOpacity
                onPress={loadContactsWithRelationships}
                style={styles.reloadButton}>
                <Text style={styles.reloadButtonText}>Reload</Text>
              </TouchableOpacity>
            </View>
          )}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.primary[50],
    padding: 12,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 16,
  },
  backButton: {
    padding: 4,
  },
  headerTextContainer: {
    flex: 1,
    alignItems: 'center',
  },
  title: {
    fontSize: 20,
    fontWeight: '700',
    color: colors.primary[900],
  },
  subtitleContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 2,
  },
  subtitle: {
    fontSize: 12,
    color: colors.primary[900] + '80',
  },
  countText: {
    fontSize: 12,
    color: colors.secondary[600],
    fontWeight: '600',
  },
  list: {
    flex: 1,
  },
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: 40,
  },
  loadingText: {
    marginTop: 12,
    fontSize: 14,
    color: colors.primary[900] + '80',
  },
  emptyText: {
    fontSize: 14,
    color: colors.primary[900] + '70',
    marginBottom: 16,
  },
  reloadButton: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 8,
    backgroundColor: colors.primary[900],
  },
  reloadButtonText: {
    color: colors.primary[50],
    fontSize: 14,
    fontWeight: '600',
  },
  contactCard: {
    backgroundColor: colors.primary[200] + '20',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: colors.dark[500] + '10',
  },
  contactHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 16,
  },
  avatar: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: colors.secondary[500],
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 12,
  },
  avatarText: {
    color: '#fff',
    fontSize: 20,
    fontWeight: '700',
  },
  contactInfo: {
    flex: 1,
  },
  contactName: {
    fontSize: 18,
    fontWeight: '700',
    color: colors.primary[900],
    marginBottom: 4,
  },
  contactEmail: {
    fontSize: 14,
    color: colors.primary[900] + '80',
    marginBottom: 2,
  },
  contactCount: {
    fontSize: 12,
    color: colors.primary[900] + '60',
  },
  section: {
    marginBottom: 16,
  },
  sectionLabel: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.primary[900],
    marginBottom: 8,
  },
  descriptionText: {
    fontSize: 14,
    color: colors.primary[900] + '90',
    lineHeight: 20,
  },
  tagsContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  tag: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 16,
    backgroundColor: colors.secondary[500] + '30',
    borderWidth: 1,
    borderColor: colors.secondary[600] + '50',
  },
  groupTag: {
    backgroundColor: colors.primary[200] + '40',
    borderColor: colors.primary[300] + '60',
  },
  sourceTag: {
    backgroundColor: colors.accent[500] + '30',
    borderColor: colors.accent[600] + '50',
  },
  tagText: {
    fontSize: 12,
    color: colors.primary[900] + '90',
    fontWeight: '500',
  },
  noteItem: {
    marginBottom: 6,
  },
  noteText: {
    fontSize: 14,
    color: colors.primary[900] + '80',
    lineHeight: 20,
  },
  noDataText: {
    fontSize: 12,
    color: colors.primary[900] + '60',
    fontStyle: 'italic',
    textAlign: 'center',
    paddingVertical: 8,
  },
  relationshipsSection: {
    marginTop: 0,
    marginBottom: 24,
  },
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 16,
    paddingHorizontal: 4,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: colors.primary[900],
  },
  countPill: {
    backgroundColor: colors.secondary[500],
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 12,
    minWidth: 40,
    alignItems: 'center',
  },
  countPillText: {
    color: '#fff',
    fontSize: 12,
    fontWeight: '700',
  },
  relationshipCard: {
    backgroundColor: colors.primary[200] + '20',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: colors.secondary[500] + '30',
  },
  relationshipHeader: {
    marginBottom: 12,
  },
  relationshipInfo: {
    flexDirection: 'column',
  },
  relationshipProject: {
    fontSize: 16,
    fontWeight: '700',
    color: colors.secondary[600],
    marginBottom: 4,
  },
  relationshipContact: {
    fontSize: 14,
    color: colors.primary[900] + '80',
  },
  relationshipDescription: {
    marginBottom: 12,
  },
  relationshipDescriptionText: {
    fontSize: 14,
    color: colors.primary[900] + '90',
    lineHeight: 20,
  },
  relationshipNotes: {
    marginBottom: 12,
  },
  relationshipNoteText: {
    fontSize: 13,
    color: colors.primary[900] + '80',
    lineHeight: 18,
    marginBottom: 4,
  },
});

