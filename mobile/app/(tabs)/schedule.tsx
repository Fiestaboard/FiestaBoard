import React, { useCallback, useState } from 'react';
import { View, Text, ScrollView, Switch, StyleSheet, useColorScheme, RefreshControl, TouchableOpacity, Alert } from 'react-native';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useServerContext } from '../_layout';
import { useSchedules, useScheduleEnabled, usePages, queryKeys } from '../../hooks/use-board';
import { colors, spacing, fontSize } from '../../lib/theme';
import { Clock, Trash2 } from 'lucide-react-native';
import type { ScheduleEntry } from '@fiestaboard/shared';

function formatDays(schedule: ScheduleEntry): string {
  if (schedule.day_pattern === 'all') return 'Every day';
  if (schedule.day_pattern === 'weekdays') return 'Mon-Fri';
  if (schedule.day_pattern === 'weekends') return 'Sat-Sun';
  if (schedule.day_pattern === 'custom' && schedule.custom_days) {
    return schedule.custom_days.map((d) => d.slice(0, 3)).join(', ');
  }
  return '';
}

export default function ScheduleScreen() {
  const { api } = useServerContext();
  const colorScheme = useColorScheme();
  const theme = colorScheme === 'dark' ? colors.dark : colors.light;
  const queryClient = useQueryClient();

  const { data: schedulesData, refetch } = useSchedules(api);
  const { data: enabledData } = useScheduleEnabled(api);
  const { data: pagesData } = usePages(api);

  const schedules = schedulesData?.schedules || [];
  const pages = pagesData?.pages || [];
  const isEnabled = enabledData?.enabled ?? false;

  const toggleMutation = useMutation({
    mutationFn: (enabled: boolean) => api!.setScheduleEnabled(enabled),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.scheduleEnabled });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api!.deleteSchedule(id),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.schedules });
    },
  });

  const getPageName = (pageId: string) => pages.find((p) => p.id === pageId)?.name || 'Unknown';

  const handleDelete = (id: string) => {
    Alert.alert('Delete Schedule', 'Are you sure?', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Delete', style: 'destructive', onPress: () => deleteMutation.mutate(id) },
    ]);
  };

  const [refreshing, setRefreshing] = useState(false);
  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await refetch();
    setRefreshing(false);
  }, [refetch]);

  return (
    <ScrollView
      style={[styles.container, { backgroundColor: theme.background }]}
      contentContainerStyle={styles.content}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
    >
      {/* Schedule Toggle */}
      <View style={[styles.card, { backgroundColor: theme.surface }]}>
        <View style={styles.toggleRow}>
          <Text style={[styles.toggleLabel, { color: theme.text }]}>Schedule Enabled</Text>
          <Switch
            value={isEnabled}
            onValueChange={(v) => toggleMutation.mutate(v)}
            trackColor={{ true: colors.primary }}
          />
        </View>
      </View>

      {/* Schedule Entries */}
      <View style={[styles.card, { backgroundColor: theme.surface }]}>
        <Text style={[styles.sectionTitle, { color: theme.text }]}>Schedule Entries</Text>
        {schedules.length === 0 ? (
          <View style={styles.empty}>
            <Clock size={32} color={theme.textSecondary} />
            <Text style={[styles.emptyText, { color: theme.textSecondary }]}>No schedules yet</Text>
          </View>
        ) : (
          schedules.map((entry) => (
            <View key={entry.id} style={[styles.entryRow, { borderBottomColor: theme.separator }]}>
              <View style={styles.entryInfo}>
                <Text style={[styles.entryPage, { color: theme.text }]}>{getPageName(entry.page_id)}</Text>
                <Text style={[styles.entryTime, { color: theme.textSecondary }]}>
                  {entry.start_time} – {entry.end_time} · {formatDays(entry)}
                </Text>
              </View>
              <TouchableOpacity onPress={() => handleDelete(entry.id)} hitSlop={8}>
                <Trash2 size={18} color={theme.destructive} />
              </TouchableOpacity>
            </View>
          ))
        )}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  content: { padding: spacing.md, gap: spacing.md },
  card: { borderRadius: 12, padding: spacing.md },
  toggleRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  toggleLabel: { fontSize: fontSize.body, fontWeight: '600' },
  sectionTitle: { fontSize: fontSize.body, fontWeight: '600', marginBottom: spacing.sm },
  entryRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 12, borderBottomWidth: StyleSheet.hairlineWidth },
  entryInfo: { flex: 1 },
  entryPage: { fontSize: fontSize.body, fontWeight: '500' },
  entryTime: { fontSize: fontSize.caption, marginTop: 2 },
  empty: { padding: 32, alignItems: 'center', gap: 8 },
  emptyText: { fontSize: fontSize.body },
});
