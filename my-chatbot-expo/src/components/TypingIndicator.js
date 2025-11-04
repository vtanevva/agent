import React from 'react';
import {View, Text, StyleSheet, Animated} from 'react-native';
import {LinearGradient} from 'expo-linear-gradient';
import {colors} from '../styles/colors';

export default function TypingIndicator() {
  const dot1 = React.useRef(new Animated.Value(0)).current;
  const dot2 = React.useRef(new Animated.Value(0)).current;
  const dot3 = React.useRef(new Animated.Value(0)).current;

  React.useEffect(() => {
    const animateDot = (dot, delay) => {
      return Animated.loop(
        Animated.sequence([
          Animated.delay(delay),
          Animated.timing(dot, {
            toValue: 1,
            duration: 400,
            useNativeDriver: true,
          }),
          Animated.timing(dot, {
            toValue: 0,
            duration: 400,
            useNativeDriver: true,
          }),
        ]),
      );
    };

    const anim1 = animateDot(dot1, 0);
    const anim2 = animateDot(dot2, 200);
    const anim3 = animateDot(dot3, 400);

    Animated.parallel([anim1, anim2, anim3]).start();

    return () => {
      anim1.stop();
      anim2.stop();
      anim3.stop();
    };
  }, []);

  const translateY1 = dot1.interpolate({
    inputRange: [0, 1],
    outputRange: [0, -8],
  });
  const translateY2 = dot2.interpolate({
    inputRange: [0, 1],
    outputRange: [0, -8],
  });
  const translateY3 = dot3.interpolate({
    inputRange: [0, 1],
    outputRange: [0, -8],
  });

  return (
    <View style={styles.container}>
      <LinearGradient
        colors={[colors.secondary[500] + '40', colors.dark[500] + '40']}
        style={styles.bubble}>
        <View style={styles.content}>
          <View style={styles.avatar}>
            <Text style={styles.avatarText}>AI</Text>
          </View>
          <View style={styles.dots}>
            <Animated.View
              style={[
                styles.dot,
                {transform: [{translateY: translateY1}]},
              ]}
            />
            <Animated.View
              style={[
                styles.dot,
                {transform: [{translateY: translateY2}]},
              ]}
            />
            <Animated.View
              style={[
                styles.dot,
                {transform: [{translateY: translateY3}]},
              ]}
            />
          </View>
        </View>
      </LinearGradient>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: 'flex-start',
    marginVertical: 8,
  },
  bubble: {
    maxWidth: 120,
    borderRadius: 16,
    padding: 12,
    marginLeft: 12,
  },
  content: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  avatar: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: colors.secondary[500],
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarText: {
    color: colors.primary[50],
    fontSize: 12,
    fontWeight: '600',
  },
  dots: {
    flexDirection: 'row',
    gap: 4,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.secondary[500],
  },
});

