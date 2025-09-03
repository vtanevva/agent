import React, { useState, useEffect } from 'react';

const CalendarView = ({ events = [], onEventClick, onClose }) => {
  const [currentDate, setCurrentDate] = useState(new Date());
  const [selectedDate, setSelectedDate] = useState(new Date());

  // Generate calendar days
  const getDaysInMonth = (date) => {
    const year = date.getFullYear();
    const month = date.getMonth();
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    const daysInMonth = lastDay.getDate();
    const startingDay = firstDay.getDay();
    
    const days = [];
    
    // Add empty days for padding
    for (let i = 0; i < startingDay; i++) {
      days.push(null);
    }
    
    // Add days of the month
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
      hour12: true 
    });
  };

  const formatDate = (date) => {
    return date.toLocaleDateString('en-US', { 
      weekday: 'short', 
      month: 'short', 
      day: 'numeric' 
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
  const monthName = currentDate.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });

  const nextMonth = () => {
    setCurrentDate(new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 1));
  };

  const prevMonth = () => {
    setCurrentDate(new Date(currentDate.getFullYear(), currentDate.getMonth() - 1, 1));
  };

  const today = new Date();

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl shadow-2xl max-w-4xl w-full max-h-[90vh] overflow-hidden">
        {/* Header */}
        <div className="bg-gradient-to-r from-blue-500 to-purple-600 text-white p-6">
          <div className="flex justify-between items-center">
            <h2 className="text-2xl font-bold">📅 Calendar</h2>
            <button
              onClick={onClose}
              className="text-white hover:text-gray-200 text-xl"
            >
              ✕
            </button>
          </div>
          
          {/* Month Navigation */}
          <div className="flex justify-between items-center mt-4">
            <button
              onClick={prevMonth}
              className="bg-white bg-opacity-20 hover:bg-opacity-30 rounded-full p-2 transition-all"
            >
              ←
            </button>
            <h3 className="text-xl font-semibold">{monthName}</h3>
            <button
              onClick={nextMonth}
              className="bg-white bg-opacity-20 hover:bg-opacity-30 rounded-full p-2 transition-all"
            >
              →
            </button>
          </div>
        </div>

        <div className="flex h-[calc(90vh-140px)]">
          {/* Calendar Grid */}
          <div className="flex-1 p-6">
            {/* Day Headers */}
            <div className="grid grid-cols-7 gap-1 mb-4">
              {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map(day => (
                <div key={day} className="text-center text-gray-600 font-semibold text-sm py-2">
                  {day}
                </div>
              ))}
            </div>

            {/* Calendar Days */}
            <div className="grid grid-cols-7 gap-1">
              {days.map((day, index) => {
                const isToday = day && day.toDateString() === today.toDateString();
                const isSelected = day && day.toDateString() === selectedDate.toDateString();
                const dayEvents = getEventsForDate(day);
                
                return (
                  <div
                    key={index}
                    className={`min-h-[80px] p-2 border border-gray-200 rounded-lg cursor-pointer transition-all ${
                      !day ? 'bg-gray-50' : 
                      isToday ? 'bg-blue-100 border-blue-300' :
                      isSelected ? 'bg-purple-100 border-purple-300' :
                      'bg-white hover:bg-gray-50'
                    }`}
                    onClick={() => day && setSelectedDate(day)}
                  >
                    {day && (
                      <>
                        <div className={`text-sm font-semibold mb-1 ${
                          isToday ? 'text-blue-600' : 
                          isSelected ? 'text-purple-600' : 
                          'text-gray-700'
                        }`}>
                          {day.getDate()}
                        </div>
                        
                        {/* Event Indicators */}
                        <div className="space-y-1">
                          {dayEvents.slice(0, 2).map((event, eventIndex) => (
                            <div
                              key={eventIndex}
                              className="text-xs bg-blue-500 text-white px-1 py-0.5 rounded truncate"
                              title={event.summary}
                            >
                              {event.summary}
                            </div>
                          ))}
                          {dayEvents.length > 2 && (
                            <div className="text-xs text-gray-500">
                              +{dayEvents.length - 2} more
                            </div>
                          )}
                        </div>
                      </>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Events Panel */}
          <div className="w-80 bg-gray-50 p-6 border-l border-gray-200 overflow-y-auto">
            <h4 className="text-lg font-semibold text-gray-800 mb-4">
              Events for {formatDate(selectedDate)}
            </h4>
            
            <div className="space-y-3">
              {getEventsForDate(selectedDate).length === 0 ? (
                <div className="text-gray-500 text-center py-8">
                  <div className="text-4xl mb-2">📅</div>
                  <p>No events scheduled</p>
                </div>
              ) : (
                getEventsForDate(selectedDate).map((event, index) => (
                  <div
                    key={index}
                    className="bg-white rounded-lg p-4 shadow-sm border border-gray-200 hover:shadow-md transition-all cursor-pointer"
                    onClick={() => onEventClick && onEventClick(event)}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <h5 className="font-semibold text-gray-800 mb-1">
                          {event.summary}
                        </h5>
                        <div className="text-sm text-gray-600 mb-2">
                          {formatTime(event.start)} - {formatTime(event.end)}
                        </div>
                        {event.location && (
                          <div className="text-sm text-gray-500 mb-1">
                            📍 {event.location}
                          </div>
                        )}
                        {event.description && (
                          <div className="text-sm text-gray-600 line-clamp-2">
                            {event.description}
                          </div>
                        )}
                      </div>
                      <div className="ml-2">
                        <div className="w-3 h-3 bg-blue-500 rounded-full"></div>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* Quick Actions */}
            <div className="mt-6 pt-6 border-t border-gray-200">
              <h5 className="text-sm font-semibold text-gray-700 mb-3">Quick Actions</h5>
              <div className="space-y-2">
                <button className="w-full bg-blue-500 text-white py-2 px-4 rounded-lg text-sm hover:bg-blue-600 transition-colors">
                  + Add Event
                </button>
                <button className="w-full bg-gray-200 text-gray-700 py-2 px-4 rounded-lg text-sm hover:bg-gray-300 transition-colors">
                  View All Events
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default CalendarView;
