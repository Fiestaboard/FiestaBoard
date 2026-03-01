import * as SecureStore from 'expo-secure-store';

const SERVER_URL_KEY = 'fiestaboard_server_url';

export async function getServerUrl(): Promise<string | null> {
  try {
    return await SecureStore.getItemAsync(SERVER_URL_KEY);
  } catch {
    return null;
  }
}

export async function setServerUrl(url: string): Promise<void> {
  // Normalize: remove trailing slash
  const normalized = url.replace(/\/+$/, '');
  await SecureStore.setItemAsync(SERVER_URL_KEY, normalized);
}

export async function clearServerUrl(): Promise<void> {
  await SecureStore.deleteItemAsync(SERVER_URL_KEY);
}
