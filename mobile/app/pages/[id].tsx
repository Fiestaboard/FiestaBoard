import React from 'react';
import { View, Text, ScrollView, TouchableOpacity, StyleSheet, useColorScheme, Alert } from 'react-native';
import { useLocalSearchParams, Stack } from 'expo-router';
import { useServerContext } from '../_layout';
import { usePages, useActivePage, useSetActivePage, usePagePreview, useBoardSettings, getEffectiveBoardColor } from '../../hooks/use-board';
import { BoardPreview } from '../../components/BoardPreview';
import { colors, spacing, fontSize } from '../../lib/theme';
import { Check, Send } from 'lucide-react-native';

export default function PageDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { api } = useServerContext();
  const colorScheme = useColorScheme();
  const theme = colorScheme === 'dark' ? colors.dark : colors.light;

  const { data: pagesData } = usePages(api);
  const { data: activePageData } = useActivePage(api);
  const { data: boardSettings } = useBoardSettings(api);
  const { data: preview } = usePagePreview(api, id || null);
  const setActiveMutation = useSetActivePage(api);

  const page = pagesData?.pages?.find((p: any) => p.id === id);
  const isActive = activePageData?.page_id === id;
  const boardColor = getEffectiveBoardColor(boardSettings);

  const handleSetActive = async () => {
    if (!id) return;
    try {
      await setActiveMutation.mutateAsync(id);
      Alert.alert('Success', `"${page?.name}" is now the active page`);
    } catch {
      Alert.alert('Error', 'Failed to set active page');
    }
  };

  const handleSendToBoard = async () => {
    if (!api || !id) return;
    try {
      await api.sendPage(id);
      Alert.alert('Sent', 'Page sent to board');
    } catch {
      Alert.alert('Error', 'Failed to send page to board');
    }
  };

  if (!page) {
    return (
      <View style={[styles.container, { backgroundColor: theme.background }]}>
        <Text style={[styles.emptyText, { color: theme.textSecondary }]}>Page not found</Text>
      </View>
    );
  }

  return (
    <>
      <Stack.Screen options={{ headerTitle: page.name }} />
      <ScrollView style={[styles.container, { backgroundColor: theme.background }]} contentContainerStyle={styles.content}>
        <BoardPreview
          content={preview?.lines?.join('\n') || ''}
          deviceType={page.device_type || 'flagship'}
          boardColor={boardColor}
        />

        <View style={[styles.card, { backgroundColor: theme.surface }]}>
          <View style={styles.metaRow}>
            <Text style={[styles.metaLabel, { color: theme.textSecondary }]}>Type</Text>
            <Text style={[styles.metaValue, { color: theme.text }]}>{page.type}</Text>
          </View>
          <View style={styles.metaRow}>
            <Text style={[styles.metaLabel, { color: theme.textSecondary }]}>Device</Text>
            <Text style={[styles.metaValue, { color: theme.text }]}>{page.device_type || 'flagship'}</Text>
          </View>
          <View style={styles.metaRow}>
            <Text style={[styles.metaLabel, { color: theme.textSecondary }]}>Duration</Text>
            <Text style={[styles.metaValue, { color: theme.text }]}>{page.duration_seconds}s</Text>
          </View>
        </View>

        <View style={styles.actions}>
          <TouchableOpacity
            style={[styles.actionButton, { backgroundColor: isActive ? theme.surfaceSecondary : colors.primary }]}
            onPress={handleSetActive}
            disabled={isActive}
            activeOpacity={0.8}
          >
            <Check size={18} color={isActive ? theme.textSecondary : '#fff'} />
            <Text style={[styles.actionText, { color: isActive ? theme.textSecondary : '#fff' }]}>
              {isActive ? 'Active' : 'Set Active'}
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.actionButton, { backgroundColor: theme.surface }]}
            onPress={handleSendToBoard}
            activeOpacity={0.8}
          >
            <Send size={18} color={colors.primary} />
            <Text style={[styles.actionText, { color: colors.primary }]}>Send to Board</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  content: { padding: spacing.md, gap: spacing.md },
  card: { borderRadius: 12, padding: spacing.md },
  metaRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 8 },
  metaLabel: { fontSize: fontSize.body },
  metaValue: { fontSize: fontSize.body, fontWeight: '500' },
  actions: { flexDirection: 'row', gap: spacing.sm },
  actionButton: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, borderRadius: 10, padding: 14, shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.1, shadowRadius: 2, elevation: 2 },
  actionText: { fontSize: fontSize.body, fontWeight: '600' },
  emptyText: { fontSize: fontSize.body, textAlign: 'center', padding: 40 },
});
