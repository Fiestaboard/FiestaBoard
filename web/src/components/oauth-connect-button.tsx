"use client";

import React, { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { Loader2, CheckCircle2, XCircle, ExternalLink } from "lucide-react";

interface OAuthConnectButtonProps {
  provider: string;
  providerName: string;
  boardId?: string;
  onConnectionChange?: (connected: boolean) => void;
  className?: string;
}

/**
 * OAuth connection button component.
 * 
 * Displays the connection status and provides a button to connect/disconnect
 * from OAuth providers like Spotify, Google Calendar, etc.
 */
export function OAuthConnectButton({
  provider,
  providerName,
  boardId = "default",
  onConnectionChange,
  className
}: OAuthConnectButtonProps) {
  const [status, setStatus] = useState<{
    connected: boolean;
    hasValidToken: boolean;
    loading: boolean;
  }>({
    connected: false,
    hasValidToken: false,
    loading: true
  });

  const [disconnecting, setDisconnecting] = useState(false);

  // Check OAuth status on mount and periodically
  const checkStatus = async () => {
    try {
      const response = await fetch(
        `/api/oauth/${provider}/status?board_id=${encodeURIComponent(boardId)}`
      );
      
      if (!response.ok) {
        throw new Error("Failed to check OAuth status");
      }
      
      const data = await response.json();
      setStatus({
        connected: data.connected,
        hasValidToken: data.has_valid_token,
        loading: false
      });
      
      onConnectionChange?.(data.connected);
    } catch (error) {
      console.error("Error checking OAuth status:", error);
      setStatus(prev => ({ ...prev, loading: false }));
    }
  };

  useEffect(() => {
    checkStatus();
    
    // Check status every 30 seconds
    const interval = setInterval(checkStatus, 30000);
    
    return () => clearInterval(interval);
  }, [provider, boardId]);

  const handleConnect = () => {
    // Open authorization URL in a new window
    const authUrl = `/api/oauth/${provider}/authorize?board_id=${encodeURIComponent(boardId)}`;
    window.location.href = authUrl;
  };

  const handleDisconnect = async () => {
    setDisconnecting(true);
    
    try {
      const response = await fetch(
        `/api/oauth/${provider}?board_id=${encodeURIComponent(boardId)}`,
        { method: "DELETE" }
      );
      
      if (!response.ok) {
        throw new Error("Failed to disconnect");
      }
      
      toast.success(`Disconnected from ${providerName}`);
      
      // Update status
      setStatus({
        connected: false,
        hasValidToken: false,
        loading: false
      });
      
      onConnectionChange?.(false);
    } catch (error) {
      console.error("Error disconnecting:", error);
      toast.error(`Failed to disconnect from ${providerName}`);
    } finally {
      setDisconnecting(false);
    }
  };

  if (status.loading) {
    return (
      <div className={className}>
        <Button disabled variant="outline" size="sm">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          Checking status...
        </Button>
      </div>
    );
  }

  return (
    <div className={className}>
      <div className="flex items-center gap-2">
        {status.connected ? (
          <>
            <Badge
              variant={status.hasValidToken ? "default" : "secondary"}
              className="gap-1"
            >
              {status.hasValidToken ? (
                <>
                  <CheckCircle2 className="h-3 w-3" />
                  Connected
                </>
              ) : (
                <>
                  <XCircle className="h-3 w-3" />
                  Token expired
                </>
              )}
            </Badge>
            <Button
              variant="outline"
              size="sm"
              onClick={handleDisconnect}
              disabled={disconnecting}
            >
              {disconnecting ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Disconnecting...
                </>
              ) : (
                "Disconnect"
              )}
            </Button>
          </>
        ) : (
          <Button
            variant="default"
            size="sm"
            onClick={handleConnect}
            className="gap-2"
          >
            <ExternalLink className="h-4 w-4" />
            Connect {providerName}
          </Button>
        )}
      </div>
      {status.connected && (
        <p className="text-xs text-muted-foreground mt-2">
          Your {providerName} account is connected. Tokens are stored securely and encrypted.
        </p>
      )}
    </div>
  );
}
