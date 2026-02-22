"use client";

import { useEffect, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Loader2, CheckCircle, XCircle, MessageSquare } from "lucide-react";
import { toast } from "sonner";

function SlackOAuthCallbackContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [errorMessage, setErrorMessage] = useState<string>("");
  const [channels, setChannels] = useState<Array<{ id: string; name: string; is_private: boolean }>>([]);
  const [selectedChannel, setSelectedChannel] = useState<string>("");
  const [workspaceName, setWorkspaceName] = useState<string>("");
  const [isSelectingChannel, setIsSelectingChannel] = useState(false);

  useEffect(() => {
    const handleCallback = async () => {
      const code = searchParams?.get("code");
      const state = searchParams?.get("state");
      const error = searchParams?.get("error");

      if (error) {
        setStatus("error");
        setErrorMessage(`OAuth error: ${error}`);
        return;
      }

      if (!code || !state) {
        setStatus("error");
        setErrorMessage("Missing OAuth parameters");
        return;
      }

      try {
        // Get the redirect URI (current origin + path without query params)
        const redirectUri = `${window.location.origin}/oauth/callback/slack`;

        // Exchange code for access token
        const result = await api.handleOAuthCallback("slack", code, state, redirectUri);

        if (result.success) {
          setStatus("success");
          setWorkspaceName(result.workspace_name);
          setChannels(result.channels);
          
          // Auto-select first channel if only one exists
          if (result.channels.length === 1) {
            setSelectedChannel(result.channels[0].id);
          }
          
          toast.success(`Connected to ${result.workspace_name}!`);
        } else {
          setStatus("error");
          setErrorMessage("Failed to authenticate with Slack");
        }
      } catch (err) {
        setStatus("error");
        setErrorMessage(err instanceof Error ? err.message : "Unknown error");
        toast.error("Failed to complete OAuth flow");
      }
    };

    handleCallback();
  }, [searchParams]);

  const handleChannelSelect = async () => {
    if (!selectedChannel) {
      toast.error("Please select a channel");
      return;
    }

    setIsSelectingChannel(true);

    try {
      const channel = channels.find(ch => ch.id === selectedChannel);
      if (!channel) {
        throw new Error("Channel not found");
      }

      await api.selectOAuthChannel("slack", channel.id, channel.name);
      toast.success(`Channel #${channel.name} selected!`);
      
      // Redirect to integrations page
      setTimeout(() => {
        router.push("/integrations");
      }, 1000);
    } catch (err) {
      toast.error("Failed to select channel");
      setIsSelectingChannel(false);
    }
  };

  const handleSkipChannel = () => {
    toast.info("You can configure the channel later in plugin settings");
    router.push("/integrations");
  };

  if (status === "loading") {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Loader2 className="h-5 w-5 animate-spin" />
              Connecting to Slack...
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Please wait while we complete the authentication process.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        <Card className="w-full max-w-md border-destructive">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-destructive">
              <XCircle className="h-5 w-5" />
              Connection Failed
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">{errorMessage}</p>
            <Button onClick={() => router.push("/integrations")} className="w-full">
              Return to Integrations
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-green-600">
            <CheckCircle className="h-5 w-5" />
            Successfully Connected!
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <p className="text-sm font-medium">Connected to workspace:</p>
            <p className="text-lg font-semibold">{workspaceName}</p>
          </div>

          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <MessageSquare className="h-4 w-4 text-muted-foreground" />
              <p className="text-sm font-medium">Select a channel to monitor:</p>
            </div>
            
            <select
              value={selectedChannel}
              onChange={(e) => setSelectedChannel(e.target.value)}
              className="w-full px-3 py-2 rounded-md border border-input bg-background text-sm"
              disabled={isSelectingChannel}
            >
              <option value="">-- Select a channel --</option>
              {channels.map((channel) => (
                <option key={channel.id} value={channel.id}>
                  #{channel.name} {channel.is_private ? "(private)" : ""}
                </option>
              ))}
            </select>
          </div>

          <div className="flex gap-2">
            <Button
              onClick={handleChannelSelect}
              disabled={!selectedChannel || isSelectingChannel}
              className="flex-1"
            >
              {isSelectingChannel ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Saving...
                </>
              ) : (
                "Select Channel"
              )}
            </Button>
            <Button
              onClick={handleSkipChannel}
              variant="outline"
              disabled={isSelectingChannel}
              className="flex-1"
            >
              Skip for Now
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default function SlackOAuthCallbackPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Loader2 className="h-5 w-5 animate-spin" />
              Loading...
            </CardTitle>
          </CardHeader>
        </Card>
      </div>
    }>
      <SlackOAuthCallbackContent />
    </Suspense>
  );
}
