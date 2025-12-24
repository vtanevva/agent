import { Platform } from 'react-native';

// API configuration
// For device/emulator: use your computer's IP address
// For web: use localhost
// Find your IP with: ipconfig (Windows) or ifconfig (Mac/Linux)

// Your computer's local IP address - UPDATE THIS if your IP changes
const LOCAL_IP = '192.168.0.101';

const getApiBaseUrl = () => {
  // Check environment variable first
  if (process.env.API_BASE_URL) {
    console.log('Using API_BASE_URL from env:', process.env.API_BASE_URL);
    return process.env.API_BASE_URL;
  }
  
  // Railway production URL - UPDATE THIS with your Railway URL
  // Find it in Railway dashboard -> your project -> Settings -> Domains
  const RAILWAY_URL = 'https://web-production-0b6ce.up.railway.app'; // ⬅️ UPDATE THIS!
  
  // For development, use localhost if USE_LOCAL is explicitly set to 'true'
  // OR if we're running on localhost
  const USE_LOCAL = process.env.USE_LOCAL === 'true' || 
    (typeof window !== 'undefined' && window.location.hostname === 'localhost');
  
  // Detect if we're in production (running on Railway domain or production build)
  const isProduction = typeof window !== 'undefined' && 
    (window.location.hostname.includes('railway.app') || 
     window.location.hostname.includes('railway'));
  
  if (USE_LOCAL && !isProduction) {
    // For web platform, use localhost
    if (Platform.OS === 'web') {
      const url = 'http://localhost:10000';
      console.log('Using local web API URL:', url);
      return url;
    }
    
    // For device/emulator (iOS/Android), use your computer's IP address
    const url = `http://${LOCAL_IP}:10000`;
    console.log('Using local device API URL:', url);
    return url;
  }
  
  // Production: Use Railway URL or current origin
  const apiUrl = isProduction && typeof window !== 'undefined' 
    ? window.location.origin  // Use same origin in production
    : RAILWAY_URL;
  console.log('Using production API URL:', apiUrl);
  return apiUrl;
};

export const API_BASE_URL = getApiBaseUrl();

// Log the API URL when module loads
console.log('API_BASE_URL configured:', API_BASE_URL);

export const genSession = (id) => 
  `${id}-${Math.random().toString(36).substring(2, 8)}`;

