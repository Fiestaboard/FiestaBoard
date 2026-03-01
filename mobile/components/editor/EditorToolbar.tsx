import React, { useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, ScrollView, StyleSheet, useColorScheme,
  Modal, FlatList, SafeAreaView,
} from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { BOARD_COLORS, type LineAlignment } from '@fiestaboard/shared';
import { colors, spacing, fontSize } from '../../lib/theme';
import {
  AlignLeft, AlignCenter, AlignRight,
  Code2, Palette, X,
} from 'lucide-react-native';

interface EditorToolbarProps {
  currentAlignment: LineAlignment;
  onAlignmentChange: (alignment: LineAlignment) => void;
  onInsertVariable: (variable: string) => void;
  onInsertColor: (color: string) => void;
  api: any;
}

// Board color options for the color picker
const COLOR_OPTIONS = [
  { name: 'red', hex: BOARD_COLORS.red },
  { name: 'orange', hex: BOARD_COLORS.orange },
  { name: 'yellow', hex: BOARD_COLORS.yellow },
  { name: 'green', hex: BOARD_COLORS.green },
  { name: 'blue', hex: BOARD_COLORS.blue },
  { name: 'violet', hex: BOARD_COLORS.violet },
  { name: 'white', hex: BOARD_COLORS.white },
  { name: 'black', hex: '#1a1a1a' },
];

export function EditorToolbar({
  currentAlignment,
  onAlignmentChange,
  onInsertVariable,
  onInsertColor,
  api,
}: EditorToolbarProps) {
  const colorScheme = useColorScheme();
  const isDark = colorScheme === 'dark';
  const theme = isDark ? colors.dark : colors.light;

  const [showVariables, setShowVariables] = useState(false);
  const [showColors, setShowColors] = useState(false);

  // Fetch template variables from API
  const { data: templateVars } = useQuery({
    queryKey: ['templateVariables'],
    queryFn: () => api?.getTemplateVariables(),
    enabled: !!api,
    staleTime: 5 * 60 * 1000,
  });

  const variables = templateVars?.variables || {};

  const handleInsertVariable = useCallback((varName: string) => {
    onInsertVariable(varName);
    setShowVariables(false);
  }, [onInsertVariable]);

  const handleInsertColor = useCallback((colorName: string) => {
    onInsertColor(colorName);
    setShowColors(false);
  }, [onInsertColor]);

  return (
    <>
      <View style={[styles.toolbar, { backgroundColor: theme.surface, borderTopColor: theme.separator }]}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.toolbarContent}>
          {/* Variables */}
          <TouchableOpacity style={styles.toolButton} onPress={() => setShowVariables(true)}>
            <Code2 size={20} color={colors.primary} />
            <Text style={[styles.toolLabel, { color: colors.primary }]}>Variables</Text>
          </TouchableOpacity>

          {/* Colors */}
          <TouchableOpacity style={styles.toolButton} onPress={() => setShowColors(true)}>
            <Palette size={20} color={colors.primary} />
            <Text style={[styles.toolLabel, { color: colors.primary }]}>Colors</Text>
          </TouchableOpacity>

          <View style={[styles.separator, { backgroundColor: theme.separator }]} />

          {/* Alignment */}
          <TouchableOpacity
            style={[styles.alignButton, currentAlignment === 'left' && styles.alignActive]}
            onPress={() => onAlignmentChange('left')}
          >
            <AlignLeft size={18} color={currentAlignment === 'left' ? colors.primary : theme.textSecondary} />
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.alignButton, currentAlignment === 'center' && styles.alignActive]}
            onPress={() => onAlignmentChange('center')}
          >
            <AlignCenter size={18} color={currentAlignment === 'center' ? colors.primary : theme.textSecondary} />
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.alignButton, currentAlignment === 'right' && styles.alignActive]}
            onPress={() => onAlignmentChange('right')}
          >
            <AlignRight size={18} color={currentAlignment === 'right' ? colors.primary : theme.textSecondary} />
          </TouchableOpacity>
        </ScrollView>
      </View>

      {/* Variable Picker Modal */}
      <Modal visible={showVariables} animationType="slide" presentationStyle="pageSheet">
        <SafeAreaView style={[styles.modal, { backgroundColor: theme.background }]}>
          <View style={[styles.modalHeader, { borderBottomColor: theme.separator }]}>
            <Text style={[styles.modalTitle, { color: theme.text }]}>Insert Variable</Text>
            <TouchableOpacity onPress={() => setShowVariables(false)}>
              <X size={24} color={theme.text} />
            </TouchableOpacity>
          </View>
          <ScrollView contentContainerStyle={styles.modalContent}>
            {Object.entries(variables).map(([plugin, vars]) => (
              <View key={plugin} style={styles.varGroup}>
                <Text style={[styles.varGroupTitle, { color: theme.textSecondary }]}>{plugin}</Text>
                <View style={styles.varList}>
                  {(vars as string[]).map((v) => (
                    <TouchableOpacity
                      key={v}
                      style={[styles.varPill, { backgroundColor: theme.surfaceSecondary }]}
                      onPress={() => handleInsertVariable(`${plugin}.${v}`)}
                    >
                      <Text style={[styles.varText, { color: colors.primary }]}>{v}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </View>
            ))}
            {Object.keys(variables).length === 0 && (
              <Text style={[styles.emptyText, { color: theme.textSecondary }]}>
                No variables available. Enable some plugins first.
              </Text>
            )}
          </ScrollView>
        </SafeAreaView>
      </Modal>

      {/* Color Picker Modal */}
      <Modal visible={showColors} animationType="slide" presentationStyle="pageSheet">
        <SafeAreaView style={[styles.modal, { backgroundColor: theme.background }]}>
          <View style={[styles.modalHeader, { borderBottomColor: theme.separator }]}>
            <Text style={[styles.modalTitle, { color: theme.text }]}>Insert Color Tile</Text>
            <TouchableOpacity onPress={() => setShowColors(false)}>
              <X size={24} color={theme.text} />
            </TouchableOpacity>
          </View>
          <View style={styles.colorGrid}>
            {COLOR_OPTIONS.map(({ name, hex }) => (
              <TouchableOpacity
                key={name}
                style={[styles.colorSwatch, { backgroundColor: hex }]}
                onPress={() => handleInsertColor(name)}
              >
                <Text style={[styles.colorLabel, { color: name === 'black' ? '#fff' : name === 'white' ? '#000' : '#fff' }]}>
                  {name}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        </SafeAreaView>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  toolbar: {
    borderTopWidth: StyleSheet.hairlineWidth,
    paddingVertical: 6,
  },
  toolbarContent: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.sm,
    gap: 4,
  },
  toolButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 6,
  },
  toolLabel: { fontSize: fontSize.caption, fontWeight: '600' },
  separator: { width: 1, height: 24, marginHorizontal: 4 },
  alignButton: { padding: 6, borderRadius: 6 },
  alignActive: { backgroundColor: 'rgba(245, 166, 35, 0.12)' },
  modal: { flex: 1 },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  modalTitle: { fontSize: fontSize.headline, fontWeight: '600' },
  modalContent: { padding: spacing.md },
  varGroup: { marginBottom: spacing.lg },
  varGroupTitle: { fontSize: fontSize.caption, fontWeight: '600', textTransform: 'uppercase', marginBottom: spacing.xs },
  varList: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs },
  varPill: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 16 },
  varText: { fontSize: fontSize.caption, fontWeight: '500' },
  colorGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    padding: spacing.md,
    gap: spacing.md,
    justifyContent: 'center',
  },
  colorSwatch: {
    width: 80,
    height: 80,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.2,
    shadowRadius: 2,
    elevation: 3,
  },
  colorLabel: { fontSize: fontSize.caption, fontWeight: '600', textTransform: 'capitalize' },
  emptyText: { fontSize: fontSize.body, textAlign: 'center', padding: 20 },
});
