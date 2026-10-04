// The models an AI provider offers, asked of the provider itself
// (GET /settings/ai/providers/{id}/models), and whether a signed-in provider
// is connected so it can be asked.
//
// One cache entry per provider, shared by Settings → AI Providers and the
// FiestaBot chat panel, under the "ai-provider-models" prefix that a saved
// provider change, a finished sign-in and FiestaBot's own settings changes
// invalidate.

import { useQuery } from "@tanstack/react-query";

import { OAUTH_CONNECTIONS_QUERY_KEY } from "@/components/plugin-settings/oauth-connection";
import { type AIModel, api } from "@/lib/api";

/** A provider's model list changes rarely; a refresh is one press away. */
const MODELS_STALE_MS = 5 * 60_000;

export function useProviderModels(providerId: string, enabled: boolean) {
  return useQuery<AIModel[]>({
    queryKey: ["ai-provider-models", providerId],
    queryFn: async () => (await api.listAiProviderModels(providerId)).models,
    enabled: enabled && !!providerId,
    staleTime: MODELS_STALE_MS,
    // A provider that refuses says why at once; the user can type an id instead.
    retry: false,
  });
}

/** Whether FiestaBot's sign-in for this provider is connected. False while unknown. */
export function useAiSignInConnected(providerId: string, enabled: boolean): boolean {
  const { data } = useQuery({
    queryKey: OAUTH_CONNECTIONS_QUERY_KEY,
    queryFn: api.listOAuthConnections,
    enabled,
  });
  return !!data?.connections.some(
    (connection) => connection.id === `ai.${providerId}` && connection.status === "connected",
  );
}
