import React, {useEffect, useState} from 'react';
import {View, TextInput, TouchableOpacity, StyleSheet, Text, Platform, Image, Alert} from 'react-native';
import {LinearGradient} from 'expo-linear-gradient';
import {colors} from '../styles/colors';
import {commonStyles} from '../styles/commonStyles';
import {API_BASE_URL} from '../config/api';

// Conditionally import ImagePicker (not available on web)
let ImagePicker = null;
if (Platform.OS !== 'web') {
  try {
    ImagePicker = require('expo-image-picker');
  } catch (e) {
    console.warn('expo-image-picker not available');
  }
}

export default function InputBar({input, setInput, loading, onSend, showConnectButton, onConnect, onImageSelect}) {
  const [selectedImages, setSelectedImages] = useState([]);
  // Request image picker permissions
  useEffect(() => {
    (async () => {
      if (Platform.OS !== 'web' && ImagePicker) {
        try {
          const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
          if (status !== 'granted') {
            Alert.alert('Permission needed', 'Sorry, we need camera roll permissions to upload images!');
          }
        } catch (e) {
          console.warn('Error requesting image picker permissions:', e);
        }
      }
    })();
  }, []);

  // Add web-specific CSS to hide scrollbar
  useEffect(() => {
    if (Platform.OS === 'web' && typeof document !== 'undefined') {
      if (!document.head.querySelector('style[data-inputbar-scrollbar]')) {
        const style = document.createElement('style');
        style.setAttribute('data-inputbar-scrollbar', 'true');
        style.textContent = `
          textarea::-webkit-scrollbar {
            width: 0px;
            background: transparent;
          }
          textarea::-moz-scrollbar {
            width: 0px;
            background: transparent;
          }
          textarea {
            scrollbar-width: none;
            -ms-overflow-style: none;
          }
        `;
        document.head.appendChild(style);
      }
    }
  }, []);

  const pickImage = async () => {
    console.log('[InputBar] pickImage called, Platform:', Platform.OS);
    try {
      if (Platform.OS === 'web') {
        // Web: use file input and convert to base64 directly
        console.log('[InputBar] Web platform - creating file input');
        return new Promise((resolve) => {
          const input = document.createElement('input');
          input.type = 'file';
          input.accept = 'image/*';
          input.style.display = 'none';
          input.onchange = async (e) => {
            console.log('[InputBar] File selected:', e.target.files[0]?.name);
            const file = e.target.files[0];
            if (file) {
              // Check file size (max 10MB)
              if (file.size > 10 * 1024 * 1024) {
                Alert.alert('Error', 'Image is too large. Maximum size is 10MB.');
                resolve();
                return;
              }
              
              // Check file type
              if (!file.type.startsWith('image/')) {
                Alert.alert('Error', 'Please select an image file.');
                resolve();
                return;
              }
              
              // Convert to base64
              const reader = new FileReader();
              reader.onloadend = () => {
                console.log('[InputBar] Image converted to base64, length:', reader.result?.length);
                const base64data = reader.result;
                const newImages = [...selectedImages, base64data];
                setSelectedImages(newImages);
                if (onImageSelect) {
                  onImageSelect(newImages);
                }
                console.log('[InputBar] Image added to selection, total:', newImages.length);
              };
              reader.onerror = (error) => {
                console.error('[InputBar] FileReader error:', error);
                Alert.alert('Error', 'Failed to read image file.');
                resolve();
              };
              reader.readAsDataURL(file);
            } else {
              console.log('[InputBar] No file selected');
            }
            resolve();
          };
          document.body.appendChild(input);
          input.click();
          // Clean up after a delay
          setTimeout(() => {
            if (document.body.contains(input)) {
              document.body.removeChild(input);
            }
          }, 1000);
        });
      } else {
        // Mobile: use ImagePicker
        if (!ImagePicker) {
          Alert.alert('Error', 'Image picker not available. Please install expo-image-picker: npm install');
          return;
        }
        
        const result = await ImagePicker.launchImageLibraryAsync({
          mediaTypes: ImagePicker.MediaTypeOptions.Images,
          allowsEditing: true,
          quality: 0.8,
          allowsMultipleSelection: false,
        });

        if (!result.canceled && result.assets && result.assets.length > 0) {
          const asset = result.assets[0];
          // Convert to base64
          try {
            const response = await fetch(asset.uri);
            const blob = await response.blob();
            const reader = new FileReader();
            reader.onloadend = () => {
              const base64data = reader.result;
              const newImages = [...selectedImages, base64data];
              setSelectedImages(newImages);
              if (onImageSelect) {
                onImageSelect(newImages);
              }
            };
            reader.onerror = () => {
              Alert.alert('Error', 'Failed to read image file.');
            };
            reader.readAsDataURL(blob);
          } catch (error) {
            console.error('Error converting image to base64:', error);
            Alert.alert('Error', 'Failed to process image. Please try again.');
          }
        }
      }
    } catch (error) {
      console.error('Error picking image:', error);
      Alert.alert('Error', `Failed to pick image: ${error.message || 'Unknown error'}`);
    }
  };

  const uploadImage = async (file) => {
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('user_id', 'anonymous'); // Will be set by parent

      const response = await fetch(`${API_BASE_URL}/api/files/upload`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error('Upload failed');
      }

      const data = await response.json();
      if (data.success && data.data_uri) {
        const newImages = [...selectedImages, data.data_uri];
        setSelectedImages(newImages);
        if (onImageSelect) {
          onImageSelect(newImages);
        }
      }
    } catch (error) {
      console.error('Error uploading image:', error);
      Alert.alert('Error', 'Failed to upload image. Please try again.');
    }
  };

  const removeImage = (index) => {
    const newImages = selectedImages.filter((_, i) => i !== index);
    setSelectedImages(newImages);
    if (onImageSelect) {
      onImageSelect(newImages);
    }
  };

  return (
    <View style={styles.container}>
      {/* Selected Images Preview */}
      {selectedImages.length > 0 && (
        <View style={styles.imagePreviewContainer}>
          {selectedImages.map((imageUri, index) => (
            <View key={index} style={styles.imagePreview}>
              <Image source={{uri: imageUri}} style={styles.previewImage} />
              <TouchableOpacity
                onPress={() => removeImage(index)}
                style={styles.removeImageButton}>
                <Text style={styles.removeImageText}>×</Text>
              </TouchableOpacity>
            </View>
          ))}
        </View>
      )}

      <View style={styles.inputContainer}>
        {/* Image Picker Button */}
        <TouchableOpacity
          onPress={() => {
            console.log('[InputBar] Image button pressed');
            pickImage().catch((error) => {
              console.error('[InputBar] Error in pickImage:', error);
              Alert.alert('Error', `Failed to open image picker: ${error.message || 'Unknown error'}`);
            });
          }}
          disabled={loading}
          style={[styles.imageButton, loading && styles.imageButtonDisabled]}>
          <Text style={styles.imageButtonText}>📷</Text>
        </TouchableOpacity>

        <TextInput
          value={input}
          onChangeText={setInput}
          placeholder="You can ask me anything here..."
          placeholderTextColor={colors.primary[900] + '60'}
          style={styles.input}
          multiline
          maxHeight={100}
          maxLength={1000}
          editable={!loading}
        />

        <TouchableOpacity
          onPress={() => {
            console.log('[InputBar] Send button clicked');
            console.log('[InputBar] onSend function:', typeof onSend);
            onSend();
          }}
          disabled={loading || (!input.trim() && selectedImages.length === 0)}
          style={[
            styles.sendButton,
            (!input.trim() && selectedImages.length === 0 || loading) && styles.sendButtonDisabled,
          ]}>
          <LinearGradient
            colors={[colors.accent[500], colors.accent[600]]}
            style={styles.sendButtonGradient}>
            {loading ? (
              <Text style={styles.sendButtonText}>Sending...</Text>
            ) : (
              <Text style={styles.sendButtonText}>Send</Text>
            )}
          </LinearGradient>
        </TouchableOpacity>

        {showConnectButton && (
          <TouchableOpacity onPress={onConnect} style={styles.connectButton}>
            <LinearGradient
              colors={[colors.secondary[500], colors.secondary[600]]}
              style={styles.connectButtonGradient}>
              <Text style={styles.connectButtonText}>Connect</Text>
            </LinearGradient>
          </TouchableOpacity>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    padding: 12,
    backgroundColor: colors.primary[50],
  },
  imagePreviewContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginBottom: 8,
  },
  imagePreview: {
    position: 'relative',
    width: 60,
    height: 60,
    borderRadius: 8,
    overflow: 'hidden',
    borderWidth: 2,
    borderColor: colors.accent[500],
  },
  previewImage: {
    width: '100%',
    height: '100%',
  },
  removeImageButton: {
    position: 'absolute',
    top: -4,
    right: -4,
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: colors.dark[500],
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 2,
    borderColor: colors.primary[50],
  },
  removeImageText: {
    color: colors.primary[50],
    fontSize: 16,
    fontWeight: 'bold',
    lineHeight: 20,
  },
  inputContainer: {
    flexDirection: 'row',
    gap: 10,
    alignItems: 'center',
  },
  imageButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.secondary[500] + '30',
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.secondary[500] + '60',
    cursor: 'pointer',
  },
  imageButtonDisabled: {
    opacity: 0.5,
  },
  imageButtonText: {
    fontSize: 20,
  },
  input: {
    flex: 1,
    ...commonStyles.input,
    minHeight: 40,
    maxHeight: 100,
    paddingTop: 4,
    paddingBottom: 4,
    borderWidth: 0,
    outlineWidth: 0,
    textAlignVertical: 'center',
  },
  sendButton: {
    borderRadius: 10,
    overflow: 'hidden',
    ...commonStyles.shadowMd,
    alignSelf: 'flex-end',
  },
  sendButtonGradient: {
    paddingHorizontal: 20,
    paddingVertical: 14,
    minWidth: 90,
    minHeight: 48,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendButtonDisabled: {
    opacity: 0.5,
  },
  sendButtonText: {
    ...commonStyles.buttonText,
    fontSize: 16,
  },
  connectButton: {
    borderRadius: 12,
    overflow: 'hidden',
    ...commonStyles.shadowMd,
  },
  connectButtonGradient: {
    paddingHorizontal: 20,
    paddingVertical: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  connectButtonText: {
    ...commonStyles.buttonText,
    fontSize: 16,
  },
});

