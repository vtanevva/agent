import React from 'react';

const CalendarEvent = ({ event, onEventClick }) => {
  const formatTime = (dateTimeString) => {
    const date = new Date(dateTimeString);
    return date.toLocaleTimeString('en-US', { 
      hour: 'numeric', 
      minute: '2-digit',
      hour12: true 
    });
  };

  const formatDate = (dateTimeString) => {
    const date = new Date(dateTimeString);
    return date.toLocaleDateString('en-US', { 
      weekday: 'short', 
      month: 'short', 
      day: 'numeric',
      year: 'numeric'
    });
  };

  const getEventStatus = () => {
    const now = new Date();
    const startTime = new Date(event.start);
    const endTime = new Date(event.end);
    
    if (now < startTime) {
      return { status: 'upcoming', color: 'bg-blue-100 text-blue-800', icon: '⏰' };
    } else if (now >= startTime && now <= endTime) {
      return { status: 'ongoing', color: 'bg-green-100 text-green-800', icon: '🟢' };
    } else {
      return { status: 'completed', color: 'bg-gray-100 text-gray-800', icon: '✅' };
    }
  };

  const eventStatus = getEventStatus();

  return (
    <div 
      className="bg-white rounded-xl shadow-lg border border-gray-200 p-4 hover:shadow-xl transition-all duration-300 cursor-pointer max-w-md"
      onClick={() => onEventClick && onEventClick(event)}
    >
      {/* Event Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center space-x-2">
          <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg flex items-center justify-center text-white text-sm font-bold">
            📅
          </div>
          <div>
            <h3 className="font-semibold text-gray-800 text-lg">{event.summary}</h3>
            <p className="text-sm text-gray-500">{formatDate(event.start)}</p>
          </div>
        </div>
        <div className={`px-2 py-1 rounded-full text-xs font-medium ${eventStatus.color}`}>
          {eventStatus.icon} {eventStatus.status}
        </div>
      </div>

      {/* Event Details */}
      <div className="space-y-2">
        {/* Time */}
        <div className="flex items-center space-x-2 text-sm text-gray-600">
          <span className="text-gray-400">🕐</span>
          <span>{formatTime(event.start)} - {formatTime(event.end)}</span>
        </div>

        {/* Location */}
        {event.location && (
          <div className="flex items-center space-x-2 text-sm text-gray-600">
            <span className="text-gray-400">📍</span>
            <span>{event.location}</span>
          </div>
        )}

        {/* Description */}
        {event.description && (
          <div className="text-sm text-gray-600 mt-3 p-3 bg-gray-50 rounded-lg">
            <p className="line-clamp-3">{event.description}</p>
          </div>
        )}

        {/* Attendees */}
        {event.attendees && event.attendees.length > 0 && (
          <div className="flex items-center space-x-2 text-sm text-gray-600">
            <span className="text-gray-400">👥</span>
            <span>{event.attendees.length} attendee{event.attendees.length !== 1 ? 's' : ''}</span>
          </div>
        )}
      </div>

      {/* Action Buttons */}
      <div className="flex space-x-2 mt-4 pt-3 border-t border-gray-100">
        <button className="flex-1 bg-blue-500 text-white py-2 px-3 rounded-lg text-sm hover:bg-blue-600 transition-colors">
          View Details
        </button>
        <button className="flex-1 bg-gray-100 text-gray-700 py-2 px-3 rounded-lg text-sm hover:bg-gray-200 transition-colors">
          Edit
        </button>
      </div>
    </div>
  );
};

export default CalendarEvent;
