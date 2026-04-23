import React from 'react';
import {View, Text, TextInput, TouchableOpacity, StyleSheet, Platform} from 'react-native';
import {Svg, Circle, Line, Path} from 'react-native-svg';
import {theme} from '../styles/theme';

/**
 * Top search bar used on Home (screens 56/57) and Weekly Schedule (screen 85).
 *
 * Props:
 *   placeholder — override placeholder text
 *   leading     — 'search' (default) or 'back'
 *   onLeadingPress — handler when leading == 'back'
 *   value, onChangeText, onSubmit — standard TextInput props
 *   showShortcut — show ⌘K chip on the right (default true)
 */
export default function TopSearchBar({
  placeholder = 'Ask Aivis or search for anything...',
  leading = 'search',
  onLeadingPress,
  value,
  onChangeText,
  onSubmit,
  showShortcut = true,
}) {
  const LeadingIcon = () => {
    if (leading === 'back') {
      return (
        <Svg width={18} height={18} viewBox="0 0 24 24" fill="none">
          <Path
            d="M15 5l-7 7 7 7"
            stroke={theme.colors.textPrimary}
            strokeWidth={1.8}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </Svg>
      );
    }
    return (
      <Svg width={18} height={18} viewBox="0 0 24 24" fill="none">
        <Circle cx="11" cy="11" r="7" stroke={theme.colors.textSecondary} strokeWidth={1.6} />
        <Line
          x1="16.2"
          y1="16.2"
          x2="20"
          y2="20"
          stroke={theme.colors.textSecondary}
          strokeWidth={1.8}
          strokeLinecap="round"
        />
      </Svg>
    );
  };

  const Wrapper = leading === 'back' ? TouchableOpacity : View;
  const wrapperProps = leading === 'back' ? {onPress: onLeadingPress, activeOpacity: 0.8} : {};

  return (
    <View style={styles.row}>
      {leading === 'back' ? (
        <TouchableOpacity onPress={onLeadingPress} style={styles.backCircle} activeOpacity={0.8}>
          <LeadingIcon />
        </TouchableOpacity>
      ) : null}

      <Wrapper {...wrapperProps} style={styles.pill}>
        {leading !== 'back' ? (
          <View style={styles.iconWrap}>
            <LeadingIcon />
          </View>
        ) : null}
        <TextInput
          value={value}
          onChangeText={onChangeText}
          onSubmitEditing={onSubmit}
          placeholder={placeholder}
          placeholderTextColor={theme.colors.textSecondary}
          style={[
            styles.input,
            Platform.OS === 'web' && {outline: 'none', outlineWidth: 0, boxShadow: 'none'},
          ]}
          returnKeyType="search"
        />
        {showShortcut ? (
          <View style={styles.shortcut}>
            <Text style={styles.shortcutText}>⌘K</Text>
          </View>
        ) : null}
      </Wrapper>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: 16,
    paddingTop: 10,
    paddingBottom: 6,
  },
  backCircle: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: theme.colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
    ...theme.shadow.card,
  },
  pill: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: theme.colors.surfaceMuted,
    borderRadius: theme.radius.pill,
    paddingHorizontal: 14,
    height: 40,
  },
  iconWrap: {
    marginRight: 8,
  },
  input: {
    flex: 1,
    fontSize: 14,
    color: theme.colors.textPrimary,
    paddingVertical: 0,
    borderWidth: 0,
  },
  shortcut: {
    marginLeft: 8,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 6,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  shortcutText: {
    fontSize: 11,
    fontWeight: '600',
    color: theme.colors.textSecondary,
  },
});
