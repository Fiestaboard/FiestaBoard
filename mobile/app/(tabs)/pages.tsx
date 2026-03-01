import React, { useCallback } from 'react';
import { View, Text, FlatList, TouchableOpacity, StyleSheet, useColorScheme, RefreshControl } from 'react-native';
import { useRouter } from 'expo-router';
import { useServerContext } from '../_layout';
import { usePages, useActivePage, useBoardSettings, getEffectiveBoardColor, usePagePreview } from '../../hooks/use-board';
import { BoardPreview } from '../../components/BoardPreview';
import { colors, spacing, fontSize } from '../../lib/theme';
import { Check } from 'lucide-react-native';
import type { Page } from '@fiestaboard/shared';

function PageCard({ page, isActive, boardColor, onPress }: { page: Page; isActive: boolean; boardColor: 'black' | 'white'; onPress: () => void }) {
  const colorScheme = useColorScheme();
  const theme = colorScheme === 'dark' ? colors.dark : colors.light;
  const { api } = useServerContext();
  const { data: preview } = usePagePreview(api, page.id);

  return (
    <TouchableOpacity style={[styles.pageCard, { backgroundColor: theme.surface }]} onPress={onPress} activeOpacity={0.7}>
      <BoardPreview
        content={preview?.lines?.join('\n') || ''}
        deviceType={page.device_type || 'flagship'}
        boardColor={boardColor}
        compact
      />
      <View style={styles.pageInfo}>
        <View style={styles.pageNameRow}>
          <Text style={[styles.pageName, { color: theme.text }]} numberOfLines={1}>{page.name}</Text>
          {isActive && <Check size={16} color={colors.primary} />}
        </View>
        <Text style={[styles.pageType, { color: theme.textSecondary }]}>{page.device_type || 'flagship'}</Text>
      </View>
    </TouchableOpacity>
  );
}

export default function PagesScreen() {
  const { api } = useServerContext();
  const router = useRouter();
  const colorScheme = useColorScheme();
  const theme = colorScheme === 'dark' ? colors.dark : colors.light;

  const { data: pagesData, isLoading, refetch } = usePages(api);
  const { data: activePageData } = useActivePage(api);
  const { data: boardSettings } = useBoardSettings(api);
  const boardColor = getEffectiveBoardColor(boardSettings);

  const pages = pagesData?.pages || [];
  const activePageId = activePageData?.page_id;

  const [refreshing, setRefreshing] = React.useState(false);
  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await refetch();
    setRefreshing(false);
  }, [refetch]);

  const renderPage = useCallback(({ item }: { item: Page }) => (
    <PageCard
      page={item}
      isActive={item.id === activePageId}
      boardColor={boardColor}
      onPress={() => router.push(`/pages/${item.id}`)}
    />
  ), [activePageId, boardColor, router]);

  return (
    <View style={[styles.container, { backgroundColor: theme.background }]}>
      <FlatList
        data={pages}
        renderItem={renderPage}
        keyExtractor={(item) => item.id}
        numColumns={2}
        columnWrapperStyle={styles.row}
        contentContainerStyle={styles.list}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
        ListEmptyComponent={
          !isLoading ? (
            <View style={styles.empty}>
              <Text style={[styles.emptyText, { color: theme.textSecondary }]}>No pages yet</Text>
            </View>
          ) : null
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  list: { padding: spacing.md, gap: spacing.md },
  row: { gap: spacing.md },
  pageCard: {
    flex: 1,
    borderRadius: 12,
    padding: spacing.sm,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
    elevation: 2,
  },
  pageInfo: { marginTop: spacing.sm },
  pageNameRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  pageName: { fontSize: fontSize.body, fontWeight: '600', flex: 1 },
  pageType: { fontSize: fontSize.caption, marginTop: 2 },
  empty: { padding: 40, alignItems: 'center' },
  emptyText: { fontSize: fontSize.body },
});
