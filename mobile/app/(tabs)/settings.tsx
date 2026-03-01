import React from 'react';
import { View, Text, ScrollView, Switch, StyleSheet, useColorScheme, TouchableOpacity, Alert, Linking } from 'react-native';
import { useRouter } from 'expo-router';
import { useServerContext } from '../_layout';
import { useStatus, useVersion, useGeneralConfig, useBoardSettings, useToggleDevMode } from '../../hooks/use-board';
import { StatusIndicator } from '../../components/StatusIndicator';
import { colors, spacing, fontSize } from '../../lib/theme';
import { ChevronRight } from 'lucide-react-native';

function SettingsSection({ title, children }: { title: string; children: React.ReactNode }) {
  const colorScheme = useColorScheme();
  const theme = colorScheme === 'dark' ? colors.dark : colors.light;
  return (
    <View style={styles.section}>
      <Text style={[styles.sectionTitle, { color: theme.textSecondary }]}>{title}</Text>
      <View style={[styles.sectionContent, { backgroundColor: theme.surface }]}>{children}</View>
    </View>
  );
}

function SettingsRow({ label, value, onPress, accessory }: { label: string; value?: string; onPress?: () => void; accessory?: React.ReactNode }) {
  const colorScheme = useColorScheme();
  const theme = colorScheme === 'dark' ? colors.dark : colors.light;
  const Container = onPress ? TouchableOpacity : View;
  return (
    <Container style={[styles.row, { borderBottomColor: theme.separator }]} onPress={onPress} activeOpacity={0.7}>
      <Text style={[styles.rowLabel, { color: theme.text }]}>{label}</Text>
      <View style={styles.rowRight}>
        {value && <Text style={[styles.rowValue, { color: theme.textSecondary }]}>{value}</Text>}
        {accessory}
        {onPress && <ChevronRight size={16} color={theme.textSecondary} />}
      </View>
    </Container>
  );
}

export default function SettingsScreen() {
  const { api, serverUrl, connected, disconnect } = useServerContext();
  const router = useRouter();
  const colorScheme = useColorScheme();
  const theme = colorScheme === 'dark' ? colors.dark : colors.light;

  const { data: status } = useStatus(api);
  const { data: version } = useVersion(api);
  const { data: generalConfig } = useGeneralConfig(api);
  const { data: boardSettings } = useBoardSettings(api);
  const devModeMutation = useToggleDevMode(api);

  const isRunning = status?.running ?? false;
  const devMode = status?.config_summary?.dev_mode ?? false;

  const handleDisconnect = () => {
    Alert.alert('Disconnect', 'Remove this server connection?', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Disconnect', style: 'destructive', onPress: async () => { await disconnect(); router.replace('/connect'); } },
    ]);
  };

  return (
    <ScrollView style={[styles.container, { backgroundColor: theme.background }]} contentContainerStyle={styles.content} testID="settings-screen">
      <SettingsSection title="SERVER">
        <SettingsRow label="Server URL" value={serverUrl || 'Not configured'} />
        <SettingsRow
          label="Connection"
          accessory={<StatusIndicator status={connected ? 'running' : 'error'} label={connected ? 'Connected' : 'Disconnected'} size={8} />}
        />
        <SettingsRow label="Change Server" onPress={() => router.push('/connect')} />
        <SettingsRow label="Disconnect" onPress={handleDisconnect} />
      </SettingsSection>

      <SettingsSection title="GENERAL">
        <SettingsRow label="Timezone" value={generalConfig?.timezone || '—'} />
        <SettingsRow label="Refresh Interval" value={generalConfig ? `${generalConfig.refresh_interval_seconds}s` : '—'} />
        <SettingsRow label="Output Target" value={generalConfig?.output_target || '—'} />
      </SettingsSection>

      <SettingsSection title="BOARDS">
        {(boardSettings?.boards || []).map((board) => (
          <SettingsRow key={board.id} label={board.name || board.id} value={`${board.device_type} · ${board.api_mode}`} />
        ))}
        {(!boardSettings?.boards || boardSettings.boards.length === 0) && (
          <SettingsRow label="No boards configured" />
        )}
      </SettingsSection>

      <SettingsSection title="SERVICE">
        <SettingsRow
          label="Status"
          accessory={<StatusIndicator status={isRunning ? 'running' : 'stopped'} label={isRunning ? 'Running' : 'Stopped'} size={8} />}
        />
        <SettingsRow
          label="Dev Mode"
          accessory={
            <Switch
              value={devMode}
              onValueChange={(v) => devModeMutation.mutate(v)}
              trackColor={{ true: colors.primary }}
            />
          }
        />
      </SettingsSection>

      <SettingsSection title="ABOUT">
        <SettingsRow label="App Version" value="1.0.0" />
        <SettingsRow label="Server Version" value={version?.package_version ? `v${version.package_version}` : '—'} />
        <SettingsRow label="Website" onPress={() => Linking.openURL('https://fiestaboard.app')} />
        <SettingsRow label="Discord" onPress={() => Linking.openURL('https://discord.gg/ujasGntNhQ')} />
      </SettingsSection>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  content: { paddingBottom: spacing.xl },
  section: { marginTop: spacing.lg },
  sectionTitle: { fontSize: fontSize.caption, fontWeight: '600', textTransform: 'uppercase', paddingHorizontal: spacing.md, marginBottom: spacing.xs },
  sectionContent: { borderRadius: 12, marginHorizontal: spacing.md, overflow: 'hidden' },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: spacing.md, paddingVertical: 14, borderBottomWidth: StyleSheet.hairlineWidth },
  rowLabel: { fontSize: fontSize.body },
  rowRight: { flexDirection: 'row', alignItems: 'center', gap: 6, flexShrink: 1 },
  rowValue: { fontSize: fontSize.body, textAlign: 'right' },
});
