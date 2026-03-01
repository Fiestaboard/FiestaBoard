import React, { useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, useColorScheme, ActivityIndicator, Alert, KeyboardAvoidingView, Platform } from 'react-native';
import { useRouter } from 'expo-router';
import { useServerContext } from './_layout';
import { colors, spacing, fontSize } from '../lib/theme';
import { Wifi, Server, ArrowRight } from 'lucide-react-native';

export default function ConnectScreen() {
  const router = useRouter();
  const { setServer, testConnection, serverUrl } = useServerContext();
  const colorScheme = useColorScheme();
  const isDark = colorScheme === 'dark';
  const theme = isDark ? colors.dark : colors.light;

  const [url, setUrl] = useState(serverUrl || 'http://');
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleConnect = async () => {
    if (!url || url === 'http://' || url === 'https://') {
      setError('Please enter a server URL');
      return;
    }
    setTesting(true);
    setError(null);

    const success = await testConnection(url);
    if (success) {
      await setServer(url);
      router.replace('/(tabs)');
    } else {
      setError('Could not connect to server. Please check the URL and make sure FiestaBoard is running.');
    }
    setTesting(false);
  };

  return (
    <KeyboardAvoidingView
      style={[styles.container, { backgroundColor: theme.background }]}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <View style={styles.content}>
        <View style={styles.header}>
          <Server size={48} color={colors.primary} />
          <Text style={[styles.title, { color: theme.text }]}>Connect to FiestaBoard</Text>
          <Text style={[styles.subtitle, { color: theme.textSecondary }]}>
            Enter the URL of your FiestaBoard server
          </Text>
        </View>

        <View style={styles.form}>
          <Text style={[styles.label, { color: theme.textSecondary }]}>Server URL</Text>
          <TextInput
            style={[styles.input, { backgroundColor: theme.surface, color: theme.text, borderColor: error ? theme.destructive : theme.separator }]}
            value={url}
            onChangeText={setUrl}
            placeholder="http://fiestaboard.local:4420"
            placeholderTextColor={theme.textSecondary}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
            returnKeyType="go"
            onSubmitEditing={handleConnect}
          />
          {error && <Text style={[styles.error, { color: theme.destructive }]}>{error}</Text>}

          <TouchableOpacity
            style={[styles.button, { backgroundColor: colors.primary, opacity: testing ? 0.7 : 1 }]}
            onPress={handleConnect}
            disabled={testing}
            activeOpacity={0.8}
          >
            {testing ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <>
                <Text style={styles.buttonText}>Connect</Text>
                <ArrowRight size={18} color="#fff" />
              </>
            )}
          </TouchableOpacity>
        </View>

        <View style={styles.hint}>
          <Wifi size={16} color={theme.textSecondary} />
          <Text style={[styles.hintText, { color: theme.textSecondary }]}>
            Make sure your phone is on the same network as your FiestaBoard server
          </Text>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  content: { flex: 1, justifyContent: 'center', padding: spacing.lg },
  header: { alignItems: 'center', marginBottom: 40 },
  title: { fontSize: fontSize.title, fontWeight: '700', marginTop: spacing.md },
  subtitle: { fontSize: fontSize.body, marginTop: spacing.xs, textAlign: 'center' },
  form: { gap: spacing.sm },
  label: { fontSize: fontSize.caption, fontWeight: '600', textTransform: 'uppercase' },
  input: { borderWidth: 1, borderRadius: 10, padding: 14, fontSize: fontSize.body },
  error: { fontSize: fontSize.caption },
  button: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, borderRadius: 10, padding: 16, marginTop: spacing.sm },
  buttonText: { color: '#fff', fontSize: fontSize.body, fontWeight: '600' },
  hint: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 32, justifyContent: 'center' },
  hintText: { fontSize: fontSize.caption, flex: 1 },
});
