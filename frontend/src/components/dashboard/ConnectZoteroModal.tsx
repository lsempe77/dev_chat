"use client";

/**
 * Connect Zotero Modal Component
 *
 * Two-step workflow:
 * 1. Enter API credentials (API Key + User ID)
 * 2. Select collection to sync (optional - can sync entire library)
 */

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { 
  Dialog, 
  DialogContent, 
  DialogDescription,
  DialogHeader, 
  DialogTitle 
} from "@/components/ui/dialog";
import { 
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Checkbox } from "@/components/ui/checkbox";
import { Loader2, Check, AlertCircle, ExternalLink, Trash2, Library, FolderTree } from "lucide-react";

import {
  type ZoteroConnection,
  type ZoteroCollection,
  type ZoteroLibraryInfo,
  validateZoteroCredentials,
  connectZotero,
  getZoteroConnection,
  disconnectZotero,
  getZoteroCollections,
  getZoteroLibraryInfo,
  syncFromZotero,
} from "@/lib/rag-api";

interface ConnectZoteroModalProps {
  ragId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: () => void;
}

export function ConnectZoteroModal({ 
  ragId, 
  open, 
  onOpenChange,
  onSuccess 
}: ConnectZoteroModalProps) {
  // Step management
  const [step, setStep] = useState<"credentials" | "collections">("credentials");

  // Check for existing connection
  const [checkingConnection, setCheckingConnection] = useState(true);
  const [existingConnection, setExistingConnection] = useState<ZoteroConnection | null>(null);
  const [disconnecting, setDisconnecting] = useState(false);

  // Credentials step state
  const [apiKey, setApiKey] = useState("");
  const [userId, setUserId] = useState("");
  const [libraryType, setLibraryType] = useState<"user" | "group">("user");
  const [connecting, setConnecting] = useState(false);
  const [connectionError, setConnectionError] = useState("");

  // Collections step state
  const [libraryInfo, setLibraryInfo] = useState<ZoteroLibraryInfo | null>(null);
  const [collections, setCollections] = useState<ZoteroCollection[]>([]);
  const [selectedCollection, setSelectedCollection] = useState<string | null>(null);
  const [syncPdfs, setSyncPdfs] = useState(true);
  const [loadingCollections, setLoadingCollections] = useState(false);
  
  // Sync state
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<{ success: boolean; message: string } | null>(null);

  // Check for existing connection on open
  useEffect(() => {
    if (open) {
      checkExistingConnection();
    }
  }, [open, ragId]);

  const checkExistingConnection = async () => {
    setCheckingConnection(true);
    try {
      const connection = await getZoteroConnection(ragId);
      if (connection) {
        setExistingConnection(connection);
        setUserId(connection.zotero_user_id);
        setLibraryType(connection.library_type as "user" | "group");
        setSyncPdfs(connection.sync_pdfs);
        setSelectedCollection(connection.selected_collection_key);
        // Skip credentials step and go to collections
        setStep("collections");
        // Load library info and collections
        await loadLibraryData();
      }
    } catch (err) {
      console.error("Failed to check existing connection:", err);
    } finally {
      setCheckingConnection(false);
    }
  };

  const loadLibraryData = async () => {
    setLoadingCollections(true);
    try {
      const [info, colls] = await Promise.all([
        getZoteroLibraryInfo(ragId),
        getZoteroCollections(ragId),
      ]);
      setLibraryInfo(info);
      setCollections(colls);
    } catch (err) {
      console.error("Failed to load library data:", err);
    } finally {
      setLoadingCollections(false);
    }
  };

  const handleDisconnect = async () => {
    if (!confirm("Are you sure you want to disconnect Zotero? This will not delete any synced documents.")) {
      return;
    }

    setDisconnecting(true);
    try {
      await disconnectZotero(ragId);
      setExistingConnection(null);
      setStep("credentials");
      setApiKey("");
      setUserId("");
      setLibraryInfo(null);
      setCollections([]);
      onSuccess?.();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to disconnect");
    } finally {
      setDisconnecting(false);
    }
  };

  const handleValidateAndConnect = async () => {
    if (!apiKey || !userId) {
      setConnectionError("Please enter both API Key and User ID");
      return;
    }

    setConnecting(true);
    setConnectionError("");

    try {
      // First validate credentials
      const result = await validateZoteroCredentials(ragId, apiKey, userId, libraryType);

      if (!result.valid) {
        setConnectionError(result.error || "Invalid credentials");
        return;
      }

      // Connect
      const connection = await connectZotero(ragId, apiKey, userId, libraryType, undefined, syncPdfs);
      setExistingConnection(connection);
      
      if (result.library_info) {
        setLibraryInfo(result.library_info);
      }

      // Move to collections step
      setStep("collections");
      
      // Load collections
      await loadLibraryData();
      
    } catch (err: unknown) {
      setConnectionError(err instanceof Error ? err.message : "Connection failed");
    } finally {
      setConnecting(false);
    }
  };

  const handleSaveSettings = async () => {
    try {
      // Only update connection if we have a new API key
      // Otherwise, just sync with existing connection
      if (apiKey) {
        await connectZotero(
          ragId, 
          apiKey,
          userId,
          libraryType,
          selectedCollection || undefined,
          syncPdfs
        );
      }
      
      // Auto-sync after connecting/saving
      setSyncing(true);
      setSyncResult(null);
      try {
        const result = await syncFromZotero(ragId, selectedCollection || undefined, syncPdfs);
        const message = `Synced ${result.items_synced} items. ${result.items_updated} updated, ${result.pdfs_downloaded} PDFs downloaded.`;
        setSyncResult({ success: result.success, message });
        
        // Close modal after showing result briefly
        setTimeout(() => {
          onSuccess?.();
          onOpenChange(false);
        }, 2000);
      } catch (syncErr) {
        console.error("Sync failed:", syncErr);
        setSyncResult({ 
          success: false, 
          message: syncErr instanceof Error ? syncErr.message : "Sync failed" 
        });
      } finally {
        setSyncing(false);
      }
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to save settings");
    }
  };

  const handleClose = () => {
    onOpenChange(false);
    // Reset state after close animation
    setTimeout(() => {
      if (!existingConnection) {
        setStep("credentials");
        setApiKey("");
        setUserId("");
        setConnectionError("");
      }
    }, 200);
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Library className="h-5 w-5" />
            {existingConnection ? "Zotero Connection" : "Connect Zotero"}
          </DialogTitle>
          <DialogDescription>
            {existingConnection 
              ? "Manage your Zotero connection settings"
              : "Connect your Zotero library to sync references and PDFs"
            }
          </DialogDescription>
        </DialogHeader>

        {checkingConnection ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : step === "credentials" ? (
          // Step 1: Enter credentials
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="apiKey">Zotero API Key</Label>
              <Input
                id="apiKey"
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="Enter your Zotero API key"
              />
              <p className="text-xs text-muted-foreground">
                Get your API key from{" "}
                <a
                  href="https://www.zotero.org/settings/keys/new"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary hover:underline inline-flex items-center gap-1"
                >
                  Zotero Settings <ExternalLink className="h-3 w-3" />
                </a>
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="userId">User ID / Group ID</Label>
              <Input
                id="userId"
                value={userId}
                onChange={(e) => setUserId(e.target.value)}
                placeholder="Enter your Zotero User ID (number)"
              />
              <p className="text-xs text-muted-foreground">
                Find your User ID at{" "}
                <a
                  href="https://www.zotero.org/settings/keys"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary hover:underline inline-flex items-center gap-1"
                >
                  Zotero Settings <ExternalLink className="h-3 w-3" />
                </a>
                {" "}(it&apos;s a number, not your username)
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="libraryType">Library Type</Label>
              <Select value={libraryType} onValueChange={(v) => setLibraryType(v as "user" | "group")}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="user">Personal Library</SelectItem>
                  <SelectItem value="group">Group Library</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                For group libraries, enter the Group ID instead of User ID
              </p>
            </div>

            {connectionError && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{connectionError}</AlertDescription>
              </Alert>
            )}

            <div className="flex justify-end gap-2 pt-4">
              <Button variant="outline" onClick={handleClose}>
                Cancel
              </Button>
              <Button onClick={handleValidateAndConnect} disabled={connecting}>
                {connecting ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Connecting...
                  </>
                ) : (
                  "Connect"
                )}
              </Button>
            </div>
          </div>
        ) : (
          // Step 2: Collections & Settings
          <div className="space-y-4">
            {/* Connection status */}
            <div className="rounded-lg border bg-muted/50 p-4">
              <div className="flex items-center gap-2 text-sm">
                <Check className="h-4 w-4 text-green-600" />
                <span className="font-medium">Connected to Zotero</span>
              </div>
              {libraryInfo && (
                <div className="mt-2 text-sm text-muted-foreground">
                  <p>{libraryInfo.name}</p>
                  <p>{libraryInfo.num_items} items • {libraryInfo.num_collections} collections</p>
                </div>
              )}
              {existingConnection?.last_synced_at && (
                <p className="mt-2 text-xs text-muted-foreground">
                  Last synced: {new Date(existingConnection.last_synced_at).toLocaleString()}
                </p>
              )}
            </div>

            {/* Collection selection */}
            <div className="space-y-2">
              <Label className="flex items-center gap-2">
                <FolderTree className="h-4 w-4" />
                Sync Collection
              </Label>
              {loadingCollections ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Loading collections...
                </div>
              ) : (
                <Select 
                  value={selectedCollection || "all"} 
                  onValueChange={(v) => setSelectedCollection(v === "all" ? null : v)}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select a collection" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">📚 Entire Library</SelectItem>
                    {collections.map((coll) => (
                      <SelectItem key={coll.key} value={coll.key}>
                        📁 {coll.name} ({coll.num_items})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
              <p className="text-xs text-muted-foreground">
                Choose a specific collection or sync your entire library
              </p>
            </div>

            {/* Sync PDFs option */}
            <div className="flex items-center space-x-2">
              <Checkbox
                id="syncPdfs"
                checked={syncPdfs}
                onCheckedChange={(checked) => setSyncPdfs(checked === true)}
              />
              <Label htmlFor="syncPdfs" className="text-sm font-normal cursor-pointer">
                Download PDF attachments when syncing
              </Label>
            </div>

            {/* Sync result feedback */}
            {syncResult && (
              <Alert variant={syncResult.success ? "default" : "destructive"}>
                {syncResult.success ? (
                  <Check className="h-4 w-4" />
                ) : (
                  <AlertCircle className="h-4 w-4" />
                )}
                <AlertDescription>{syncResult.message}</AlertDescription>
              </Alert>
            )}

            <div className="flex justify-between pt-4">
              <Button
                variant="destructive"
                size="sm"
                onClick={handleDisconnect}
                disabled={disconnecting || syncing}
              >
                {disconnecting ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <>
                    <Trash2 className="mr-2 h-4 w-4" />
                    Disconnect
                  </>
                )}
              </Button>
              
              <div className="flex gap-2">
                <Button variant="outline" onClick={handleClose} disabled={syncing}>
                  Cancel
                </Button>
                <Button onClick={handleSaveSettings} disabled={syncing}>
                  {syncing ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Syncing...
                    </>
                  ) : (
                    "Save & Sync"
                  )}
                </Button>
              </div>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
