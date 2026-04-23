import { Platform, NativeModules } from 'react-native';

// API configuration
// For device/emulator: use your computer's IP address
// For web: use localhost
// Find your IP with: ipconfig (Windows) or ifconfig (Mac/Linux)

// Fallback computer IP (only used if we can't auto-detect the dev host)
// You can still override everything with EXPO_PUBLIC_API_BASE_URL / API_BASE_URL.
const FALLBACK_LOCAL_IP = '192.168.0.101';

/** Safe on native: `window` may exist without `window.location` (Expo / Hermes). */
const getWebHostname = () => {
  try {
    if (typeof window === 'undefined' || !window.location) return '';
    const h = window.location.hostname;
    return typeof h === 'string' ? h : '';
  } catch {
    return '';
  }
};

const getWebOrigin = () => {
  try {
    if (typeof window === 'undefined' || !window.location) return '';
    const o = window.location.origin;
    return typeof o === 'string' ? o : '';
  } catch {
    return '';
  }
};

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
  
  // Detect production only in a real browser (native has no location.hostname).
  const webHost = getWebHostname();
  const isProduction =
    !!webHost &&
    (webHost.includes('railway.app') ||
      webHost.includes('railway') ||
      webHost.includes('aivis.pw'));

  // Web: if not production, prefer the current hostname with core backend port 5000.
  // Aligns with `python server.py core` / gunicorn core_app:app (start.sh, cwd backend/).
  if (Platform.OS === 'web' && webHost) {
    if (!isProduction) {
      const url = `http://${webHost}:5000`;
      console.log('Using local web API URL (derived from window host):', url);
      return url;
    }
  }

  // Native (iOS/Android): only use local backend when explicitly enabled.
  if (Platform.OS !== 'web' && USE_LOCAL && !isProduction) {
    const devHost = getDevHostFromRN();
    const host = devHost || FALLBACK_LOCAL_IP;
    const url = `http://${host}:5000`;
    console.log('Using local device API URL:', url, '(devHost=', devHost, ')');
    return url;
  }
  
  // Production: Use Railway URL or current origin (web only when origin exists).
  const origin = getWebOrigin();
  const apiUrl = isProduction && origin ? origin : RAILWAY_URL;
  console.log('Using production API URL:', apiUrl);
  return apiUrl;
};

export const API_BASE_URL = getApiBaseUrl();

// Log the API URL when module loads
console.log('API_BASE_URL configured:', API_BASE_URL);

// Optional: a separate base URL for the local core backend (SQLite + ingestion).
// This lets the app keep using API_BASE_URL for chat/OAuth while reading inbox
// data from a different service (e.g. local backend on :5000).
const getCoreBackendUrl = () => {
  const envCore =
    process.env.EXPO_PUBLIC_CORE_BACKEND_URL ||
    process.env.CORE_BACKEND_URL;
  if (envCore) {
    console.log('Using CORE_BACKEND_URL from env:', envCore);
    return envCore;
  }

  // Default local core backend port.
  const webHostCore = getWebHostname();
  if (Platform.OS === 'web' && webHostCore) {
    const url = `http://${webHostCore}:5000`;
    console.log('Using local web CORE_BACKEND_URL (derived):', url);
    return url;
  }

  const devHost = getDevHostFromRN();
  const host = devHost || FALLBACK_LOCAL_IP;
  const url = `http://${host}:5000`;
  console.log('Using local device CORE_BACKEND_URL:', url, '(devHost=', devHost, ')');
  return url;
};

export const CORE_BACKEND_URL = getCoreBackendUrl();
console.log('CORE_BACKEND_URL configured:', CORE_BACKEND_URL);

export const genSession = (id) => 
  `${id}-${Math.random().toString(36).substring(2, 8)}`;

