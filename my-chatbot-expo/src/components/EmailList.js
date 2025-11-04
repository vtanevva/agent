import React from 'react';
import {View, Text, TouchableOpacity, StyleSheet, ScrollView} from 'react-native';
import {LinearGradient} from 'expo-linear-gradient';
import {colors} from '../styles/colors';
import {commonStyles} from '../styles/commonStyles';

export default function EmailList({emails, onSelect}) {
  if (!emails || emails.length === 0) {
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
        {emails.map((email, index) => (
          <TouchableOpacity
            key={email.threadId || index}
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

