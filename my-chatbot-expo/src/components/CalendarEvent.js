import React from 'react';
import {View, Text, TouchableOpacity, StyleSheet} from 'react-native';
import {LinearGradient} from 'expo-linear-gradient';
import {colors} from '../styles/colors';
import {commonStyles} from '../styles/commonStyles';

export default function CalendarEvent({event, onEventClick}) {
  const formatTime = (dateTimeString) => {
    const date = new Date(dateTimeString);
    return date.toLocaleTimeString('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
    });
  };

  const formatDate = (dateTimeString) => {
    const date = new Date(dateTimeString);
    return date.toLocaleDateString('en-US', {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  const getEventStatus = () => {
    const now = new Date();
    const startTime = new Date(event.start);
    const endTime = new Date(event.end);
    
    if (now < startTime) {
      return {status: 'upcoming', color: colors.accent[500], icon: '⏰'};
    } else if (now >= startTime && now <= endTime) {
      return {status: 'ongoing', color: colors.secondary[500], icon: '🟢'};
    } else {
      return {status: 'completed', color: colors.dark[500], icon: '✅'};
    }
  };

  const eventStatus = getEventStatus();

  return (
    <TouchableOpacity
      onPress={() => onEventClick && onEventClick(event)}
      style={styles.container}>
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          <LinearGradient
            colors={[colors.accent[500], colors.secondary[600]]}
            style={styles.icon}>
            <Text style={styles.iconText}>📅</Text>
          </LinearGradient>
          <View style={styles.titleContainer}>
            <Text style={styles.title}>{event.summary}</Text>
            <Text style={styles.date}>{formatDate(event.start)}</Text>
          </View>
        </View>
        <View style={[styles.statusBadge, {backgroundColor: eventStatus.color + '30'}]}>
          <Text style={[styles.statusText, {color: eventStatus.color}]}>
            {eventStatus.icon} {eventStatus.status}
          </Text>
        </View>
      </View>

      <View style={styles.details}>
        <View style={styles.detailRow}>
          <Text style={styles.detailEmoji}>🕐</Text>
          <Text style={styles.detailText}>
            {formatTime(event.start)} - {formatTime(event.end)}
          </Text>
        </View>

        {event.location && (
          <View style={styles.detailRow}>
            <Text style={styles.detailEmoji}>📍</Text>
            <Text style={styles.detailText}>{event.location}</Text>
          </View>
        )}

        {event.description && (
          <View style={styles.descriptionContainer}>
            <Text style={styles.description} numberOfLines={3}>
              {event.description}
            </Text>
          </View>
        )}

        {event.attendees && event.attendees.length > 0 && (
          <View style={styles.detailRow}>
            <Text style={styles.detailEmoji}>👥</Text>
            <Text style={styles.detailText}>
              {event.attendees.length} attendee{event.attendees.length !== 1 ? 's' : ''}
            </Text>
          </View>
        )}
      </View>

      <View style={styles.actions}>
        <TouchableOpacity
          onPress={() => onEventClick && onEventClick(event)}
          style={styles.actionButton}>
          <LinearGradient
            colors={[colors.accent[500], colors.accent[600]]}
            style={styles.actionButtonGradient}>
            <Text style={styles.actionButtonText}>View Details</Text>
          </LinearGradient>
        </TouchableOpacity>
        <TouchableOpacity style={[styles.actionButton, styles.actionButtonSecondary]}>
          <Text style={styles.actionButtonTextSecondary}>Edit</Text>
        </TouchableOpacity>
      </View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  container: {
    ...commonStyles.glassEffect,
    padding: 16,
    marginBottom: 12,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.dark[500] + '20',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 12,
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    flex: 1,
    gap: 12,
  },
  icon: {
    width: 40,
    height: 40,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
    ...commonStyles.shadowSm,
  },
  iconText: {
    fontSize: 20,
  },
  titleContainer: {
    flex: 1,
  },
  title: {
    fontSize: 18,
    fontWeight: '600',
    color: colors.primary[900],
    marginBottom: 4,
  },
  date: {
    fontSize: 14,
    color: colors.primary[900] + '60',
  },
  statusBadge: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 16,
  },
  statusText: {
    fontSize: 12,
    fontWeight: '600',
  },
  details: {
    gap: 8,
    marginBottom: 12,
  },
  detailRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  detailEmoji: {
    fontSize: 16,
  },
  detailText: {
    fontSize: 14,
    color: colors.primary[900] + '70',
  },
  descriptionContainer: {
    backgroundColor: colors.primary[100] + '80',
    padding: 12,
    borderRadius: 8,
    marginTop: 4,
  },
  description: {
    fontSize: 14,
    color: colors.primary[900] + '70',
    lineHeight: 20,
  },
  actions: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 12,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: colors.dark[500] + '10',
  },
  actionButton: {
    flex: 1,
    borderRadius: 8,
    overflow: 'hidden',
    ...commonStyles.shadowSm,
  },
  actionButtonGradient: {
    paddingVertical: 10,
    paddingHorizontal: 16,
    alignItems: 'center',
  },
  actionButtonText: {
    color: colors.primary[50],
    fontSize: 14,
    fontWeight: '600',
  },
  actionButtonSecondary: {
    backgroundColor: colors.primary[100] + '80',
    borderWidth: 1,
    borderColor: colors.dark[500] + '20',
  },
  actionButtonTextSecondary: {
    color: colors.primary[900] + '70',
    fontSize: 14,
    fontWeight: '600',
    textAlign: 'center',
    paddingVertical: 10,
  },
});

