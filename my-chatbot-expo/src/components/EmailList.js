import React from 'react';
import {View, Text, TouchableOpacity, StyleSheet, ScrollView} from 'react-native';
import {LinearGradient} from 'expo-linear-gradient';
import {colors} from '../styles/colors';
import {commonStyles} from '../styles/commonStyles';

export default function EmailList({emails, onSelect, onArchive, onDone, hiddenThreadIds}) {
  const filtered = Array.isArray(emails)
    ? emails.filter(e => !(hiddenThreadIds || []).includes(e.threadId))
    : [];

  if (!filtered || filtered.length === 0) {
    return (
      <View style={styles.emptyContainer}>
        <Text style={styles.emptyEmoji}>📭</Text>
        <Text style={styles.emptyText}>No emails found</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Recent Emails</Text>
        <Text style={styles.headerSubtitle}>Select an email to reply to</Text>
      </View>
      
      <ScrollView
        style={styles.scrollView}
        showsVerticalScrollIndicator={false}>
        {filtered.map((email, index) => (
          <View key={email.threadId || index} style={styles.itemWrapper}>
            <TouchableOpacity
              onPress={() => onSelect(email.threadId, email.from)}
              style={styles.emailCard}>
              <View style={styles.emailContent}>
                <LinearGradient
                  colors={[colors.accent[500], colors.secondary[600]]}
                  style={styles.emailIcon}>
                  <Text style={styles.emailIconText}>
                    {(email.from?.charAt(0) || 'E').toUpperCase()}
                  </Text>
                </LinearGradient>
                
                <View style={styles.emailText}>
                  <View style={styles.emailHeader}>
                    <Text style={styles.emailFrom} numberOfLines={1}>
                      {email.from?.replace(/<[^>]*>/g, '').trim() || 'Unknown'}
                    </Text>
                    {email.idx && (
                      <View style={styles.badge}>
                        <Text style={styles.badgeText}>#{email.idx}</Text>
                      </View>
                    )}
                  </View>
                  
                  <Text style={styles.emailSubject} numberOfLines={1}>
                    {email.subject || 'No subject'}
                  </Text>
                  
                  <Text style={styles.emailSnippet} numberOfLines={2}>
                    {email.snippet || ''}
                  </Text>
                </View>
              </View>
              
              {email.threadId && (
                <View style={styles.threadBadge}>
                  <Text style={styles.threadBadgeText}>
                    {email.threadId.slice(-8)}
                  </Text>
                </View>
              )}
            </TouchableOpacity>
            <View style={styles.actionRow}>
              <TouchableOpacity
                style={[styles.smallBtn, styles.archiveBtn]}
                onPress={() => onArchive?.(email.threadId)}
              >
                <Text style={styles.smallBtnText}>Archive</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.smallBtn, styles.doneBtn]}
                onPress={() => onDone?.(email.threadId)}
              >
                <Text style={styles.smallBtnText}>Done</Text>
              </TouchableOpacity>
            </View>
          </View>
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    marginVertical: 16,
  },
  header: {
    alignItems: 'center',
    marginBottom: 16,
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: colors.primary[900],
    marginBottom: 4,
  },
  headerSubtitle: {
    fontSize: 14,
    color: colors.primary[900] + '60',
  },
  scrollView: {
    maxHeight: 400,
  },
  emailCard: {
    ...commonStyles.glassEffect,
    padding: 12,
    marginBottom: 12,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.dark[500] + '30',
  },
  emailContent: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 12,
  },
  emailIcon: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
    ...commonStyles.shadowMd,
  },
  emailIconText: {
    color: colors.primary[50],
    fontSize: 16,
    fontWeight: '600',
  },
  emailText: {
    flex: 1,
    gap: 4,
  },
  emailHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  emailFrom: {
    flex: 1,
    fontSize: 14,
    fontWeight: '500',
    color: colors.primary[900],
  },
  badge: {
    backgroundColor: colors.primary[200] + '80',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 12,
  },
  badgeText: {
    fontSize: 12,
    color: colors.primary[900] + '60',
  },
  emailSubject: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.primary[900],
    marginTop: 4,
  },
  emailSnippet: {
    fontSize: 12,
    color: colors.primary[900] + '70',
    lineHeight: 18,
    marginTop: 4,
  },
  threadBadge: {
    marginTop: 8,
    alignSelf: 'flex-end',
    backgroundColor: colors.primary[200] + '80',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 8,
  },
  threadBadgeText: {
    fontSize: 10,
    color: colors.primary[900] + '60',
    fontFamily: 'monospace',
  },
  actionRow: {
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'flex-end',
    marginTop: -6,
    marginBottom: 12,
  },
  smallBtn: {
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 8,
    borderWidth: 1,
  },
  smallBtnText: {
    fontSize: 12,
    fontWeight: '500',
  },
  archiveBtn: {
    borderColor: colors.dark[500] + '20',
    backgroundColor: colors.primary[200] + '30',
  },
  doneBtn: {
    borderColor: colors.secondary[600] + '30',
    backgroundColor: colors.secondary[500] + '25',
  },
  emptyContainer: {
    alignItems: 'center',
    padding: 32,
  },
  emptyEmoji: {
    fontSize: 48,
    marginBottom: 16,
  },
  emptyText: {
    fontSize: 14,
    color: colors.primary[900] + '60',
  },
});

