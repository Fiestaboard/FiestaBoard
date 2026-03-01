import React, { useState, useEffect } from 'react';
import { View, Text, ScrollView, Switch, TextInput, TouchableOpacity, StyleSheet, useColorScheme, Alert, ActivityIndicator } from 'react-native';
import { useLocalSearchParams, Stack } from 'expo-router';
import { useServerContext } from '../_layout';
import { usePlugin, usePluginManifest, useTogglePlugin, useUpdatePluginConfig } from '../../hooks/use-board';
import { colors, spacing, fontSize } from '../../lib/theme';
import { Save } from 'lucide-react-native';

export default function PluginConfigScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { api } = useServerContext();
  const colorScheme = useColorScheme();
  const theme = colorScheme === 'dark' ? colors.dark : colors.light;

  const { data: plugin, isLoading } = usePlugin(api, id || '');
  const { data: manifest } = usePluginManifest(api, id || '');
  const togglePlugin = useTogglePlugin(api);
  const updateConfig = useUpdatePluginConfig(api);

  const [config, setConfig] = useState<Record<string, any>>({});
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (plugin?.config) {
      setConfig(plugin.config);
      setDirty(false);
    }
  }, [plugin?.config]);

  const handleToggle = (enabled: boolean) => {
    if (!id) return;
    togglePlugin.mutate({ pluginId: id, enabled });
  };

  const handleSave = async () => {
    if (!id) return;
    try {
      await updateConfig.mutateAsync({ pluginId: id, config });
      setDirty(false);
      Alert.alert('Saved', 'Plugin configuration updated');
    } catch {
      Alert.alert('Error', 'Failed to save configuration');
    }
  };

  const updateField = (key: string, value: any) => {
    setConfig((prev) => ({ ...prev, [key]: value }));
    setDirty(true);
  };

  if (isLoading) {
    return (
      <View style={[styles.container, styles.center, { backgroundColor: theme.background }]}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  if (!plugin) {
    return (
      <View style={[styles.container, styles.center, { backgroundColor: theme.background }]}>
        <Text style={{ color: theme.textSecondary }}>Plugin not found</Text>
      </View>
    );
  }

  // Render settings fields from schema
  const schema = plugin.settings_schema || {};
  const properties = (schema as any).properties || {};
  const required = (schema as any).required || [];

  return (
    <>
      <Stack.Screen options={{ headerTitle: plugin.name }} />
      <ScrollView style={[styles.container, { backgroundColor: theme.background }]} contentContainerStyle={styles.content}>
        {/* Header */}
        <View style={[styles.card, { backgroundColor: theme.surface }]}>
          <Text style={[styles.pluginName, { color: theme.text }]}>{plugin.name}</Text>
          <Text style={[styles.pluginDesc, { color: theme.textSecondary }]}>{plugin.description}</Text>
          <Text style={[styles.pluginMeta, { color: theme.textSecondary }]}>v{plugin.version} by {plugin.author}</Text>
          <View style={[styles.toggleRow, { marginTop: spacing.md }]}>
            <Text style={[styles.toggleLabel, { color: theme.text }]}>Enabled</Text>
            <Switch
              value={plugin.enabled}
              onValueChange={handleToggle}
              trackColor={{ true: colors.primary }}
            />
          </View>
        </View>

        {/* Config Fields */}
        {Object.keys(properties).length > 0 && (
          <View style={[styles.card, { backgroundColor: theme.surface }]}>
            <Text style={[styles.sectionTitle, { color: theme.text }]}>Configuration</Text>
            {Object.entries(properties).map(([key, propSchema]: [string, any]) => {
              const value = config[key];
              const isRequired = required.includes(key);
              const label = propSchema.title || key;

              if (propSchema.type === 'boolean') {
                return (
                  <View key={key} style={[styles.fieldRow, { borderBottomColor: theme.separator }]}>
                    <Text style={[styles.fieldLabel, { color: theme.text }]}>{label}</Text>
                    <Switch
                      value={!!value}
                      onValueChange={(v) => updateField(key, v)}
                      trackColor={{ true: colors.primary }}
                    />
                  </View>
                );
              }

              if (propSchema.type === 'number' || propSchema.type === 'integer') {
                return (
                  <View key={key} style={[styles.field, { borderBottomColor: theme.separator }]}>
                    <Text style={[styles.fieldLabel, { color: theme.text }]}>
                      {label}{isRequired ? ' *' : ''}
                    </Text>
                    <TextInput
                      style={[styles.fieldInput, { backgroundColor: theme.surfaceSecondary, color: theme.text }]}
                      value={value != null ? String(value) : ''}
                      onChangeText={(t) => updateField(key, t === '' ? null : Number(t))}
                      keyboardType="numeric"
                      placeholder={propSchema.description || ''}
                      placeholderTextColor={theme.textSecondary}
                    />
                  </View>
                );
              }

              // Default: string input
              return (
                <View key={key} style={[styles.field, { borderBottomColor: theme.separator }]}>
                  <Text style={[styles.fieldLabel, { color: theme.text }]}>
                    {label}{isRequired ? ' *' : ''}
                  </Text>
                  {propSchema.enum ? (
                    <Text style={[styles.fieldValue, { color: theme.textSecondary }]}>{value || '—'}</Text>
                  ) : (
                    <TextInput
                      style={[styles.fieldInput, { backgroundColor: theme.surfaceSecondary, color: theme.text }]}
                      value={value != null ? String(value) : ''}
                      onChangeText={(t) => updateField(key, t)}
                      placeholder={propSchema.description || ''}
                      placeholderTextColor={theme.textSecondary}
                      secureTextEntry={key.toLowerCase().includes('key') || key.toLowerCase().includes('password') || key.toLowerCase().includes('secret')}
                    />
                  )}
                </View>
              );
            })}
          </View>
        )}

        {/* Save Button */}
        {dirty && (
          <TouchableOpacity
            style={[styles.saveButton, { backgroundColor: colors.primary }]}
            onPress={handleSave}
            activeOpacity={0.8}
          >
            <Save size={18} color="#fff" />
            <Text style={styles.saveText}>Save Configuration</Text>
          </TouchableOpacity>
        )}
      </ScrollView>
    </>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  center: { justifyContent: 'center', alignItems: 'center' },
  content: { padding: spacing.md, gap: spacing.md, paddingBottom: spacing.xl },
  card: { borderRadius: 12, padding: spacing.md },
  pluginName: { fontSize: fontSize.headline, fontWeight: '700' },
  pluginDesc: { fontSize: fontSize.body, marginTop: 4 },
  pluginMeta: { fontSize: fontSize.caption, marginTop: 4 },
  toggleRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  toggleLabel: { fontSize: fontSize.body, fontWeight: '500' },
  sectionTitle: { fontSize: fontSize.body, fontWeight: '600', marginBottom: spacing.sm },
  fieldRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 12, borderBottomWidth: StyleSheet.hairlineWidth },
  field: { paddingVertical: 12, borderBottomWidth: StyleSheet.hairlineWidth },
  fieldLabel: { fontSize: fontSize.body, marginBottom: 6 },
  fieldInput: { borderRadius: 8, padding: 10, fontSize: fontSize.body },
  fieldValue: { fontSize: fontSize.body },
  saveButton: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, borderRadius: 10, padding: 16 },
  saveText: { color: '#fff', fontSize: fontSize.body, fontWeight: '600' },
});
