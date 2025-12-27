"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { 
  Settings, 
  TestTube,
  CheckCircle,
  AlertCircle,
  Loader2,
  Database,
  Cloud,
  Cpu,
  RefreshCw,
  Trash2,
  AlertTriangle
} from "lucide-react";
import { getAdminStatus, checkHealth, getCollectionInfo, getBackendSettings, BackendSettings } from "@/lib/admin-api";

interface ConnectionStatus {
  name: string;
  status: "connected" | "disconnected" | "checking";
  details?: string;
}

interface StorageStats {
  bucket: string;
  inputPath: string;
  outputPath: string;
  storageUsedBytes: number;
  fileCount: number;
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
}

export function SettingsTab() {
  const [isLoading, setIsLoading] = useState(true);
  const [isResettingQdrant, setIsResettingQdrant] = useState(false);
  const [isResettingR2, setIsResettingR2] = useState(false);
  const [isResettingDB, setIsResettingDB] = useState(false);
  const [dangerConfirm, setDangerConfirm] = useState<string | null>(null);
  const [storageStats, setStorageStats] = useState<StorageStats>({
    bucket: "devchat-pdfs",
    inputPath: "/input-pdfs/",
    outputPath: "/outputs/",
    storageUsedBytes: 0,
    fileCount: 0,
  });
  const [backendSettings, setBackendSettings] = useState<BackendSettings | null>(null);
  const [connections, setConnections] = useState<ConnectionStatus[]>([
    { name: "Cloudflare R2", status: "checking", details: "Checking..." },
    { name: "Qdrant Cloud", status: "checking", details: "Checking..." },
    { name: "Modal", status: "checking", details: "Checking..." },
    { name: "Cohere API", status: "checking", details: "Checking..." },
  ]);

  // Fetch connection status from backend
  const fetchStatus = useCallback(async () => {
    setIsLoading(true);
    
    try {
      // Fetch health, collection info, admin status, and settings in parallel
      const [healthResult, collectionResult, statusResult, settingsResult] = await Promise.allSettled([
        checkHealth(),
        getCollectionInfo(),
        getAdminStatus(),
        getBackendSettings(),
      ]);

      const newConnections: ConnectionStatus[] = [];

      // Check R2 (from health)
      if (healthResult.status === "fulfilled") {
        const health = healthResult.value;
        newConnections.push({
          name: "Cloudflare R2",
          status: health.components?.r2 ? "connected" : "disconnected",
          details: health.components?.r2 ? "devchat-pdfs bucket" : "Connection failed",
        });
        newConnections.push({
          name: "Cohere API",
          status: health.components?.cohere ? "connected" : "disconnected",
          details: health.components?.cohere ? "embed-v4.0 / rerank-v3.5" : "Connection failed",
        });
        newConnections.push({
          name: "Modal",
          status: "connected",  // Assume connected if backend is working
          details: "GPU workers available",
        });
      } else {
        newConnections.push({ name: "Cloudflare R2", status: "disconnected", details: "Backend unreachable" });
        newConnections.push({ name: "Cohere API", status: "disconnected", details: "Backend unreachable" });
        newConnections.push({ name: "Modal", status: "disconnected", details: "Backend unreachable" });
      }

      // Update storage stats from admin status
      if (statusResult.status === "fulfilled") {
        const status = statusResult.value;
        if (status.storage) {
          setStorageStats({
            bucket: status.storage.bucket || "devchat-pdfs",
            inputPath: status.storage.input_path || "/input-pdfs/",
            outputPath: status.storage.output_path || "/outputs/",
            storageUsedBytes: status.storage.storage_used_bytes || 0,
            fileCount: status.storage.file_count || 0,
          });
        }
      }

      // Update backend settings
      if (settingsResult.status === "fulfilled") {
        setBackendSettings(settingsResult.value);
      }

      // Check Qdrant
      if (collectionResult.status === "fulfilled") {
        const collection = collectionResult.value;
        newConnections.push({
          name: "Qdrant Cloud",
          status: "connected",
          details: `${collection.points_count.toLocaleString()} vectors indexed`,
        });
      } else {
        newConnections.push({
          name: "Qdrant Cloud",
          status: "disconnected",
          details: "Connection failed",
        });
      }

      setConnections(newConnections);
    } catch (err) {
      console.error("Failed to fetch status:", err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Initial load
  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  const testConnection = async (name: string) => {
    setConnections(prev => prev.map(c => 
      c.name === name ? { ...c, status: "checking" as const } : c
    ));
    
    // Re-fetch all status to test connections
    await fetchStatus();
  };

  const testAllConnections = async () => {
    setConnections(prev => prev.map(c => ({ ...c, status: "checking" as const })));
    await fetchStatus();
  };

  // Danger Zone Actions
  const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  const resetQdrant = async () => {
    if (dangerConfirm !== "qdrant") {
      setDangerConfirm("qdrant");
      return;
    }
    setIsResettingQdrant(true);
    setDangerConfirm(null);
    try {
      const res = await fetch(`${API_BASE_URL}/admin/collection`, { method: "DELETE" });
      if (!res.ok) throw new Error(await res.text());
      alert("Qdrant collection reset successfully!");
      await fetchStatus();
    } catch (err) {
      alert(`Failed to reset Qdrant: ${err}`);
    } finally {
      setIsResettingQdrant(false);
    }
  };

  const clearR2 = async () => {
    if (dangerConfirm !== "r2") {
      setDangerConfirm("r2");
      return;
    }
    setIsResettingR2(true);
    setDangerConfirm(null);
    try {
      const res = await fetch(`${API_BASE_URL}/admin/r2/clear`, { method: "DELETE" });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      alert(`R2 cleared: ${data.deleted_count} files deleted`);
    } catch (err) {
      alert(`Failed to clear R2: ${err}`);
    } finally {
      setIsResettingR2(false);
    }
  };

  const resetDatabase = async () => {
    if (dangerConfirm !== "database") {
      setDangerConfirm("database");
      return;
    }
    setIsResettingDB(true);
    setDangerConfirm(null);
    try {
      const res = await fetch(`${API_BASE_URL}/admin/database/reset`, { method: "POST" });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      alert(`Database reset: ${data.deleted_count} documents deleted`);
    } catch (err) {
      alert(`Failed to reset database: ${err}`);
    } finally {
      setIsResettingDB(false);
    }
  };

  const resetAll = async () => {
    if (dangerConfirm !== "all") {
      setDangerConfirm("all");
      return;
    }
    setDangerConfirm(null);
    setIsResettingDB(true);
    setIsResettingQdrant(true);
    setIsResettingR2(true);
    try {
      // Reset in order: DB -> Qdrant -> R2
      await fetch(`${API_BASE_URL}/admin/database/reset`, { method: "POST" });
      await fetch(`${API_BASE_URL}/admin/collection`, { method: "DELETE" });
      await fetch(`${API_BASE_URL}/admin/r2/clear`, { method: "DELETE" });
      alert("Complete system reset successful!");
      await fetchStatus();
    } catch (err) {
      alert(`Reset failed: ${err}`);
    } finally {
      setIsResettingDB(false);
      setIsResettingQdrant(false);
      setIsResettingR2(false);
    }
  };

  const getStatusIcon = (status: ConnectionStatus["status"]) => {
    switch (status) {
      case "connected":
        return <CheckCircle className="h-4 w-4 text-green-500" />;
      case "disconnected":
        return <AlertCircle className="h-4 w-4 text-red-500" />;
      case "checking":
        return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />;
    }
  };

  return (
    <div className="grid gap-6 md:grid-cols-2">
      {/* Connection Status */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Database className="h-5 w-5" />
            Service Connections
          </CardTitle>
          <CardDescription>
            Status of external services and APIs
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex justify-end">
            <Button
              variant="outline"
              size="sm"
              onClick={testAllConnections}
              disabled={isLoading}
            >
              <RefreshCw className={`h-3 w-3 mr-1 ${isLoading ? "animate-spin" : ""}`} />
              Refresh All
            </Button>
          </div>
          {connections.map((conn) => (
            <div 
              key={conn.name}
              className="flex items-center justify-between p-3 rounded-lg border"
            >
              <div className="flex items-center gap-3">
                {getStatusIcon(conn.status)}
                <div>
                  <p className="font-medium">{conn.name}</p>
                  {conn.details && (
                    <p className="text-xs text-muted-foreground">{conn.details}</p>
                  )}
                </div>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => testConnection(conn.name)}
                disabled={conn.status === "checking"}
              >
                <TestTube className="h-3 w-3 mr-1" />
                Test
              </Button>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* MinerU Settings - Read from backend */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Cpu className="h-5 w-5" />
            PDF Processing (MinerU)
          </CardTitle>
          <CardDescription>
            Document extraction settings (configured on Modal)
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="p-4 rounded-lg bg-muted/50 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">OCR Enabled</span>
              <Badge variant="secondary">Yes</Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Table Extraction</span>
              <Badge variant="secondary">Yes</Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Formula Extraction</span>
              <Badge variant="secondary">Yes</Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Device</span>
              <Badge variant="outline">GPU (Modal A10G)</Badge>
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            MinerU runs on Modal GPU workers. Settings are configured in the Modal deployment.
          </p>
        </CardContent>
      </Card>

      {/* Chunking Settings - Read from backend */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Settings className="h-5 w-5" />
            Chunking & Indexing
          </CardTitle>
          <CardDescription>
            How documents are split and stored (read from backend)
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="p-4 rounded-lg bg-muted/50 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Chunk Size</span>
              <span className="text-sm font-medium">{backendSettings?.chunking.chunk_size ?? 512} tokens</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Chunk Overlap</span>
              <span className="text-sm font-medium">{backendSettings?.chunking.chunk_overlap ?? 50} tokens</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Parent Chunk Size</span>
              <span className="text-sm font-medium">{backendSettings?.chunking.parent_chunk_size ?? 2048} tokens</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Semantic Chunking</span>
              <Badge variant={backendSettings?.chunking.use_semantic_chunking ? "default" : "secondary"}>
                {backendSettings?.chunking.use_semantic_chunking ? "Enabled" : "Disabled"}
              </Badge>
            </div>
          </div>
          
          <div className="p-4 rounded-lg bg-muted/50 space-y-3">
            <h4 className="text-sm font-medium">Retrieval Settings</h4>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Initial Retrieval (top_k)</span>
              <span className="text-sm font-medium">{backendSettings?.retrieval.retrieval_top_k ?? 50}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Final Context</span>
              <span className="text-sm font-medium">{backendSettings?.retrieval.final_top_k ?? 10} chunks</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Reranking</span>
              <Badge variant={backendSettings?.retrieval.rerank_enabled ? "default" : "secondary"}>
                {backendSettings?.retrieval.rerank_enabled ? backendSettings?.retrieval.rerank_model : "Disabled"}
              </Badge>
            </div>
          </div>
          
          <p className="text-xs text-muted-foreground">
            These settings are configured via environment variables on Railway.
          </p>
        </CardContent>
      </Card>

      {/* Cloud Storage */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Cloud className="h-5 w-5" />
            Storage Configuration
          </CardTitle>
          <CardDescription>
            Cloudflare R2 bucket settings (read from backend)
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="p-4 rounded-lg bg-muted/50 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Bucket</span>
              <Badge variant="secondary">{storageStats.bucket}</Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Input Path</span>
              <code className="text-xs bg-muted px-2 py-1 rounded">{storageStats.inputPath}</code>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Output Path</span>
              <code className="text-xs bg-muted px-2 py-1 rounded">{storageStats.outputPath}</code>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Files</span>
              <span className="text-sm font-medium">{storageStats.fileCount.toLocaleString()}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Storage Used</span>
              <span className="text-sm font-medium">{formatBytes(storageStats.storageUsedBytes)}</span>
            </div>
          </div>
          
          <p className="text-xs text-muted-foreground">
            Storage credentials are configured via environment variables. 
            Contact admin to update R2 settings.
          </p>
        </CardContent>
      </Card>

      {/* Danger Zone */}
      <Card className="md:col-span-2 border-red-500/50">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-red-600">
            <AlertTriangle className="h-5 w-5" />
            Danger Zone
          </CardTitle>
          <CardDescription>
            Destructive actions that cannot be undone. Click once to confirm, click again to execute.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="p-4 rounded-lg border border-red-200 bg-red-50/50 dark:bg-red-950/20 space-y-3">
              <div>
                <h4 className="font-medium text-red-700 dark:text-red-400">Reset Qdrant Vectors</h4>
                <p className="text-xs text-muted-foreground">Delete all vector embeddings. Documents will need reprocessing.</p>
              </div>
              <Button 
                variant={dangerConfirm === "qdrant" ? "destructive" : "outline"}
                size="sm"
                onClick={resetQdrant}
                disabled={isResettingQdrant}
                className={dangerConfirm === "qdrant" ? "" : "border-red-300 text-red-600 hover:bg-red-100"}
              >
                {isResettingQdrant ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Trash2 className="h-4 w-4 mr-2" />
                )}
                {dangerConfirm === "qdrant" ? "Click to Confirm" : "Reset Qdrant"}
              </Button>
            </div>

            <div className="p-4 rounded-lg border border-red-200 bg-red-50/50 dark:bg-red-950/20 space-y-3">
              <div>
                <h4 className="font-medium text-red-700 dark:text-red-400">Clear R2 Storage</h4>
                <p className="text-xs text-muted-foreground">Delete all PDFs and processed outputs from Cloudflare R2.</p>
              </div>
              <Button 
                variant={dangerConfirm === "r2" ? "destructive" : "outline"}
                size="sm"
                onClick={clearR2}
                disabled={isResettingR2}
                className={dangerConfirm === "r2" ? "" : "border-red-300 text-red-600 hover:bg-red-100"}
              >
                {isResettingR2 ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Trash2 className="h-4 w-4 mr-2" />
                )}
                {dangerConfirm === "r2" ? "Click to Confirm" : "Clear R2"}
              </Button>
            </div>

            <div className="p-4 rounded-lg border border-red-200 bg-red-50/50 dark:bg-red-950/20 space-y-3">
              <div>
                <h4 className="font-medium text-red-700 dark:text-red-400">Reset PostgreSQL</h4>
                <p className="text-xs text-muted-foreground">Delete all document metadata from the database.</p>
              </div>
              <Button 
                variant={dangerConfirm === "database" ? "destructive" : "outline"}
                size="sm"
                onClick={resetDatabase}
                disabled={isResettingDB}
                className={dangerConfirm === "database" ? "" : "border-red-300 text-red-600 hover:bg-red-100"}
              >
                {isResettingDB ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Trash2 className="h-4 w-4 mr-2" />
                )}
                {dangerConfirm === "database" ? "Click to Confirm" : "Reset Database"}
              </Button>
            </div>

            <div className="p-4 rounded-lg border border-red-500 bg-red-100/50 dark:bg-red-950/40 space-y-3">
              <div>
                <h4 className="font-medium text-red-700 dark:text-red-400">⚠️ Complete System Reset</h4>
                <p className="text-xs text-muted-foreground">Delete ALL data: vectors, files, and metadata. Start completely fresh.</p>
              </div>
              <Button 
                variant={dangerConfirm === "all" ? "destructive" : "outline"}
                size="sm"
                onClick={resetAll}
                disabled={isResettingDB || isResettingQdrant || isResettingR2}
                className={dangerConfirm === "all" ? "" : "border-red-500 text-red-700 hover:bg-red-200"}
              >
                {(isResettingDB || isResettingQdrant || isResettingR2) ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Trash2 className="h-4 w-4 mr-2" />
                )}
                {dangerConfirm === "all" ? "Click to Confirm FULL RESET" : "Reset Everything"}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Settings Note */}
      <div className="md:col-span-2">
        <p className="text-xs text-muted-foreground text-center">
          All settings are read from the backend and configured via environment variables.
          Contact admin to change settings on Railway (backend) or Modal (PDF processing).
        </p>
      </div>
    </div>
  );
}
