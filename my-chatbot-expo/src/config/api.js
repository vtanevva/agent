// API configuration
export const API_BASE_URL = 
  process.env.API_BASE_URL || 
  'http://localhost:10000';

export const genSession = (id) => 
  `${id}-${Math.random().toString(36).substring(2, 8)}`;

