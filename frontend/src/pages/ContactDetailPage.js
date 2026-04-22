import React, {useEffect, useState, useCallback} from 'react';
import {View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {useRoute, useNavigation} from '@react-navigation/native';
import {colors} from '../styles/colors';
import {commonStyles} from '../styles/commonStyles';
import {API_BASE_URL} from '../config/api';
import {Svg, Path} from 'react-native-svg';
import EditContactModal from '../components/EditContactModal';

export default function ContactDetailPage() {
  const route = useRoute();
  const navigation = useNavigation();
  const {userId, contact} = route.params || {};
  
  const [contactData, setContactData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('info'); // 'info' or 'notes'
  const [pastConversations, setPastConversations] = useState([]);
  const [loadingConversations, setLoadingConversations] = useState(false);
  const [editOpen, setEditOpen] = useState(false);

  const loadContactDetail = useCallback(async () => {
    if (!userId || !contact?.email) return;
    
    setLoading(true);
    try {
      const r = await fetch(`${API_BASE_URL}/api/contacts/detail`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId, email: contact.email}),
      });
      const data = await r.json();
      if (data?.success) {
        setContactData(data);
        if (data.past_conversations) {
          setPastConversations(data.past_conversations);
        }
      }
    } catch (e) {
      console.error('Error loading contact detail:', e);
    } finally {
      setLoading(false);
    }
  }, [userId, contact]);

  const loadConversations = useCallback(async () => {
    if (!userId || !contact?.email) return;
    
    setLoadingConversations(true);
    try {
      const r = await fetch(`${API_BASE_URL}/api/contacts/conversations`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId, email: contact.email, limit: 50}),
      });
      const data = await r.json();
      if (data?.success) {
        setPastConversations(data.conversations || []);
      }
    } catch (e) {
      console.error('Error loading conversations:', e);
    } finally {
      setLoadingConversations(false);
    }
  }, [userId, contact]);

  useEffect(() => {
    loadContactDetail();
  }, [loadContactDetail]);

  useEffect(() => {
    if (activeTab === 'notes') {
      loadConversations();
    }
  }, [activeTab, loadConversations]);

  if (loading) {
    return (
      <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={colors.secondary[500]} />
          <Text style={styles.loadingText}>Loading contact details...</Text>
        </View>
      </SafeAreaView>
    );
  }

  const contactInfo = contactData?.contact || contact;
  const lastInteraction = contactData?.last_interaction;
  const generalNotes = contactData?.general_notes || '';

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}>
          <Svg width="24" height="24" viewBox="0 0 24 24" fill={colors.primary[900]}>
            <Path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z"/>
          </Svg>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Contact Details</Text>
        <TouchableOpacity onPress={() => setEditOpen(true)} style={styles.editButton}>
          <Svg width="20" height="20" viewBox="0 0 24 24" fill={colors.secondary[600]}>
            <Path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/>
          </Svg>
          <Text style={styles.editButtonText}>Edit</Text>
        </TouchableOpacity>
      </View>

      {/* Contact Avatar and Basic Info */}
      <View style={styles.contactHeader}>
        <View style={styles.avatar}>
          <Text style={styles.avatarText}>
            {(contactInfo?.name || contactInfo?.email || 'C').charAt(0).toUpperCase()}
          </Text>
        </View>
        <Text style={styles.contactName}>{contactInfo?.name || '(No name)'}</Text>
        <Text style={styles.contactEmail}>{contactInfo?.email}</Text>
        {contactInfo?.nickname && (
          <Text style={styles.contactNickname}>"{contactInfo.nickname}"</Text>
        )}
      </View>

      {/* Tabs */}
      <View style={styles.tabs}>
        <TouchableOpacity
          onPress={() => setActiveTab('info')}
          style={[styles.tab, activeTab === 'info' && styles.tabActive]}>
          <Text style={[styles.tabText, activeTab === 'info' && styles.tabTextActive]}>
            Information
          </Text>
        </TouchableOpacity>
        <TouchableOpacity
          onPress={() => setActiveTab('notes')}
          style={[styles.tab, activeTab === 'notes' && styles.tabActive]}>
          <Text style={[styles.tabText, activeTab === 'notes' && styles.tabTextActive]}>
            Notes
          </Text>
        </TouchableOpacity>
      </View>

      {/* Content */}
      <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
        {activeTab === 'info' ? (
          <View style={styles.infoTab}>
            {/* Personal Information */}
            <View style={styles.section}>
              <Text style={styles.sectionTitle}>Personal Information</Text>
              <View style={styles.infoRow}>
                <Text style={styles.infoLabel}>Name:</Text>
                <Text style={styles.infoValue}>{contactInfo?.name || '(No name)'}</Text>
              </View>
              {contactInfo?.nickname && (
                <View style={styles.infoRow}>
                  <Text style={styles.infoLabel}>Nickname:</Text>
                  <Text style={styles.infoValue}>"{contactInfo.nickname}"</Text>
                </View>
              )}
              <View style={styles.infoRow}>
                <Text style={styles.infoLabel}>Email:</Text>
                <Text style={styles.infoValue}>{contactInfo?.email}</Text>
              </View>
              {contactInfo?.groups && contactInfo.groups.length > 0 && (
                <View style={styles.infoRow}>
                  <Text style={styles.infoLabel}>Groups:</Text>
                  <View style={styles.groupsContainer}>
                    {contactInfo.groups.map((group, idx) => (
                      <View key={idx} style={styles.groupPill}>
                        <Text style={styles.groupPillText}>{group}</Text>
                      </View>
                    ))}
                  </View>
                </View>
              )}
              {contactInfo?.count && (
                <View style={styles.infoRow}>
                  <Text style={styles.infoLabel}>Interactions:</Text>
                  <Text style={styles.infoValue}>{contactInfo.count}</Text>
                </View>
              )}
            </View>

            {/* Last Interaction */}
            {lastInteraction && (
              <View style={styles.section}>
                <Text style={styles.sectionTitle}>Last Interaction</Text>
                <View style={styles.interactionCard}>
                  <Text style={styles.interactionSubject}>{lastInteraction.subject}</Text>
                  <Text style={styles.interactionFrom}>From: {lastInteraction.from}</Text>
                  {lastInteraction.date && (
                    <Text style={styles.interactionDate}>{lastInteraction.date}</Text>
                  )}
                  {lastInteraction.snippet && (
                    <Text style={styles.interactionSnippet}>{lastInteraction.snippet}</Text>
                  )}
                </View>
              </View>
            )}
          </View>
        ) : (
          <View style={styles.notesTab}>
            {/* General Notes */}
            <View style={styles.section}>
              <Text style={styles.sectionTitle}>General Notes</Text>
              {generalNotes ? (
                <View style={styles.notesCard}>
                  <Text style={styles.notesText}>{generalNotes}</Text>
                </View>
              ) : (
                <View style={styles.emptyCard}>
                  <Text style={styles.emptyText}>No general notes available yet.</Text>
                  <Text style={styles.emptySubtext}>
                    Notes will be automatically generated from your conversations.
                  </Text>
                </View>
              )}
            </View>

            {/* Past Conversations */}
            <View style={styles.section}>
              <Text style={styles.sectionTitle}>Past Conversations</Text>
              {loadingConversations ? (
                <View style={styles.loadingContainer}>
                  <ActivityIndicator size="small" color={colors.secondary[500]} />
                </View>
              ) : pastConversations.length > 0 ? (
                pastConversations.map((conv, idx) => (
                  <View key={idx} style={styles.conversationCard}>
                    <View style={styles.conversationHeader}>
                      <Text style={styles.conversationDate}>
                        {conv.created_at ? new Date(conv.created_at).toLocaleDateString() : 'Unknown date'}
                      </Text>
                      <Text style={styles.conversationSession}>
                        Session: {conv.session_id?.slice(-8) || 'N/A'}
                      </Text>
                    </View>
                    {conv.message && (
                      <Text style={styles.conversationMessage} numberOfLines={3}>
                        {conv.message}
                      </Text>
                    )}
                    {conv.messages && conv.messages.length > 0 && (
                      <View style={styles.messagesList}>
                        {conv.messages.slice(0, 3).map((msg, msgIdx) => (
                          <View key={msgIdx} style={styles.messageItem}>
                            <Text style={styles.messageRole}>
                              {msg.role === 'user' ? 'You' : 'Assistant'}:
                            </Text>
                            <Text style={styles.messageText} numberOfLines={2}>
                              {msg.text}
                            </Text>
                          </View>
                        ))}
                        {conv.messages.length > 3 && (
                          <Text style={styles.moreMessages}>
                            +{conv.messages.length - 3} more messages
                          </Text>
                        )}
                      </View>
                    )}
                  </View>
                ))
              ) : (
                <View style={styles.emptyCard}>
                  <Text style={styles.emptyText}>No past conversations found.</Text>
                  <Text style={styles.emptySubtext}>
                    Conversations mentioning this contact will appear here.
                  </Text>
                </View>
              )}
            </View>
          </View>
        )}
      </ScrollView>
      <EditContactModal
        visible={editOpen}
        onClose={(saved, updated) => {
          setEditOpen(false);
          if (saved && updated) {
            // Reload contact details to show updated information
            loadContactDetail();
          }
        }}
        userId={userId}
        contact={contactInfo}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.primary[50],
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: 12,
  },
  loadingText: {
    color: colors.primary[900] + '80',
    fontSize: 14,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    backgroundColor: colors.primary[50],
    borderBottomWidth: 1,
    borderBottomColor: colors.dark[500] + '10',
  },
  backButton: {
    marginRight: 12,
    padding: 4,
  },
  headerTitle: {
    fontSize: 20,
    fontWeight: '700',
    color: colors.primary[900],
    flex: 1,
  },
  editButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 8,
    backgroundColor: colors.secondary[500] + '20',
    borderWidth: 1,
    borderColor: colors.secondary[500] + '40',
  },
  editButtonText: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.secondary[700],
  },
  contactHeader: {
    alignItems: 'center',
    padding: 24,
    backgroundColor: colors.primary[50],
    borderBottomWidth: 1,
    borderBottomColor: colors.dark[500] + '10',
  },
  avatar: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: colors.secondary[500],
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 12,
    ...commonStyles.shadowLg,
  },
  avatarText: {
    fontSize: 32,
    fontWeight: '700',
    color: '#fff',
  },
  contactName: {
    fontSize: 24,
    fontWeight: '700',
    color: colors.primary[900],
    marginBottom: 4,
  },
  contactEmail: {
    fontSize: 14,
    color: colors.primary[900] + '80',
    marginBottom: 4,
  },
  contactNickname: {
    fontSize: 16,
    color: colors.secondary[700],
    fontStyle: 'italic',
  },
  tabs: {
    flexDirection: 'row',
    backgroundColor: colors.primary[50],
    borderBottomWidth: 1,
    borderBottomColor: colors.dark[500] + '10',
  },
  tab: {
    flex: 1,
    paddingVertical: 16,
    alignItems: 'center',
    borderBottomWidth: 2,
    borderBottomColor: 'transparent',
  },
  tabActive: {
    borderBottomColor: colors.secondary[500],
  },
  tabText: {
    fontSize: 16,
    color: colors.primary[900] + '80',
    fontWeight: '500',
  },
  tabTextActive: {
    color: colors.secondary[700],
    fontWeight: '700',
  },
  content: {
    flex: 1,
    padding: 16,
  },
  infoTab: {
    gap: 16,
  },
  notesTab: {
    gap: 16,
  },
  section: {
    marginBottom: 24,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: colors.primary[900],
    marginBottom: 12,
  },
  infoRow: {
    flexDirection: 'row',
    marginBottom: 12,
    flexWrap: 'wrap',
  },
  infoLabel: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.primary[900] + '80',
    width: 100,
  },
  infoValue: {
    fontSize: 14,
    color: colors.primary[900],
    flex: 1,
  },
  groupsContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    flex: 1,
  },
  groupPill: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
    backgroundColor: colors.primary[200] + '40',
    borderWidth: 1,
    borderColor: colors.dark[500] + '10',
  },
  groupPillText: {
    fontSize: 12,
    color: colors.primary[900] + '90',
  },
  interactionCard: {
    backgroundColor: colors.primary[200] + '20',
    padding: 16,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.dark[500] + '10',
  },
  interactionSubject: {
    fontSize: 16,
    fontWeight: '600',
    color: colors.primary[900],
    marginBottom: 8,
  },
  interactionFrom: {
    fontSize: 14,
    color: colors.primary[900] + '80',
    marginBottom: 4,
  },
  interactionDate: {
    fontSize: 12,
    color: colors.primary[900] + '60',
    marginBottom: 8,
  },
  interactionSnippet: {
    fontSize: 14,
    color: colors.primary[900] + '90',
    lineHeight: 20,
  },
  notesCard: {
    backgroundColor: colors.primary[200] + '20',
    padding: 16,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.dark[500] + '10',
  },
  notesText: {
    fontSize: 14,
    color: colors.primary[900],
    lineHeight: 22,
  },
  emptyCard: {
    backgroundColor: colors.primary[200] + '10',
    padding: 24,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.dark[500] + '10',
    alignItems: 'center',
  },
  emptyText: {
    fontSize: 14,
    color: colors.primary[900] + '80',
    marginBottom: 4,
    textAlign: 'center',
  },
  emptySubtext: {
    fontSize: 12,
    color: colors.primary[900] + '60',
    textAlign: 'center',
  },
  conversationCard: {
    backgroundColor: colors.primary[200] + '20',
    padding: 16,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.dark[500] + '10',
    marginBottom: 12,
  },
  conversationHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  conversationDate: {
    fontSize: 12,
    color: colors.primary[900] + '80',
    fontWeight: '600',
  },
  conversationSession: {
    fontSize: 11,
    color: colors.primary[900] + '60',
  },
  conversationMessage: {
    fontSize: 14,
    color: colors.primary[900],
    lineHeight: 20,
  },
  messagesList: {
    marginTop: 12,
    gap: 8,
  },
  messageItem: {
    paddingLeft: 12,
    borderLeftWidth: 2,
    borderLeftColor: colors.secondary[500] + '40',
  },
  messageRole: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.secondary[700],
    marginBottom: 4,
  },
  messageText: {
    fontSize: 13,
    color: colors.primary[900] + '90',
    lineHeight: 18,
  },
  moreMessages: {
    fontSize: 12,
    color: colors.primary[900] + '60',
    fontStyle: 'italic',
    marginTop: 4,
  },
});

