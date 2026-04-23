// Design tokens tuned to match the Aivis Figma prototype (screens 56 / 57 / 85).
// Prefer importing from here over hard-coded hex values in new screens/components.

export const theme = {
  colors: {
    // Surfaces
    bg: '#F3F3F2',           // app background (warm off-white)
    surface: '#FFFFFF',      // cards / bubbles
    surfaceMuted: '#ECECEA', // search bar, chips
    surfaceAlt: '#F7F7F5',

    // Borders / hairlines
    border: 'rgba(17, 17, 17, 0.08)',
    borderStrong: 'rgba(17, 17, 17, 0.14)',

    // Text
    textPrimary: '#111111',
    textSecondary: 'rgba(17, 17, 17, 0.55)',
    textMuted: 'rgba(17, 17, 17, 0.40)',
    textOnDark: '#FFFFFF',

    // Accent dot palette for task bullets (muted pastels)
    dot: {
      orange: '#E8A464',
      pink: '#D98CA0',
      blue: '#7FA3C9',
      yellow: '#D9B85E',
      green: '#8FB07F',
      lavender: '#A79AC3',
    },

    // Calendar event fills (very soft pastels, high alpha so text is readable on light bg)
    event: {
      lavenderBg: '#DCE3F2',
      lavenderBorder: '#B7C2DC',
      sageBg: '#D7E6CE',
      sageBorder: '#AEC99E',
      peachBg: '#F4DDCB',
      peachBorder: '#DEBA9C',
      blushBg: '#F1D4D9',
      blushBorder: '#D8A8B1',
    },

    // Weekly schedule: fixed meaning (meetings / email tasks / chat tasks)
    schedule: {
      meetingBg: '#D4E8FA',
      meetingBorder: '#5B8EC9',
      emailTaskBg: '#D4ECD8',
      emailTaskBorder: '#5A9B63',
      chatTaskBg: '#F7DCC4',
      chatTaskBorder: '#D97A3C',
      otherTaskBg: '#E6E6E4',
      otherTaskBorder: '#A8A8A6',
    },
  },

  radius: {
    sm: 8,
    md: 12,
    lg: 16,
    xl: 20,
    pill: 999,
  },

  spacing: {
    xs: 4,
    sm: 8,
    md: 12,
    lg: 16,
    xl: 24,
    xxl: 32,
  },

  fonts: {
    regular: 'Inter_400Regular',
    medium: 'Inter_500Medium',
    semibold: 'Inter_600SemiBold',
    bold: 'Inter_700Bold',
  },

  type: {
    // Display greeting ("Good afternoon, Alex")
    display: {fontSize: 28, fontFamily: 'Inter_600SemiBold', letterSpacing: -0.3},
    // Section header ("Needs your attention (7)")
    sectionHeader: {fontSize: 14, fontFamily: 'Inter_600SemiBold'},
    // Task title inside card
    cardTitle: {fontSize: 15, fontFamily: 'Inter_600SemiBold'},
    cardSubtitle: {fontSize: 12, fontFamily: 'Inter_500Medium'},
    // Pill action chip text
    chip: {fontSize: 13, fontFamily: 'Inter_500Medium'},
    // Search placeholder
    searchPlaceholder: {fontSize: 14, fontFamily: 'Inter_400Regular'},
    // Timeline hour labels
    hourLabel: {fontSize: 11, fontFamily: 'Inter_500Medium'},
    // Event block title
    eventTitle: {fontSize: 11, fontFamily: 'Inter_600SemiBold'},
  },

  // Very soft, almost-imperceptible shadow (Figma uses subtle diffusion)
  shadow: {
    card: {
      shadowColor: '#000',
      shadowOffset: {width: 0, height: 1},
      shadowOpacity: 0.04,
      shadowRadius: 4,
      elevation: 2,
    },
    float: {
      shadowColor: '#000',
      shadowOffset: {width: 0, height: 4},
      shadowOpacity: 0.08,
      shadowRadius: 12,
      elevation: 6,
    },
  },
};

// Deterministic dot color picker for a task id/title so colors are stable across renders.
export function pickDotColor(seed = '') {
  const palette = [
    theme.colors.dot.orange,
    theme.colors.dot.pink,
    theme.colors.dot.blue,
    theme.colors.dot.yellow,
    theme.colors.dot.green,
    theme.colors.dot.lavender,
  ];
  let h = 0;
  for (let i = 0; i < String(seed).length; i++) {
    h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  }
  return palette[h % palette.length];
}

// Deterministic pastel event palette pair.
export function pickEventColor(seed = '') {
  const palette = [
    {bg: theme.colors.event.lavenderBg, border: theme.colors.event.lavenderBorder},
    {bg: theme.colors.event.sageBg, border: theme.colors.event.sageBorder},
    {bg: theme.colors.event.peachBg, border: theme.colors.event.peachBorder},
    {bg: theme.colors.event.blushBg, border: theme.colors.event.blushBorder},
  ];
  let h = 0;
  for (let i = 0; i < String(seed).length; i++) {
    h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  }
  return palette[h % palette.length];
}
