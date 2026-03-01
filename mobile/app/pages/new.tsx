import React, { useState, useCallback, useEffect } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, useColorScheme, Alert, ActivityIndicator } from 'react-native';
import { useRouter, useLocalSearchParams, Stack } from 'expo-router';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useServerContext } from '../_layout';
import { useBoardSettings, getEffectiveBoardColor, queryKeys } from '../../hooks/use-board';
import { TemplateEditor } from '../../components/editor/TemplateEditor';
import { colors, spacing, fontSize } from '../../lib/theme';
import { Save } from 'lucide-react-native';
import { DEVICE_DIMENSIONS, type DeviceType, type LineAlignment } from '@fiestaboard/shared';

export default function NewPageScreen() {
  const params = useLocalSearchParams<{ device?: string }>();
  const { api } = useServerContext();
  const router = useRouter();
  const queryClient = useQueryClient();
  const colorScheme = useColorScheme();
  const theme = colorScheme === 'dark' ? colors.dark : colors.light;

  const deviceType = (params.device as DeviceType) || 'flagship';
  const { data: boardSettings } = useBoardSettings(api);
  const boardColor = getEffectiveBoardColor(boardSettings);

  const dims = DEVICE_DIMENSIONS[deviceType] || DEVICE_DIMENSIONS.flagship;

  const [name, setName] = useState('');
  const [lines, setLines] = useState<string[]>(Array(dims.rows).fill(''));
  const [alignments, setAlignments] = useState<LineAlignment[]>(Array(dims.rows).fill('left' as LineAlignment));
  const [previewContent, setPreviewContent] = useState('');
  const [saving, setSaving] = useState(false);

  // Debounced preview
  useEffect(() => {
    if (!api || lines.every((l) => !l)) return;
    const timer = setTimeout(async () => {
      try {
        const result = await api.renderTemplate(lines);
        setPreviewContent(result.lines?.join('\n') || '');
      } catch {
        // Preview failure is non-critical
      }
    }, 500);
    return () => clearTimeout(timer);
  }, [api, lines]);

  const handleSave = async () => {
    if (!api) return;
    if (!name.trim()) {
      Alert.alert('Name Required', 'Please enter a page name');
      return;
    }
    setSaving(true);
    try {
      const lineMetadata = alignments.map((a) => ({
        alignment: a,
        wrap: false,
      }));
      await api.createPage({
        name: name.trim(),
        type: 'template',
        device_type: deviceType,
        template: lines,
        line_metadata: lineMetadata,
      });
      queryClient.invalidateQueries({ queryKey: queryKeys.pages });
      Alert.alert('Created', 'Page created successfully', [
        { text: 'OK', onPress: () => router.back() },
      ]);
    } catch (err) {
      Alert.alert('Error', 'Failed to create page');
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <Stack.Screen
        options={{
          headerShown: true,
          headerTitle: 'New Page',
          headerBackTitle: 'Cancel',
          headerRight: () => (
            <TouchableOpacity onPress={handleSave} disabled={saving} style={styles.saveBtn}>
              {saving ? (
                <ActivityIndicator size="small" color={colors.primary} />
              ) : (
                <Save size={22} color={colors.primary} />
              )}
            </TouchableOpacity>
          ),
        }}
      />
      <View style={[styles.container, { backgroundColor: theme.background }]}>
        {/* Page Name */}
        <View style={[styles.nameRow, { backgroundColor: theme.surface }]}>
          <TextInput
            style={[styles.nameInput, { color: theme.text }]}
            value={name}
            onChangeText={setName}
            placeholder="Page name"
            placeholderTextColor={theme.textSecondary}
            autoFocus
          />
        </View>

        {/* Template Editor */}
        <TemplateEditor
          initialLines={lines}
          deviceType={deviceType}
          boardColor={boardColor}
          initialAlignments={alignments}
          onChange={(newLines, newAlignments) => {
            setLines(newLines);
            setAlignments(newAlignments);
          }}
          previewContent={previewContent}
          api={api}
        />
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  nameRow: { paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  nameInput: { fontSize: fontSize.headline, fontWeight: '600' },
  saveBtn: { paddingHorizontal: spacing.sm },
});
