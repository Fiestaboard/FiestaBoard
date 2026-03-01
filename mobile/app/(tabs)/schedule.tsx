import React, { useCallback, useState, useMemo } from 'react';
import { View, Text, ScrollView, Switch, StyleSheet, useColorScheme, RefreshControl, TouchableOpacity, Alert, Dimensions } from 'react-native';
import { Calendar } from 'react-native-big-calendar';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { startOfWeek, addDays, format } from 'date-fns';
import { useServerContext } from '../_layout';
import { useSchedules, useScheduleEnabled, usePages, queryKeys } from '../../hooks/use-board';
import { colors, spacing, fontSize } from '../../lib/theme';
import { Clock, Trash2, CalendarDays, List } from 'lucide-react-native';
import type { ScheduleEntry, Page } from '@fiestaboard/shared';

// Color palette for schedule events
const EVENT_COLORS = [
  '#4a90d9', '#e74c3c', '#27ae60', '#f39c12', '#9b59b6',
  '#1abc9c', '#e67e22', '#2ecc71', '#3498db', '#e91e63',
];

function getEventColor(id: string): string {
  let hash = 0;
  for (let i = 0; i < id.length; i++) {
    hash = ((hash << 5) - hash + id.charCodeAt(i)) | 0;
  }
  return EVENT_COLORS[Math.abs(hash) % EVENT_COLORS.length];
}

function formatDays(schedule: ScheduleEntry): string {
  if (schedule.day_pattern === 'all') return 'Every day';
  if (schedule.day_pattern === 'weekdays') return 'Mon–Fri';
  if (schedule.day_pattern === 'weekends') return 'Sat–Sun';
  if (schedule.day_pattern === 'custom' && schedule.custom_days) {
    return schedule.custom_days.map((d) => d.slice(0, 3)).join(', ');
  }
  return '';
}

function getDaysForPattern(schedule: ScheduleEntry, weekStart: Date): number[] {
  switch (schedule.day_pattern) {
    case 'all': return [0, 1, 2, 3, 4, 5, 6];
    case 'weekdays': return [1, 2, 3, 4, 5];
    case 'weekends': return [0, 6];
    case 'custom': {
      const dayMap: Record<string, number> = {
        sunday: 0, monday: 1, tuesday: 2, wednesday: 3,
        thursday: 4, friday: 5, saturday: 6,
      };
      return (schedule.custom_days || []).map((d) => dayMap[d.toLowerCase()] ?? -1).filter((d) => d >= 0);
    }
    default: return [0, 1, 2, 3, 4, 5, 6];
  }
}

interface CalendarEventItem {
  title: string;
  start: Date;
  end: Date;
  color?: string;
  scheduleId: string;
}

function schedulesToEvents(schedules: ScheduleEntry[], pages: Page[]): CalendarEventItem[] {
  const weekStart = startOfWeek(new Date(), { weekStartsOn: 0 });
  const events: CalendarEventItem[] = [];

  for (const schedule of schedules) {
    if (!schedule.enabled) continue;

    const pageName = pages.find((p) => p.id === schedule.page_id)?.name || 'Unknown';
    const [startH, startM] = schedule.start_time.split(':').map(Number);
    const [endH, endM] = schedule.end_time.split(':').map(Number);
    const color = getEventColor(schedule.id);
    const days = getDaysForPattern(schedule, weekStart);

    for (const dayOffset of days) {
      const dayDate = addDays(weekStart, dayOffset);
      const start = new Date(dayDate);
      start.setHours(startH, startM, 0, 0);
      const end = new Date(dayDate);
      end.setHours(endH, endM, 0, 0);

      // Handle overnight schedules
      if (end <= start) {
        end.setDate(end.getDate() + 1);
      }

      events.push({
        title: pageName,
        start,
        end,
        color,
        scheduleId: schedule.id,
      });
    }
  }

  return events;
}

type ViewMode = 'calendar' | 'list';

export default function ScheduleScreen() {
  const { api } = useServerContext();
  const colorScheme = useColorScheme();
  const isDark = colorScheme === 'dark';
  const theme = isDark ? colors.dark : colors.light;
  const queryClient = useQueryClient();

  const { data: schedulesData, refetch } = useSchedules(api);
  const { data: enabledData } = useScheduleEnabled(api);
  const { data: pagesData } = usePages(api);

  const schedules = schedulesData?.schedules || [];
  const pages = pagesData?.pages || [];
  const isEnabled = enabledData?.enabled ?? false;
  const [viewMode, setViewMode] = useState<ViewMode>('calendar');

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

  const calendarEvents = useMemo(() => schedulesToEvents(schedules, pages), [schedules, pages]);

  const [refreshing, setRefreshing] = useState(false);
  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await refetch();
    setRefreshing(false);
  }, [refetch]);

  const screenHeight = Dimensions.get('window').height;

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

      {/* View Mode Toggle */}
      <View style={styles.viewToggle}>
        <TouchableOpacity
          style={[styles.viewToggleButton, viewMode === 'calendar' && { backgroundColor: colors.primary }]}
          onPress={() => setViewMode('calendar')}
        >
          <CalendarDays size={16} color={viewMode === 'calendar' ? '#fff' : theme.textSecondary} />
          <Text style={[styles.viewToggleText, { color: viewMode === 'calendar' ? '#fff' : theme.textSecondary }]}>Calendar</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.viewToggleButton, viewMode === 'list' && { backgroundColor: colors.primary }]}
          onPress={() => setViewMode('list')}
        >
          <List size={16} color={viewMode === 'list' ? '#fff' : theme.textSecondary} />
          <Text style={[styles.viewToggleText, { color: viewMode === 'list' ? '#fff' : theme.textSecondary }]}>List</Text>
        </TouchableOpacity>
      </View>

      {/* Calendar View */}
      {viewMode === 'calendar' && (
        <View style={[styles.calendarContainer, { backgroundColor: theme.surface, height: screenHeight * 0.6 }]}>
          <Calendar
            events={calendarEvents}
            height={screenHeight * 0.6}
            mode="week"
            weekStartsOn={0}
            eventCellStyle={(event) => ({
              backgroundColor: (event as CalendarEventItem).color || colors.primary,
              borderRadius: 4,
            })}
            theme={{
              palette: {
                primary: {
                  main: colors.primary,
                  contrastText: '#fff',
                },
                gray: {
                  '200': theme.separator,
                  '500': theme.textSecondary,
                  '800': theme.text,
                },
              },
              typography: {
                fontFamily: undefined,
                xs: { fontSize: 10, fontWeight: '400' as const },
                sm: { fontSize: 12, fontWeight: '500' as const },
                xl: { fontSize: 18, fontWeight: '600' as const },
              },
            }}
            swipeEnabled
            showTime
          />
        </View>
      )}

      {/* List View */}
      {viewMode === 'list' && (
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
                <View style={[styles.entryColor, { backgroundColor: getEventColor(entry.id) }]} />
                <View style={styles.entryInfo}>
                  <Text style={[styles.entryPage, { color: theme.text }]}>{getPageName(entry.page_id)}</Text>
                  <Text style={[styles.entryTime, { color: theme.textSecondary }]}>
                    {entry.start_time} – {entry.end_time} · {formatDays(entry)}
                  </Text>
                  {!entry.enabled && (
                    <Text style={[styles.entryDisabled, { color: theme.warning }]}>Disabled</Text>
                  )}
                </View>
                <TouchableOpacity onPress={() => handleDelete(entry.id)} hitSlop={8}>
                  <Trash2 size={18} color={theme.destructive} />
                </TouchableOpacity>
              </View>
            ))
          )}
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  content: { padding: spacing.md, gap: spacing.md, paddingBottom: spacing.xl },
  card: { borderRadius: 12, padding: spacing.md },
  toggleRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  toggleLabel: { fontSize: fontSize.body, fontWeight: '600' },
  viewToggle: { flexDirection: 'row', gap: spacing.xs, alignSelf: 'center' },
  viewToggleButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 8,
  },
  viewToggleText: { fontSize: fontSize.caption, fontWeight: '600' },
  calendarContainer: { borderRadius: 12, overflow: 'hidden' },
  sectionTitle: { fontSize: fontSize.body, fontWeight: '600', marginBottom: spacing.sm },
  entryRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 12,
    borderBottomWidth: StyleSheet.hairlineWidth,
    gap: spacing.sm,
  },
  entryColor: { width: 4, height: 32, borderRadius: 2 },
  entryInfo: { flex: 1 },
  entryPage: { fontSize: fontSize.body, fontWeight: '500' },
  entryTime: { fontSize: fontSize.caption, marginTop: 2 },
  entryDisabled: { fontSize: fontSize.caption, marginTop: 2, fontStyle: 'italic' },
  empty: { padding: 32, alignItems: 'center', gap: 8 },
  emptyText: { fontSize: fontSize.body },
});
