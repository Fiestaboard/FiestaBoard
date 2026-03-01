import { Tabs, Redirect } from 'expo-router';
import { useColorScheme } from 'react-native';
import { Home, FileText, Calendar, Puzzle, Settings } from 'lucide-react-native';
import { colors } from '../../lib/theme';
import { useServerContext } from '../_layout';

export default function TabLayout() {
  const colorScheme = useColorScheme();
  const isDark = colorScheme === 'dark';
  const theme = isDark ? colors.dark : colors.light;
  const { serverUrl, loading } = useServerContext();

  // Show connect screen if no server is configured
  if (!loading && !serverUrl) {
    return <Redirect href="/connect" />;
  }

  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: theme.textSecondary,
        tabBarStyle: {
          backgroundColor: theme.surface,
          borderTopColor: theme.separator,
        },
        headerStyle: {
          backgroundColor: theme.surface,
        },
        headerTintColor: theme.text,
        headerTitleStyle: {
          fontWeight: '600',
        },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: 'Dashboard',
          headerLargeTitle: true,
          tabBarIcon: ({ color, size }) => <Home size={size} color={color} />,
        }}
      />
      <Tabs.Screen
        name="pages"
        options={{
          title: 'Pages',
          headerLargeTitle: true,
          tabBarIcon: ({ color, size }) => <FileText size={size} color={color} />,
        }}
      />
      <Tabs.Screen
        name="schedule"
        options={{
          title: 'Schedule',
          headerLargeTitle: true,
          tabBarIcon: ({ color, size }) => <Calendar size={size} color={color} />,
        }}
      />
      <Tabs.Screen
        name="integrations"
        options={{
          title: 'Integrations',
          headerLargeTitle: true,
          tabBarIcon: ({ color, size }) => <Puzzle size={size} color={color} />,
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{
          title: 'Settings',
          headerLargeTitle: true,
          tabBarIcon: ({ color, size }) => <Settings size={size} color={color} />,
        }}
      />
    </Tabs>
  );
}
