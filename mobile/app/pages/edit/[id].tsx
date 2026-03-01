import React, { useState, useCallback, useEffect } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, useColorScheme, Alert, ActivityIndicator } from 'react-native';
import { useLocalSearchParams, useRouter, Stack } from 'expo-router';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useServerContext } from '../../_layout';
import { usePages, useBoardSettings, getEffectiveBoardColor, queryKeys } from '../../../hooks/use-board';
import { TemplateEditor } from '../../../components/editor/TemplateEditor';
import { colors, spacing, fontSize } from '../../../lib/theme';
import { Save } from 'lucide-react-native';
import type { LineAlignment } from '@fiestaboard/shared';

export default function EditPageScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { api } = useServerContext();
  const router = useRouter();
  const queryClient = useQueryClient();
  const colorScheme = useColorScheme();
  const theme = colorScheme === 'dark' ? colors.dark : colors.light;

  const { data: pagesData } = usePages(api);
  const { data: boardSettings } = useBoardSettings(api);
  const boardColor = getEffectiveBoardColor(boardSettings);
  const page = pagesData?.pages?.find((p: any) => p.id === id);

  const [name, setName] = useState('');
  const [lines, setLines] = useState<string[]>([]);
  const [alignments, setAlignments] = useState<LineAlignment[]>([]);
  const [previewContent, setPreviewContent] = useState('');
  const [saving, setSaving] = useState(false);

  // Initialize from page data
  useEffect(() => {
    if (page) {
      setName(page.name);
      const template = page.template || [];
      setLines(template);
      setAlignments(page.line_metadata?.map((m: any) => m.alignment) || []);
    }
  }, [page]);

  // Debounced preview
  useEffect(() => {
    if (!api || lines.length === 0) return;
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
    if (!api || !id) return;
    setSaving(true);
    try {
      const lineMetadata = alignments.map((a, i) => ({
        alignment: a,
        wrap: page?.line_metadata?.[i]?.wrap || false,
      }));
      await api.updatePage(id, {
        name,
        template: lines,
        line_metadata: lineMetadata,
      });
      queryClient.invalidateQueries({ queryKey: queryKeys.pages });
      Alert.alert('Saved', 'Page updated successfully', [
        { text: 'OK', onPress: () => router.back() },
      ]);
    } catch (err) {
      Alert.alert('Error', 'Failed to save page');
    } finally {
      setSaving(false);
    }
  };

  if (!page) {
    return (
      <View style={[styles.container, styles.center, { backgroundColor: theme.background }]}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  return (
    <>
      <Stack.Screen
        options={{
          headerTitle: 'Edit Page',
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
          />
        </View>

        {/* Template Editor */}
        <TemplateEditor
          initialLines={lines}
          deviceType={page.device_type || 'flagship'}
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
  center: { justifyContent: 'center', alignItems: 'center' },
  nameRow: { paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  nameInput: { fontSize: fontSize.headline, fontWeight: '600' },
  saveBtn: { paddingHorizontal: spacing.sm },
});
