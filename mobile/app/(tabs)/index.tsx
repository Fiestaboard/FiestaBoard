import React, { useCallback } from 'react';
import { View, Text, ScrollView, RefreshControl, StyleSheet, useColorScheme, TouchableOpacity } from 'react-native';
import { useRouter } from 'expo-router';
import { useServerContext } from '../_layout';
import { useStatus, useActivePage, usePages, usePagePreview, useBoardSettings, useSilenceStatus, getEffectiveBoardColor } from '../../hooks/use-board';
import { BoardPreview } from '../../components/BoardPreview';
import { StatusIndicator } from '../../components/StatusIndicator';
import { colors, spacing, fontSize } from '../../lib/theme';
import { Moon } from 'lucide-react-native';

export default function DashboardScreen() {
  const { api } = useServerContext();
  const router = useRouter();
  const colorScheme = useColorScheme();
  const isDark = colorScheme === 'dark';
  const theme = isDark ? colors.dark : colors.light;

  const { data: status, refetch: refetchStatus } = useStatus(api);
  const { data: activePageData } = useActivePage(api);
  const { data: pagesData } = usePages(api);
  const { data: boardSettings } = useBoardSettings(api);
  const { data: silenceStatus } = useSilenceStatus(api);

  const activePageId = activePageData?.page_id;
  const activePage = pagesData?.pages?.find((p: any) => p.id === activePageId);
  const { data: preview, refetch: refetchPreview } = usePagePreview(api, activePageId || null, { refetchInterval: 15000 });

  const boardColor = getEffectiveBoardColor(boardSettings);
  const isRunning = status?.running ?? false;
  const isSilenced = silenceStatus?.active ?? false;

  const [refreshing, setRefreshing] = React.useState(false);
  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await Promise.all([refetchStatus(), refetchPreview()]);
    setRefreshing(false);
  }, [refetchStatus, refetchPreview]);

  return (
    <ScrollView
      style={[styles.container, { backgroundColor: theme.background }]}
      contentContainerStyle={styles.content}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
    >
      {/* Board Preview */}
      <View style={[styles.card, { backgroundColor: theme.surface }]}>
        <View style={styles.cardHeader}>
          <Text style={[styles.cardTitle, { color: theme.text }]}>Current Display</Text>
          <StatusIndicator status={isRunning ? 'running' : 'stopped'} label={isRunning ? 'Running' : 'Stopped'} />
        </View>
        <BoardPreview
          content={preview?.lines?.join('\n') || ''}
          deviceType={activePage?.device_type || 'flagship'}
          boardColor={boardColor}
        />
      </View>

      {/* Active Page */}
      <TouchableOpacity
        style={[styles.card, { backgroundColor: theme.surface }]}
        onPress={() => router.push('/pages')}
        activeOpacity={0.7}
      >
        <Text style={[styles.cardTitle, { color: theme.text }]}>Active Page</Text>
        <Text style={[styles.pageTitle, { color: theme.text }]}>{activePage?.name || 'No page selected'}</Text>
        <Text style={[styles.cardSubtitle, { color: theme.textSecondary }]}>Tap to change</Text>
      </TouchableOpacity>

      {/* Silence Mode */}
      {isSilenced && (
        <View style={[styles.card, styles.silenceCard, { backgroundColor: theme.surfaceSecondary }]}>
          <Moon size={18} color={theme.textSecondary} />
          <Text style={[styles.silenceText, { color: theme.textSecondary }]}>Silence mode is active</Text>
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  content: { padding: spacing.md, gap: spacing.md },
  card: {
    borderRadius: 12,
    padding: spacing.md,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
    elevation: 2,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  cardTitle: { fontSize: fontSize.body, fontWeight: '600' },
  cardSubtitle: { fontSize: fontSize.caption, marginTop: 4 },
  pageTitle: { fontSize: fontSize.headline, fontWeight: '700' },
  silenceCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  silenceText: { fontSize: fontSize.body },
});
