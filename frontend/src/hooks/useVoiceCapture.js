import {useCallback, useEffect, useRef, useState} from 'react';
import {Platform, Alert, PermissionsAndroid} from 'react-native';
import {Audio} from 'expo-av';

/**
 * Mic → text (Web Speech API, MediaRecorder+Whisper, or expo-av+Whisper).
 * Invokes ``transcriptHandlerRef.current(text)`` with the final transcript (never stale).
 */
export function useVoiceCapture({apiBaseUrl, transcriptHandlerRef, languageCode = 'en-US'}) {
  const [isSupported, setIsSupported] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const recordingRef = useRef(null);
  const recognitionRef = useRef(null);

  useEffect(() => {
    if (Platform.OS === 'web') return;
    let cancelled = false;
    (async () => {
      try {
        const {status} = await Audio.requestPermissionsAsync();
        if (cancelled) return;
        if (status === 'granted') {
          setIsSupported(true);
          try {
            await Audio.setAudioModeAsync({
              allowsRecordingIOS: true,
              playsInSilentModeIOS: true,
              staysActiveInBackground: false,
              shouldDuckAndroid: true,
            });
          } catch (e) {
            console.warn('Audio mode setup failed:', e);
          }
        } else {
          setIsSupported(false);
          Alert.alert(
            'Microphone permission',
            'Please allow microphone access in settings to use voice input.',
          );
        }
      } catch (err) {
        console.error('Permission error:', err);
        if (!cancelled) setIsSupported(false);
      }
      if (Platform.OS === 'android') {
        try {
          await PermissionsAndroid.request(PermissionsAndroid.PERMISSIONS.RECORD_AUDIO);
        } catch {}
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') return;

    const hasMediaRecorder =
      typeof navigator !== 'undefined' &&
      !!navigator.mediaDevices?.getUserMedia &&
      typeof window.MediaRecorder !== 'undefined';

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      setIsSupported(true);
      const rec = new SpeechRecognition();
      rec.continuous = false;
      rec.interimResults = false;
      rec.lang = languageCode || 'en-US';

      rec.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        setIsListening(false);
        setTimeout(() => {
          const fn = transcriptHandlerRef.current;
          if (typeof fn === 'function') fn(transcript);
        }, 50);
      };

      rec.onerror = (event) => {
        console.error('Speech recognition error:', event);
        setIsListening(false);
        const errType = event?.error || '';
        if (errType && errType !== 'no-speech' && errType !== 'aborted') {
          Alert.alert('Speech Recognition Error', 'Failed to recognize speech. Please try again.');
        }
      };

      rec.onend = () => {
        setIsListening(false);
      };
      recognitionRef.current = rec;
    } else if (hasMediaRecorder) {
      setIsSupported(true);
      recognitionRef.current = null;
    } else {
      setIsSupported(false);
    }

    return () => {
      try {
        recognitionRef.current?.abort?.();
      } catch {}
    };
  }, [languageCode, transcriptHandlerRef]);

  const transcribeAndSend = useCallback(
    async (uri) => {
      if (!uri) return;
      setTranscribing(true);
      try {
        const form = new FormData();
        const filename = uri.split('/').pop() || 'recording.m4a';
        const ext = (filename.split('.').pop() || 'm4a').toLowerCase();
        const mime =
          ext === 'wav'
            ? 'audio/wav'
            : ext === 'webm'
              ? 'audio/webm'
              : ext === 'mp3'
                ? 'audio/mpeg'
                : ext === 'ogg'
                  ? 'audio/ogg'
                  : 'audio/m4a';

        if (Platform.OS === 'web') {
          const blob = recordingRef.current?.webBlob;
          if (!blob) throw new Error('No audio blob');
          form.append('file', blob, `recording.${ext}`);
        } else {
          form.append('file', {uri, name: filename, type: mime});
        }

        const res = await fetch(`${apiBaseUrl}/api/transcribe`, {
          method: 'POST',
          body: form,
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok || !data?.success) {
          throw new Error(data?.error || `HTTP ${res.status}`);
        }
        const text = (data.text || '').trim();
        if (!text) {
          Alert.alert('No speech detected', 'I could not hear anything. Please try again.');
          return;
        }
        const fn = transcriptHandlerRef.current;
        if (typeof fn === 'function') await fn(text);
      } catch (err) {
        console.error('transcribe error:', err);
        Alert.alert('Voice error', 'Could not transcribe audio. Please try again.');
      } finally {
        setTranscribing(false);
      }
    },
    [apiBaseUrl, transcriptHandlerRef],
  );

  const startListening = useCallback(async () => {
    if (isListening || transcribing) return;

    if (Platform.OS === 'web') {
      const recognition = recognitionRef.current;
      if (recognition) {
        try {
          setIsListening(true);
          recognition.lang = languageCode || 'en-US';
          recognition.start();
          return;
        } catch (error) {
          console.warn('Web Speech API failed, falling back to recording:', error);
          setIsListening(false);
        }
      }
      try {
        if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
          Alert.alert('Voice not supported', 'This browser does not support voice input.');
          return;
        }
        const stream = await navigator.mediaDevices.getUserMedia({audio: true});
        const mimeType =
          window.MediaRecorder && MediaRecorder.isTypeSupported?.('audio/webm')
            ? 'audio/webm'
            : '';
        const mr = mimeType ? new MediaRecorder(stream, {mimeType}) : new MediaRecorder(stream);
        const chunks = [];
        mr.ondataavailable = (ev) => {
          if (ev.data && ev.data.size > 0) chunks.push(ev.data);
        };
        mr.onstop = async () => {
          try {
            const blob = new Blob(chunks, {type: mimeType || 'audio/webm'});
            recordingRef.current = {webBlob: blob};
            await transcribeAndSend('recording.webm');
          } finally {
            stream.getTracks().forEach((t) => t.stop());
          }
        };
        recordingRef.current = {webRecorder: mr, webStream: stream, webBlob: null};
        mr.start();
        setIsListening(true);
      } catch (err) {
        console.error('Web record start failed:', err);
        setIsListening(false);
        Alert.alert('Microphone error', 'Could not access microphone. Please check browser permissions.');
      }
      return;
    }

    try {
      const {status} = await Audio.getPermissionsAsync();
      let granted = status === 'granted';
      if (!granted) {
        const req = await Audio.requestPermissionsAsync();
        granted = req.status === 'granted';
      }
      if (!granted) {
        Alert.alert('Microphone permission', 'Please enable microphone access in settings.');
        setIsSupported(false);
        return;
      }
      setIsSupported(true);
      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
        staysActiveInBackground: false,
      });
      const rec = new Audio.Recording();
      await rec.prepareToRecordAsync(Audio.RecordingOptionsPresets.HIGH_QUALITY);
      await rec.startAsync();
      recordingRef.current = rec;
      setIsListening(true);
    } catch (err) {
      console.error('Mobile record start failed:', err);
      setIsListening(false);
      Alert.alert('Recording error', 'Could not start recording. Please try again.');
    }
  }, [isListening, transcribing, languageCode, transcribeAndSend]);

  const stopListening = useCallback(async () => {
    if (!isListening) return;
    setIsListening(false);

    if (Platform.OS === 'web') {
      if (recognitionRef.current && !recordingRef.current?.webRecorder) {
        try {
          recognitionRef.current.stop();
        } catch {}
        return;
      }
      const mr = recordingRef.current?.webRecorder;
      if (mr && mr.state !== 'inactive') {
        try {
          mr.stop();
        } catch {}
      }
      return;
    }

    const rec = recordingRef.current;
    if (!rec || typeof rec.stopAndUnloadAsync !== 'function') return;
    try {
      await rec.stopAndUnloadAsync();
      const uri = rec.getURI();
      recordingRef.current = null;
      try {
        await Audio.setAudioModeAsync({
          allowsRecordingIOS: false,
          playsInSilentModeIOS: true,
        });
      } catch {}
      await transcribeAndSend(uri);
    } catch (err) {
      console.error('Mobile record stop failed:', err);
      recordingRef.current = null;
    }
  }, [isListening, transcribeAndSend]);

  return {
    isSupported,
    isListening,
    transcribing,
    startListening,
    stopListening,
  };
}
