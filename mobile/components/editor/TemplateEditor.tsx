/**
 * Template Editor for FiestaBoard pages.
 *
 * Provides a multi-line text editor with:
 * - Line-by-line editing constrained to board dimensions
 * - Variable insertion toolbar
 * - Color tile insertion
 * - Line alignment controls
 * - Live preview via API
 *
 * Uses TextInput for Expo Go compatibility.
 * Can be upgraded to TenTap (TipTap-based) for development builds.
 */
import React, { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import {
  View, Text, TextInput, ScrollView, TouchableOpacity,
  StyleSheet, useColorScheme, KeyboardAvoidingView, Platform,
} from 'react-native';
import { DEVICE_DIMENSIONS, type DeviceType, type LineAlignment } from '@fiestaboard/shared';
import { BoardPreview } from '../BoardPreview';
import { EditorToolbar } from './EditorToolbar';
import { colors, spacing, fontSize } from '../../lib/theme';

interface TemplateEditorProps {
  /** Initial template lines (array of strings, one per board row) */
  initialLines: string[];
  /** Device type determines grid dimensions */
  deviceType: DeviceType;
  /** Board color for preview */
  boardColor?: 'black' | 'white';
  /** Initial line alignments */
  initialAlignments?: LineAlignment[];
  /** Called when template changes */
  onChange: (lines: string[], alignments: LineAlignment[]) => void;
  /** Preview content from API (rendered template) */
  previewContent?: string;
  /** API client for variable fetching */
  api: any;
}

export function TemplateEditor({
  initialLines,
  deviceType,
  boardColor = 'black',
  initialAlignments,
  onChange,
  previewContent,
  api,
}: TemplateEditorProps) {
  const colorScheme = useColorScheme();
  const isDark = colorScheme === 'dark';
  const theme = isDark ? colors.dark : colors.light;

  const dims = DEVICE_DIMENSIONS[deviceType] || DEVICE_DIMENSIONS.flagship;
  const numLines = dims.rows;
  const lineWidth = dims.cols;

  // State
  const [lines, setLines] = useState<string[]>(() => {
    const l = [...initialLines];
    while (l.length < numLines) l.push('');
    return l.slice(0, numLines);
  });
  const [alignments, setAlignments] = useState<LineAlignment[]>(() => {
    const a = [...(initialAlignments || [])];
    while (a.length < numLines) a.push('left');
    return a.slice(0, numLines);
  });
  const [activeLine, setActiveLine] = useState(0);
  const [showPreview, setShowPreview] = useState(false);
  const inputRefs = useRef<(TextInput | null)[]>([]);

  // Notify parent of changes
  useEffect(() => {
    onChange(lines, alignments);
  }, [lines, alignments]);

  const handleLineChange = useCallback((index: number, text: string) => {
    setLines((prev) => {
      const next = [...prev];
      // Convert to uppercase (board constraint)
      next[index] = text.toUpperCase();
      return next;
    });
  }, []);

  const handleAlignmentChange = useCallback((alignment: LineAlignment) => {
    setAlignments((prev) => {
      const next = [...prev];
      next[activeLine] = alignment;
      return next;
    });
  }, [activeLine]);

  const insertAtCursor = useCallback((text: string) => {
    setLines((prev) => {
      const next = [...prev];
      next[activeLine] = (next[activeLine] || '') + text;
      return next;
    });
  }, [activeLine]);

  const insertVariable = useCallback((variable: string) => {
    insertAtCursor(`{{${variable}}}`);
  }, [insertAtCursor]);

  const insertColor = useCallback((colorName: string) => {
    insertAtCursor(`{{${colorName}}}`);
  }, [insertAtCursor]);

  // Calculate approximate character count for display
  const getDisplayLength = (line: string): number => {
    // Template variables like {{weather.temp}} count as their max_length
    // For now, just strip {{ }} syntax and count remaining
    return line.replace(/\{\{[^}]*\}\}/g, '???').length;
  };

  return (
    <KeyboardAvoidingView style={styles.wrapper} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      {/* Preview Toggle */}
      <View style={styles.previewToggle}>
        <TouchableOpacity
          style={[styles.toggleBtn, !showPreview && { backgroundColor: colors.primary }]}
          onPress={() => setShowPreview(false)}
        >
          <Text style={[styles.toggleText, { color: !showPreview ? '#fff' : theme.textSecondary }]}>Editor</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.toggleBtn, showPreview && { backgroundColor: colors.primary }]}
          onPress={() => setShowPreview(true)}
        >
          <Text style={[styles.toggleText, { color: showPreview ? '#fff' : theme.textSecondary }]}>Preview</Text>
        </TouchableOpacity>
      </View>

      {showPreview ? (
        /* Board Preview */
        <View style={styles.previewContainer}>
          <BoardPreview
            content={previewContent || lines.join('\n')}
            deviceType={deviceType}
            boardColor={boardColor}
          />
        </View>
      ) : (
        /* Line Editor */
        <ScrollView style={[styles.editorScroll, { backgroundColor: theme.surfaceSecondary }]}>
          {lines.map((line, idx) => (
            <View
              key={idx}
              style={[
                styles.lineRow,
                activeLine === idx && styles.activeLineRow,
                { borderBottomColor: theme.separator },
              ]}
            >
              <Text style={[styles.lineNumber, { color: theme.textSecondary }]}>{idx + 1}</Text>
              <View style={styles.lineInputWrapper}>
                <TextInput
                  ref={(ref) => { inputRefs.current[idx] = ref; }}
                  style={[
                    styles.lineInput,
                    {
                      color: theme.text,
                      textAlign: alignments[idx] || 'left',
                    },
                  ]}
                  value={line}
                  onChangeText={(text) => handleLineChange(idx, text)}
                  onFocus={() => setActiveLine(idx)}
                  placeholder={`Line ${idx + 1}`}
                  placeholderTextColor={theme.textSecondary}
                  autoCapitalize="characters"
                  autoCorrect={false}
                  maxLength={200} // Allow for template syntax
                />
                <Text style={[styles.charCount, { color: getDisplayLength(line) > lineWidth ? theme.destructive : theme.textSecondary }]}>
                  {getDisplayLength(line)}/{lineWidth}
                </Text>
              </View>
            </View>
          ))}
        </ScrollView>
      )}

      {/* Toolbar */}
      {!showPreview && (
        <EditorToolbar
          currentAlignment={alignments[activeLine] || 'left'}
          onAlignmentChange={handleAlignmentChange}
          onInsertVariable={insertVariable}
          onInsertColor={insertColor}
          api={api}
        />
      )}
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  wrapper: { flex: 1 },
  previewToggle: { flexDirection: 'row', gap: 4, alignSelf: 'center', marginBottom: spacing.sm },
  toggleBtn: { paddingHorizontal: 16, paddingVertical: 6, borderRadius: 6 },
  toggleText: { fontSize: fontSize.caption, fontWeight: '600' },
  previewContainer: { padding: spacing.md },
  editorScroll: { borderRadius: 10, margin: spacing.sm },
  lineRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.sm,
    paddingVertical: 6,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  activeLineRow: {
    backgroundColor: 'rgba(245, 166, 35, 0.08)',
  },
  lineNumber: { width: 20, fontSize: fontSize.caption, fontWeight: '600', textAlign: 'center' },
  lineInputWrapper: { flex: 1, marginLeft: spacing.xs },
  lineInput: {
    fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace',
    fontSize: 16,
    paddingVertical: 6,
  },
  charCount: { fontSize: 10, textAlign: 'right', marginTop: -2 },
});
