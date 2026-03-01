import React from 'react';
import { View, Text, StyleSheet, useColorScheme } from 'react-native';
import { colors } from '../lib/theme';

interface StatusIndicatorProps {
  status: 'running' | 'stopped' | 'error' | 'loading';
  label?: string;
  size?: number;
}

export function StatusIndicator({ status, label, size = 10 }: StatusIndicatorProps) {
  const colorScheme = useColorScheme();
  const theme = colorScheme === 'dark' ? colors.dark : colors.light;

  const dotColor = {
    running: theme.success,
    stopped: theme.textSecondary,
    error: theme.destructive,
    loading: theme.textSecondary,
  }[status];

  return (
    <View style={styles.container} testID={`status-${status}`}>
      <View style={[styles.dot, { width: size, height: size, borderRadius: size / 2, backgroundColor: dotColor }]} />
      {label && <Text style={[styles.label, { color: theme.text }]}>{label}</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  dot: {},
  label: {
    fontSize: 14,
    fontWeight: '500',
  },
});
