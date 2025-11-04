import { Platform } from 'react-native';

// API configuration
// For device/emulator: use your computer's IP address
// For web: use localhost
// Find your IP with: ipconfig (Windows) or ifconfig (Mac/Linux)

// Your computer's local IP address - UPDATE THIS if your IP changes
const LOCAL_IP = '192.168.0.104';

const getApiBaseUrl = () => {
  // Check environment variable first
  if (process.env.API_BASE_URL) {
    console.log('Using API_BASE_URL from env:', process.env.API_BASE_URL);
    return process.env.API_BASE_URL;
  }
  
  // For web platform, use localhost
  if (Platform.OS === 'web') {
    const url = 'http://localhost:10000';
    console.log('Using web API URL:', url);
    return url;
  }
  
  // For device/emulator (iOS/Android), use your computer's IP address
  const url = `http://${LOCAL_IP}:10000`;
  console.log('Using device API URL:', url);
  return url;
};

export const API_BASE_URL = getApiBaseUrl();

// Log the API URL when module loads
console.log('API_BASE_URL configured:', API_BASE_URL);

export const genSession = (id) => 
  `${id}-${Math.random().toString(36).substring(2, 8)}`;

