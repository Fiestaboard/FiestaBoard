import React, { useMemo, useCallback } from 'react';
import { View, Text, SectionList, Switch, StyleSheet, useColorScheme, TouchableOpacity } from 'react-native';
import { useRouter } from 'expo-router';
import { useServerContext } from '../_layout';
import { usePlugins, useTogglePlugin } from '../../hooks/use-board';
import { colors, spacing, fontSize } from '../../lib/theme';
import { ChevronRight } from 'lucide-react-native';
import type { PluginInfo } from '@fiestaboard/shared';

export default function IntegrationsScreen() {
  const { api } = useServerContext();
  const router = useRouter();
  const colorScheme = useColorScheme();
  const theme = colorScheme === 'dark' ? colors.dark : colors.light;

  const { data: pluginsData } = usePlugins(api);
  const togglePlugin = useTogglePlugin(api);

  const plugins = pluginsData?.plugins || [];

  const sections = useMemo(() => {
    const groups: Record<string, PluginInfo[]> = {};
    for (const plugin of plugins) {
      const cat = plugin.category || 'other';
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(plugin);
    }
    return Object.entries(groups)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([title, data]) => ({
        title: title.charAt(0).toUpperCase() + title.slice(1),
        data,
      }));
  }, [plugins]);

  const handleToggle = useCallback((pluginId: string, enabled: boolean) => {
    togglePlugin.mutate({ pluginId, enabled });
  }, [togglePlugin]);

  return (
    <SectionList
      style={[styles.container, { backgroundColor: theme.background }]}
      contentContainerStyle={styles.content}
      sections={sections}
      keyExtractor={(item) => item.id}
      renderSectionHeader={({ section: { title } }) => (
        <Text style={[styles.sectionHeader, { color: theme.textSecondary }]}>{title}</Text>
      )}
      renderItem={({ item }) => (
        <TouchableOpacity
          style={[styles.pluginRow, { backgroundColor: theme.surface, borderBottomColor: theme.separator }]}
          onPress={() => router.push(`/plugins/${item.id}`)}
          activeOpacity={0.7}
        >
          <View style={styles.pluginInfo}>
            <Text style={[styles.pluginName, { color: theme.text }]}>{item.name}</Text>
            <Text style={[styles.pluginDesc, { color: theme.textSecondary }]} numberOfLines={1}>{item.description}</Text>
          </View>
          <View style={styles.pluginActions}>
            <Switch
              value={item.enabled}
              onValueChange={(v) => handleToggle(item.id, v)}
              trackColor={{ true: colors.primary }}
            />
            <ChevronRight size={18} color={theme.textSecondary} />
          </View>
        </TouchableOpacity>
      )}
      ListEmptyComponent={
        <View style={styles.empty}>
          <Text style={[styles.emptyText, { color: theme.textSecondary }]}>No plugins available</Text>
        </View>
      }
    />
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  content: { paddingBottom: spacing.xl },
  sectionHeader: { fontSize: fontSize.caption, fontWeight: '600', textTransform: 'uppercase', paddingHorizontal: spacing.md, paddingTop: spacing.lg, paddingBottom: spacing.xs },
  pluginRow: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: spacing.md, paddingVertical: 14, borderBottomWidth: StyleSheet.hairlineWidth },
  pluginInfo: { flex: 1, marginRight: spacing.sm },
  pluginName: { fontSize: fontSize.body, fontWeight: '500' },
  pluginDesc: { fontSize: fontSize.caption, marginTop: 2 },
  pluginActions: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  empty: { padding: 40, alignItems: 'center' },
  emptyText: { fontSize: fontSize.body },
});
