import React, {useState} from 'react';
import {
  View,
  Text,
  Modal,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
} from 'react-native';
import {LinearGradient} from 'expo-linear-gradient';
import {colors} from '../styles/colors';
import {commonStyles} from '../styles/commonStyles';
import CalendarEvent from './CalendarEvent';

export default function CalendarView({events = [], onEventClick, onClose}) {
  const [currentDate, setCurrentDate] = useState(new Date());
  const [selectedDate, setSelectedDate] = useState(new Date());

  const getDaysInMonth = (date) => {
    const year = date.getFullYear();
    const month = date.getMonth();
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    const daysInMonth = lastDay.getDate();
    const startingDay = firstDay.getDay();
    
    const days = [];
    for (let i = 0; i < startingDay; i++) {
      days.push(null);
    }
    for (let i = 1; i <= daysInMonth; i++) {
      days.push(new Date(year, month, i));
    }
    return days;
  };

  const formatTime = (dateTimeString) => {
    const date = new Date(dateTimeString);
    return date.toLocaleTimeString('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
    });
  };

  const formatDate = (date) => {
    return date.toLocaleDateString('en-US', {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
    });
  };

  const getEventsForDate = (date) => {
    if (!date) return [];
    return events.filter(event => {
      const eventDate = new Date(event.start);
      return eventDate.toDateString() === date.toDateString();
    });
  };

  const days = getDaysInMonth(currentDate);
  const monthName = currentDate.toLocaleDateString('en-US', {
    month: 'long',
    year: 'numeric',
  });

  const nextMonth = () => {
    setCurrentDate(
      new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 1),
    );
  };

  const prevMonth = () => {
    setCurrentDate(
      new Date(currentDate.getFullYear(), currentDate.getMonth() - 1, 1),
    );
  };

  const today = new Date();
  const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

  return (
    <Modal visible={true} transparent animationType="fade">
      <View style={styles.overlay}>
        <View style={styles.container}>
          <LinearGradient
            colors={[colors.accent[500], colors.secondary[600]]}
            style={styles.header}>
            <View style={styles.headerContent}>
              <Text style={styles.headerTitle}>📅 Calendar</Text>
              <TouchableOpacity onPress={onClose} style={styles.closeButton}>
                <Text style={styles.closeText}>✕</Text>
              </TouchableOpacity>
            </View>
            
            <View style={styles.monthNavigation}>
              <TouchableOpacity onPress={prevMonth} style={styles.navButton}>
                <Text style={styles.navText}>←</Text>
              </TouchableOpacity>
              <Text style={styles.monthName}>{monthName}</Text>
              <TouchableOpacity onPress={nextMonth} style={styles.navButton}>
                <Text style={styles.navText}>→</Text>
              </TouchableOpacity>
            </View>
          </LinearGradient>

          <View style={styles.content}>
            <View style={styles.calendarGrid}>
              <View style={styles.dayHeaders}>
                {dayNames.map(day => (
                  <View key={day} style={styles.dayHeader}>
                    <Text style={styles.dayHeaderText}>{day}</Text>
                  </View>
                ))}
              </View>

              <View style={styles.daysGrid}>
                {days.map((day, index) => {
                  const isToday =
                    day && day.toDateString() === today.toDateString();
                  const isSelected =
                    day && day.toDateString() === selectedDate.toDateString();
                  const dayEvents = getEventsForDate(day);
                  
                  return (
                    <TouchableOpacity
                      key={index}
                      onPress={() => day && setSelectedDate(day)}
                      style={[
                        styles.dayCell,
                        !day && styles.dayCellEmpty,
                        isToday && styles.dayCellToday,
                        isSelected && styles.dayCellSelected,
                      ]}>
                      {day && (
                        <>
                          <Text
                            style={[
                              styles.dayNumber,
                              isToday && styles.dayNumberToday,
                              isSelected && styles.dayNumberSelected,
                            ]}>
                            {day.getDate()}
                          </Text>
                          {dayEvents.length > 0 && (
                            <View style={styles.eventIndicators}>
                              {dayEvents.slice(0, 2).map((event, eventIndex) => (
                                <View
                                  key={eventIndex}
                                  style={styles.eventDot}
                                />
                              ))}
                              {dayEvents.length > 2 && (
                                <Text style={styles.moreEvents}>
                                  +{dayEvents.length - 2}
                                </Text>
                              )}
                            </View>
                          )}
                        </>
                      )}
                    </TouchableOpacity>
                  );
                })}
              </View>
            </View>

            <View style={styles.eventsPanel}>
              <Text style={styles.eventsTitle}>
                Events for {formatDate(selectedDate)}
              </Text>
              
              <ScrollView style={styles.eventsList} showsVerticalScrollIndicator={false}>
                {getEventsForDate(selectedDate).length === 0 ? (
                  <View style={styles.emptyEvents}>
                    <Text style={styles.emptyEmoji}>📅</Text>
                    <Text style={styles.emptyText}>No events scheduled</Text>
                  </View>
                ) : (
                  getEventsForDate(selectedDate).map((event, index) => (
                    <CalendarEvent
                      key={index}
                      event={event}
                      onEventClick={onEventClick}
                    />
                  ))
                )}
              </ScrollView>
            </View>
          </View>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 16,
  },
  container: {
    width: '100%',
    maxWidth: 800,
    maxHeight: '90%',
    backgroundColor: colors.primary[50],
    borderRadius: 16,
    overflow: 'hidden',
    ...commonStyles.shadowLg,
  },
  header: {
    padding: 24,
  },
  headerContent: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },
  headerTitle: {
    fontSize: 24,
    fontWeight: 'bold',
    color: colors.primary[50],
  },
  closeButton: {
    padding: 8,
  },
  closeText: {
    fontSize: 24,
    color: colors.primary[50],
    fontWeight: 'bold',
  },
  monthNavigation: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  navButton: {
    backgroundColor: 'rgba(255,255,255,0.2)',
    borderRadius: 20,
    padding: 8,
    width: 40,
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
  },
  navText: {
    fontSize: 20,
    color: colors.primary[50],
    fontWeight: 'bold',
  },
  monthName: {
    fontSize: 20,
    fontWeight: '600',
    color: colors.primary[50],
  },
  content: {
    flexDirection: 'row',
    height: 500,
  },
  calendarGrid: {
    flex: 1,
    padding: 16,
  },
  dayHeaders: {
    flexDirection: 'row',
    marginBottom: 8,
  },
  dayHeader: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: 8,
  },
  dayHeaderText: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.primary[900] + '80',
  },
  daysGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
  },
  dayCell: {
    width: '14.28%',
    aspectRatio: 1,
    padding: 4,
    borderWidth: 1,
    borderColor: colors.dark[500] + '20',
    borderRadius: 8,
    margin: 1,
    justifyContent: 'flex-start',
    alignItems: 'flex-start',
  },
  dayCellEmpty: {
    backgroundColor: colors.primary[100] + '50',
    borderColor: 'transparent',
  },
  dayCellToday: {
    backgroundColor: colors.accent[500] + '20',
    borderColor: colors.accent[500],
    borderWidth: 2,
  },
  dayCellSelected: {
    backgroundColor: colors.secondary[500] + '20',
    borderColor: colors.secondary[500],
    borderWidth: 2,
  },
  dayNumber: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.primary[900],
    marginBottom: 4,
  },
  dayNumberToday: {
    color: colors.accent[600],
  },
  dayNumberSelected: {
    color: colors.secondary[600],
  },
  eventIndicators: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 2,
    alignItems: 'center',
  },
  eventDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.accent[500],
  },
  moreEvents: {
    fontSize: 10,
    color: colors.primary[900] + '60',
  },
  eventsPanel: {
    width: 280,
    borderLeftWidth: 1,
    borderLeftColor: colors.dark[500] + '20',
    padding: 16,
    backgroundColor: colors.primary[100] + '50',
  },
  eventsTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: colors.primary[900],
    marginBottom: 16,
  },
  eventsList: {
    flex: 1,
  },
  emptyEvents: {
    alignItems: 'center',
    paddingVertical: 32,
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

