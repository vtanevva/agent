import { Platform, NativeModules } from 'react-native';

// API configuration
// For device/emulator: use your computer's IP address
// For web: use localhost
// Find your IP with: ipconfig (Windows) or ifconfig (Mac/Linux)

// Fallback computer IP (only used if we can't auto-detect the dev host)
// You can still override everything with EXPO_PUBLIC_API_BASE_URL / API_BASE_URL.
const FALLBACK_LOCAL_IP = '192.168.0.101';

const isProbablyPrivateHost = (host) => {
  if (!host) return false;
  if (host === 'localhost' || host === '127.0.0.1' || host === '0.0.0.0') return true;
  // RFC1918-ish quick check
  return (
    host.startsWith('10.') ||
    host.startsWith('192.168.') ||
    /^172\.(1[6-9]|2\d|3[0-1])\./.test(host)
  );
};

const getDevHostFromRN = () => {
  // In native dev, the JS bundle URL usually contains the Metro host.
  // Example: "http://192.168.1.107:8081/index.bundle?platform=ios&dev=true..."
  try {
    const scriptURL = NativeModules?.SourceCode?.scriptURL;
    if (!scriptURL || typeof scriptURL !== 'string') return null;
    const withoutProto = scriptURL.split('://')[1] || '';
    const hostPort = withoutProto.split('/')[0] || '';
    const host = hostPort.split(':')[0] || '';
    return host || null;
  } catch {
    return null;
  }
};

const getApiBaseUrl = () => {
  // Check environment variable first
  const envApi =
    process.env.EXPO_PUBLIC_API_BASE_URL ||
    process.env.API_BASE_URL;
  if (envApi) {
    console.log('Using API_BASE_URL from env:', envApi);
    return envApi;
  }
  
  // Railway production URL - UPDATE THIS with your Railway URL
  // Find it in Railway dashboard -> your project -> Settings -> Domains
  const RAILWAY_URL = 'https://web-production-0b6ce.up.railway.app'; // ⬅️ UPDATE THIS!
  
  // For development, use local backend if USE_LOCAL is explicitly set
  // OR if we can clearly tell we're not on production.
  const envUseLocal =
    process.env.EXPO_PUBLIC_USE_LOCAL ||
    process.env.USE_LOCAL;
  const USE_LOCAL = envUseLocal === 'true';
  
  // Detect if we're in production (running on Railway domain or custom domain)
  const isProduction = typeof window !== 'undefined' &&
    (window.location.hostname.includes('railway.app') ||
     window.location.hostname.includes('railway') ||
     window.location.hostname.includes('aivis.pw'));
  
  // Web: if not production, prefer the current hostname with API port 10000.
  // This fixes cases like opening the locally-served web build at http://127.0.0.1:10000
  // or http://192.168.x.x:10000 where the app previously defaulted to Railway.
  if (Platform.OS === 'web' && typeof window !== 'undefined') {
    if (!isProduction) {
      const host = window.location.hostname;
      const url = `http://${host}:10000`;
      console.log('Using local web API URL (derived from window host):', url);
      return url;
    }
  }

  // Native (iOS/Android): only use local backend when explicitly enabled.
  if (Platform.OS !== 'web' && USE_LOCAL && !isProduction) {
    const devHost = getDevHostFromRN();
    const host = devHost || FALLBACK_LOCAL_IP;
    const url = `http://${host}:10000`;
    console.log('Using local device API URL:', url, '(devHost=', devHost, ')');
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

