import React from 'react';
import {View, TouchableOpacity, StyleSheet} from 'react-native';
import {Svg, Path, Circle, Line, Rect} from 'react-native-svg';
import {theme} from '../styles/theme';

/**
 * Bottom navigation matching Figma screens 56/57/85:
 *  - Left: small circular pill (stats/week)
 *  - Center: large circular pill (primary action)
 *  - Right: small circular pill (menu)
 *
 * Any icon can be overridden via props; defaults are:
 *   left   = stats, center = plus, right = menu
 */
export default function BottomNav({
  leftIcon = 'stats',
  centerIcon = 'plus',
  rightIcon = 'menu',
  onLeft,
  onCenter,
  onRight,
}) {
  return (
    <View style={styles.wrap} pointerEvents="box-none">
      <View style={styles.row}>
        <TouchableOpacity
          activeOpacity={0.8}
          onPress={onLeft}
          style={styles.sideBtn}
          hitSlop={{top: 8, bottom: 8, left: 8, right: 8}}>
          <NavIcon name={leftIcon} size={22} />
        </TouchableOpacity>

        <TouchableOpacity
          activeOpacity={0.85}
          onPress={onCenter}
          style={styles.centerBtn}
          hitSlop={{top: 8, bottom: 8, left: 8, right: 8}}>
          <NavIcon name={centerIcon} size={28} />
        </TouchableOpacity>

        <TouchableOpacity
          activeOpacity={0.8}
          onPress={onRight}
          style={styles.sideBtn}
          hitSlop={{top: 8, bottom: 8, left: 8, right: 8}}>
          <NavIcon name={rightIcon} size={22} />
        </TouchableOpacity>
      </View>
    </View>
  );
}

function NavIcon({name, size = 22}) {
  const stroke = theme.colors.textPrimary;
  const s = size;
  switch (name) {
    case 'home':
      return (
        <Svg width={s} height={s} viewBox="0 0 24 24" fill="none">
          <Path
            d="M4 11.5L12 5l8 6.5V19a1 1 0 0 1-1 1h-4v-6h-6v6H5a1 1 0 0 1-1-1v-7.5z"
            stroke={stroke}
            strokeWidth={1.6}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        </Svg>
      );
    case 'stats':
      return (
        <Svg width={s} height={s} viewBox="0 0 24 24" fill="none">
          <Line x1="5" y1="19" x2="5" y2="11" stroke={stroke} strokeWidth={1.8} strokeLinecap="round" />
          <Line x1="12" y1="19" x2="12" y2="6" stroke={stroke} strokeWidth={1.8} strokeLinecap="round" />
          <Line x1="19" y1="19" x2="19" y2="14" stroke={stroke} strokeWidth={1.8} strokeLinecap="round" />
        </Svg>
      );
    case 'plus':
      return (
        <Svg width={s} height={s} viewBox="0 0 24 24" fill="none">
          <Line x1="12" y1="5" x2="12" y2="19" stroke={stroke} strokeWidth={1.8} strokeLinecap="round" />
          <Line x1="5" y1="12" x2="19" y2="12" stroke={stroke} strokeWidth={1.8} strokeLinecap="round" />
        </Svg>
      );
    case 'menu':
      return (
        <Svg width={s} height={s} viewBox="0 0 24 24" fill="none">
          <Line x1="4" y1="7" x2="20" y2="7" stroke={stroke} strokeWidth={1.8} strokeLinecap="round" />
          <Line x1="4" y1="12" x2="20" y2="12" stroke={stroke} strokeWidth={1.8} strokeLinecap="round" />
          <Line x1="4" y1="17" x2="20" y2="17" stroke={stroke} strokeWidth={1.8} strokeLinecap="round" />
        </Svg>
      );
    case 'back':
      return (
        <Svg width={s} height={s} viewBox="0 0 24 24" fill="none">
          <Path
            d="M15 5l-7 7 7 7"
            stroke={stroke}
            strokeWidth={1.8}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </Svg>
      );
    default:
      return (
        <Svg width={s} height={s} viewBox="0 0 24 24" fill="none">
          <Circle cx="12" cy="12" r="4" stroke={stroke} strokeWidth={1.6} />
        </Svg>
      );
  }
}

const BTN_SIZE = 56;
const CENTER_SIZE = 68;

const styles = StyleSheet.create({
  wrap: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    paddingHorizontal: 24,
    paddingBottom: 32,
    paddingTop: 8,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  sideBtn: {
    width: BTN_SIZE,
    height: BTN_SIZE,
    borderRadius: BTN_SIZE / 2,
    backgroundColor: theme.colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
    ...theme.shadow.card,
  },
  centerBtn: {
    width: CENTER_SIZE,
    height: CENTER_SIZE,
    borderRadius: CENTER_SIZE / 2,
    backgroundColor: theme.colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
    ...theme.shadow.float,
  },
});
