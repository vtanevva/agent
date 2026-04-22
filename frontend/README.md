# Aivis - Expo Mobile App

React Native Expo version of the Aivis chatbot application with latest React 19 and RN 0.81.

## 🎯 Status

✅ **Migrated to Expo SDK 54**
- React 19.1.0
- React Native 0.81.5
- Latest Expo modules

⚠️ **Pending: Voice Recognition**
- TTS working with `expo-speech`
- Voice input needs implementation (was using `@react-native-voice/voice`)

## 🚀 Quick Start

```bash
cd frontend
npm install
npx expo start
```

Then:
- Press `i` for iOS simulator
- Press `a` for Android emulator
- Press `w` for web browser
- Scan QR code with Expo Go app

## 📦 Dependencies

- `expo` - Expo SDK
- `@react-navigation/native` - Navigation
- `expo-linear-gradient` - Gradients
- `expo-speech` - Text-to-speech
- `axios` - API calls
- `react-native-screens` - Native screens

## 🔧 Migration Notes

### Fixed
- ✅ LinearGradient → expo-linear-gradient
- ✅ SafeArea → react-native-safe-area-context
- ✅ TTS → expo-speech
- ✅ Navigation works

### To Do
- ⚠️ Voice recognition (need alternative to @react-native-voice/voice)
- ⚠️ Test all features
- ⚠️ Build with EAS

## 🌐 API Config

Default API: `https://web-production-0b6ce.up.railway.app`

Update in `src/config/api.js` if needed.

## 📱 Features

- ✅ Text chat
- ✅ Email integration
- ✅ Calendar events
- ✅ Session management
- ✅ OAuth flow
- ⏳ Voice chat (TTS working, input pending)

## 🐛 Known Issues

- Node version warning (v20.10.0 vs 20.19.4 required) - still works
- Voice input temporarily disabled

## 📚 Next Steps

1. Implement voice recognition alternative
2. Test on physical devices
3. Setup EAS build for production
4. Deploy to app stores

