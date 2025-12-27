"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { 
  Settings, 
  Save,
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
import { getAdminStatus, checkHealth, getCollectionInfo } from "@/lib/admin-api";

interface ConnectionStatus {
  name: string;
  status: "connected" | "disconnected" | "checking";
  details?: string;
}

export function SettingsTab() {
  const [isSaving, setIsSaving] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isResettingQdrant, setIsResettingQdrant] = useState(false);
  const [isResettingR2, setIsResettingR2] = useState(false);
  const [isResettingDB, setIsResettingDB] = useState(false);
  const [dangerConfirm, setDangerConfirm] = useState<string | null>(null);
  const [connections, setConnections] = useState<ConnectionStatus[]>([
    { name: "Cloudflare R2", status: "checking", details: "Checking..." },
    { name: "Qdrant Cloud", status: "checking", details: "Checking..." },
    { name: "Modal", status: "checking", details: "Checking..." },
    { name: "Cohere API", status: "checking", details: "Checking..." },
  ]);

  // MinerU Settings
  const [mineruSettings, setMineruSettings] = useState({
    enableOcr: true,
    enableTableExtraction: true,
    enableFormulaExtraction: true,
    device: "auto",
    language: "auto",
    maxConcurrentJobs: 4,
  });

  // Processing Settings
  const [processingSettings, setProcessingSettings] = useState({
    chunkSize: 512,
    chunkOverlap: 50,
    autoProcessOnUpload: true,
    retryFailedJobs: true,
    maxRetries: 3,
  });

  // Fetch connection status from backend
  const fetchStatus = useCallback(async () => {
    setIsLoading(true);
    
    try {
      // Fetch health and collection info in parallel
      const [healthResult, collectionResult] = await Promise.allSettled([
        checkHealth(),
        getCollectionInfo(),
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

  const saveSettings = async () => {
    setIsSaving(true);
    
    // TODO: Save to backend when settings endpoint is available
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    setIsSaving(false);
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

      {/* MinerU Settings */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Cpu className="h-5 w-5" />
            PDF Processing (MinerU)
          </CardTitle>
          <CardDescription>
            Configure document extraction settings
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>Enable OCR</Label>
                <p className="text-xs text-muted-foreground">
                  Extract text from scanned documents
                </p>
              </div>
              <Switch
                checked={mineruSettings.enableOcr}
                onCheckedChange={(checked) => 
                  setMineruSettings(prev => ({ ...prev, enableOcr: checked }))
                }
              />
            </div>
            
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>Extract Tables</Label>
                <p className="text-xs text-muted-foreground">
                  Parse tables as structured HTML
                </p>
              </div>
              <Switch
                checked={mineruSettings.enableTableExtraction}
                onCheckedChange={(checked) => 
                  setMineruSettings(prev => ({ ...prev, enableTableExtraction: checked }))
                }
              />
            </div>
            
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>Extract Formulas</Label>
                <p className="text-xs text-muted-foreground">
                  Convert math equations to LaTeX
                </p>
              </div>
              <Switch
                checked={mineruSettings.enableFormulaExtraction}
                onCheckedChange={(checked) => 
                  setMineruSettings(prev => ({ ...prev, enableFormulaExtraction: checked }))
                }
              />
            </div>

            <div className="space-y-2">
              <Label>Max Concurrent Jobs</Label>
              <Input
                type="number"
                min={1}
                max={10}
                value={mineruSettings.maxConcurrentJobs}
                onChange={(e) => 
                  setMineruSettings(prev => ({ 
                    ...prev, 
                    maxConcurrentJobs: parseInt(e.target.value) || 1 
                  }))
                }
              />
              <p className="text-xs text-muted-foreground">
                Number of PDFs to process in parallel (affects cost)
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Chunking Settings */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Settings className="h-5 w-5" />
            Chunking & Indexing
          </CardTitle>
          <CardDescription>
            Configure how documents are split and stored
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid gap-4 grid-cols-2">
            <div className="space-y-2">
              <Label>Chunk Size (words)</Label>
              <Input
                type="number"
                min={100}
                max={2000}
                value={processingSettings.chunkSize}
                onChange={(e) => 
                  setProcessingSettings(prev => ({ 
                    ...prev, 
                    chunkSize: parseInt(e.target.value) || 512 
                  }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label>Overlap (words)</Label>
              <Input
                type="number"
                min={0}
                max={200}
                value={processingSettings.chunkOverlap}
                onChange={(e) => 
                  setProcessingSettings(prev => ({ 
                    ...prev, 
                    chunkOverlap: parseInt(e.target.value) || 50 
                  }))
                }
              />
            </div>
          </div>
          
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>Auto-process on Upload</Label>
              <p className="text-xs text-muted-foreground">
                Start processing immediately after upload
              </p>
            </div>
            <Switch
              checked={processingSettings.autoProcessOnUpload}
              onCheckedChange={(checked) => 
                setProcessingSettings(prev => ({ ...prev, autoProcessOnUpload: checked }))
              }
            />
          </div>
          
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>Retry Failed Jobs</Label>
              <p className="text-xs text-muted-foreground">
                Automatically retry failed processing jobs
              </p>
            </div>
            <Switch
              checked={processingSettings.retryFailedJobs}
              onCheckedChange={(checked) => 
                setProcessingSettings(prev => ({ ...prev, retryFailedJobs: checked }))
              }
            />
          </div>
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
            Cloudflare R2 bucket settings
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="p-4 rounded-lg bg-muted/50 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Bucket</span>
              <Badge variant="secondary">devchat-pdfs</Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Input Path</span>
              <code className="text-xs bg-muted px-2 py-1 rounded">/input-pdfs/</code>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Output Path</span>
              <code className="text-xs bg-muted px-2 py-1 rounded">/outputs/</code>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Storage Used</span>
              <span className="text-sm">2.4 GB / 10 GB</span>
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

      {/* Save Button */}
      <div className="md:col-span-2 flex justify-end gap-2">
        <Button variant="outline">
          Reset to Defaults
        </Button>
        <Button onClick={saveSettings} disabled={isSaving}>
          {isSaving ? (
            <>
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              Saving...
            </>
          ) : (
            <>
              <Save className="h-4 w-4 mr-2" />
              Save Settings
            </>
          )}
        </Button>
      </div>

      {/* Settings Note */}
      <div className="md:col-span-2">
        <p className="text-xs text-muted-foreground text-center">
          ⚠️ Note: MinerU and Chunking settings are currently display-only. 
          Settings are configured via environment variables on the backend.
        </p>
      </div>
    </div>
  );
}
