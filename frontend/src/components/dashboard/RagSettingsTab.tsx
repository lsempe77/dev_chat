"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { 
  Settings, 
  TestTube,
  CheckCircle,
  AlertCircle,
  Loader2,
  Database,
  Cloud,
  RefreshCw,
  Trash2,
  AlertTriangle,
  Globe,
  Lock,
  Copy,
  Check,
  Library,
  Cpu,
} from "lucide-react";
import { createBrowserClient } from "@supabase/ssr";
import { ConnectZoteroModal } from "./ConnectZoteroModal";
import { getZoteroConnection, type ZoteroConnection } from "@/lib/rag-api";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Available LLM providers and models (synced with backend)
const AVAILABLE_PROVIDERS = {
  openai: {
    name: "OpenAI",
    models: {
      "gpt-4o-mini": { name: "GPT-4o Mini", type: "fast", cost: "Low" },
      "gpt-4o": { name: "GPT-4o", type: "reasoning", cost: "Medium" },
      "gpt-4-turbo": { name: "GPT-4 Turbo", type: "reasoning", cost: "High" },
    },
  },
  anthropic: {
    name: "Anthropic",
    models: {
      "claude-3-5-haiku-20241022": { name: "Claude 3.5 Haiku", type: "fast", cost: "Low" },
      "claude-sonnet-4-20250514": { name: "Claude Sonnet 4", type: "reasoning", cost: "Medium" },
      "claude-3-5-sonnet-20241022": { name: "Claude 3.5 Sonnet", type: "reasoning", cost: "Medium" },
    },
  },
  google: {
    name: "Google",
    models: {
      "gemini-2.0-flash-exp": { name: "Gemini 2.0 Flash", type: "fast", cost: "Free" },
      "gemini-exp-1206": { name: "Gemini Exp", type: "reasoning", cost: "Free" },
    },
  },
};

type ProviderKey = keyof typeof AVAILABLE_PROVIDERS;

interface ModelConfig {
  provider: string;
  model: string;
  reasoning_model: string;
  temperature: number;
}

const DEFAULT_MODEL_CONFIG: ModelConfig = {
  provider: "openai",
  model: "gpt-4o-mini",
  reasoning_model: "gpt-4o",
  temperature: 0.1,
};

interface ConnectionStatus {
  name: string;
  status: "connected" | "disconnected" | "checking";
  details?: string;
}

interface StorageStats {
  inputFiles: number;
  outputFiles: number;
  totalFiles: number;
}

interface RagSettingsTabProps {
  ragId: string;
  project: {
    id: string;
    name: string;
    description: string | null;
    slug: string | null;
    qdrant_collection: string;
    is_public: boolean;
    document_count: number;
    chunk_count: number;
    model_config_data?: ModelConfig | null;
  };
  onProjectUpdated: () => void;
  onProjectDeleted: () => void;
}

function getSupabase() {
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;
  return createBrowserClient(supabaseUrl, supabaseAnonKey);
}

async function fetchWithAuth(url: string, options: RequestInit = {}) {
  const supabase = getSupabase();
  const { data: { session } } = await supabase.auth.getSession();
  
  if (!session) {
    throw new Error("Not authenticated");
  }
  
  return fetch(url, {
    ...options,
    headers: {
      ...options.headers,
      "Authorization": `Bearer ${session.access_token}`,
      "Content-Type": "application/json",
    },
  });
}

export function RagSettingsTab({ ragId, project, onProjectUpdated, onProjectDeleted }: RagSettingsTabProps) {
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Settings state
  const [editName, setEditName] = useState(project.name);
  const [editDescription, setEditDescription] = useState(project.description || "");
  const [editSlug, setEditSlug] = useState(project.slug || "");
  const [editIsPublic, setEditIsPublic] = useState(project.is_public);
  const [isSaving, setIsSaving] = useState(false);
  const [copied, setCopied] = useState(false);
  
  // Danger zone state
  const [isResettingQdrant, setIsResettingQdrant] = useState(false);
  const [isResettingR2, setIsResettingR2] = useState(false);
  const [isResettingDocuments, setIsResettingDocuments] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [dangerConfirm, setDangerConfirm] = useState<string | null>(null);
  
  // Model configuration state
  const [modelConfig, setModelConfig] = useState<ModelConfig>(
    project.model_config_data || DEFAULT_MODEL_CONFIG
  );
  const [isSavingModelConfig, setIsSavingModelConfig] = useState(false);
  const [modelConfigError, setModelConfigError] = useState<string | null>(null);
  
  // Zotero state
  const [zoteroModalOpen, setZoteroModalOpen] = useState(false);
  const [zoteroConnection, setZoteroConnection] = useState<ZoteroConnection | null>(null);
  const [loadingZotero, setLoadingZotero] = useState(true);
  
  // Connection status
  const [connections, setConnections] = useState<ConnectionStatus[]>([
    { name: "Backend API", status: "checking", details: "Checking..." },
    { name: "Qdrant Cloud", status: "checking", details: "Checking..." },
    { name: "Cloudflare R2", status: "checking", details: "Checking..." },
  ]);
  
  // Storage stats
  const [storageStats, setStorageStats] = useState<StorageStats>({
    inputFiles: 0,
    outputFiles: 0,
    totalFiles: 0,
  });
  
  // Fetch connection status
  const fetchStatus = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    
    try {
      const newConnections: ConnectionStatus[] = [];
      
      // Check backend health
      try {
        const healthRes = await fetch(`${API_BASE_URL}/health`);
        if (healthRes.ok) {
          const health = await healthRes.json();
          newConnections.push({
            name: "Backend API",
            status: "connected",
            details: "Railway FastAPI",
          });
          
          // R2 from health
          newConnections.push({
            name: "Cloudflare R2",
            status: health.components?.r2 ? "connected" : "disconnected",
            details: health.components?.r2 ? "devchat-pdfs bucket" : "Connection failed",
          });
        } else {
          newConnections.push({ name: "Backend API", status: "disconnected", details: "Unreachable" });
          newConnections.push({ name: "Cloudflare R2", status: "disconnected", details: "Backend unreachable" });
        }
      } catch {
        newConnections.push({ name: "Backend API", status: "disconnected", details: "Unreachable" });
        newConnections.push({ name: "Cloudflare R2", status: "disconnected", details: "Backend unreachable" });
      }
      
      // Check Qdrant for this project's collection
      try {
        const qdrantRes = await fetchWithAuth(`${API_BASE_URL}/rags/${ragId}`);
        if (qdrantRes.ok) {
          const data = await qdrantRes.json();
          newConnections.push({
            name: "Qdrant Cloud",
            status: "connected",
            details: `${data.chunk_count.toLocaleString()} vectors in ${data.qdrant_collection}`,
          });
        } else {
          newConnections.push({ name: "Qdrant Cloud", status: "disconnected", details: "Collection not found" });
        }
      } catch {
        newConnections.push({ name: "Qdrant Cloud", status: "disconnected", details: "Connection failed" });
      }
      
      setConnections(newConnections);
      
      // Update storage stats from documents count
      setStorageStats({
        inputFiles: project.document_count,
        outputFiles: project.document_count,
        totalFiles: project.document_count * 2,
      });
      
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to check status");
    } finally {
      setIsLoading(false);
    }
  }, [ragId, project.document_count]);
  
  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);
  
  // Fetch Zotero connection status
  const fetchZoteroStatus = useCallback(async () => {
    setLoadingZotero(true);
    try {
      const connection = await getZoteroConnection(ragId);
      setZoteroConnection(connection);
    } catch (err) {
      console.error("Failed to check Zotero connection:", err);
    } finally {
      setLoadingZotero(false);
    }
  }, [ragId]);
  
  useEffect(() => {
    fetchZoteroStatus();
  }, [fetchZoteroStatus]);
  
  // Update local state when project changes
  useEffect(() => {
    setEditName(project.name);
    setEditDescription(project.description || "");
    setEditSlug(project.slug || "");
    setEditIsPublic(project.is_public);
  }, [project]);
  
  const testAllConnections = async () => {
    setConnections(prev => prev.map(c => ({ ...c, status: "checking" as const })));
    await fetchStatus();
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
  
  // Save settings
  const handleSaveSettings = async () => {
    setIsSaving(true);
    try {
      const res = await fetchWithAuth(`${API_BASE_URL}/rags/${ragId}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: editName,
          description: editDescription || null,
          slug: editSlug || null,
          is_public: editIsPublic,
        }),
      });
      
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "Failed to save");
      }
      
      onProjectUpdated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setIsSaving(false);
    }
  };
  
  // Save model configuration
  const handleSaveModelConfig = async () => {
    setIsSavingModelConfig(true);
    setModelConfigError(null);
    try {
      const res = await fetchWithAuth(`${API_BASE_URL}/rags/${ragId}/model-config`, {
        method: "PATCH",
        body: JSON.stringify(modelConfig),
      });
      
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "Failed to save model configuration");
      }
      
      onProjectUpdated();
    } catch (err) {
      setModelConfigError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setIsSavingModelConfig(false);
    }
  };
  
  // Handle provider change - reset models to provider's defaults
  const handleProviderChange = (newProvider: string) => {
    const providerData = AVAILABLE_PROVIDERS[newProvider as ProviderKey];
    if (!providerData) return;
    
    const modelKeys = Object.keys(providerData.models);
    const fastModel = modelKeys.find(
      k => providerData.models[k as keyof typeof providerData.models].type === "fast"
    ) || modelKeys[0];
    const reasoningModel = modelKeys.find(
      k => providerData.models[k as keyof typeof providerData.models].type === "reasoning"
    ) || modelKeys[0];
    
    setModelConfig({
      ...modelConfig,
      provider: newProvider,
      model: fastModel,
      reasoning_model: reasoningModel,
    });
  };
  
  const copyShareUrl = () => {
    const url = `${window.location.origin}/r/${editSlug || ragId}`;
    navigator.clipboard.writeText(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  
  // Danger zone actions
  const resetQdrant = async () => {
    if (dangerConfirm !== "qdrant") {
      setDangerConfirm("qdrant");
      return;
    }
    setIsResettingQdrant(true);
    setDangerConfirm(null);
    try {
      const res = await fetchWithAuth(`${API_BASE_URL}/rags/${ragId}/vectors`, { method: "DELETE" });
      if (!res.ok) throw new Error(await res.text());
      alert("Qdrant vectors reset successfully! Documents will need reprocessing.");
      await fetchStatus();
      onProjectUpdated();
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
      const res = await fetchWithAuth(`${API_BASE_URL}/rags/${ragId}/storage`, { method: "DELETE" });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      alert(`R2 cleared: ${data.deleted || 0} files deleted`);
      await fetchStatus();
      onProjectUpdated();
    } catch (err) {
      alert(`Failed to clear R2: ${err}`);
    } finally {
      setIsResettingR2(false);
    }
  };
  
  const resetDocuments = async () => {
    if (dangerConfirm !== "documents") {
      setDangerConfirm("documents");
      return;
    }
    setIsResettingDocuments(true);
    setDangerConfirm(null);
    try {
      const res = await fetchWithAuth(`${API_BASE_URL}/rags/${ragId}/documents`, { method: "DELETE" });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      alert(`Documents reset: ${data.deleted || 0} documents deleted`);
      await fetchStatus();
      onProjectUpdated();
    } catch (err) {
      alert(`Failed to reset documents: ${err}`);
    } finally {
      setIsResettingDocuments(false);
    }
  };
  
  const deleteProject = async () => {
    if (dangerConfirm !== "delete") {
      setDangerConfirm("delete");
      return;
    }
    setIsDeleting(true);
    setDangerConfirm(null);
    try {
      const res = await fetchWithAuth(`${API_BASE_URL}/rags/${ragId}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await res.text());
      onProjectDeleted();
    } catch (err) {
      alert(`Failed to delete project: ${err}`);
      setIsDeleting(false);
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
            Status of external services for this project
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
                onClick={testAllConnections}
                disabled={conn.status === "checking"}
              >
                <TestTube className="h-3 w-3 mr-1" />
                Test
              </Button>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Storage Stats */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Cloud className="h-5 w-5" />
            Project Storage
          </CardTitle>
          <CardDescription>
            Storage usage for this RAG project
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="p-4 rounded-lg bg-muted/50 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Collection</span>
              <Badge variant="secondary">{project.qdrant_collection}</Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Documents</span>
              <span className="text-sm font-medium">{project.document_count.toLocaleString()}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Vector Chunks</span>
              <span className="text-sm font-medium">{project.chunk_count.toLocaleString()}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">PDFs in R2</span>
              <span className="text-sm font-medium">{storageStats.inputFiles}</span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Zotero Integration */}
      <Card className="md:col-span-2">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Library className="h-5 w-5" />
            Zotero Integration
          </CardTitle>
          <CardDescription>
            Connect your Zotero library to sync references and PDFs
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {loadingZotero ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Checking connection...
            </div>
          ) : zoteroConnection ? (
            <div className="p-4 rounded-lg bg-muted/50 space-y-3">
              <div className="flex items-center gap-2">
                <CheckCircle className="h-4 w-4 text-green-600" />
                <span className="font-medium text-green-600">Connected to Zotero</span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div className="text-muted-foreground">Library Type</div>
                <div className="font-medium capitalize">{zoteroConnection.library_type}</div>
                <div className="text-muted-foreground">User/Group ID</div>
                <div className="font-medium">{zoteroConnection.zotero_user_id}</div>
                <div className="text-muted-foreground">Items Synced</div>
                <div className="font-medium">{zoteroConnection.total_items_synced}</div>
                {zoteroConnection.last_synced_at && (
                  <>
                    <div className="text-muted-foreground">Last Synced</div>
                    <div className="font-medium">
                      {new Date(zoteroConnection.last_synced_at).toLocaleString()}
                    </div>
                  </>
                )}
                {zoteroConnection.last_sync_error && (
                  <div className="col-span-2 text-red-600 text-xs mt-2">
                    Error: {zoteroConnection.last_sync_error}
                  </div>
                )}
              </div>
              <Button 
                variant="outline" 
                size="sm" 
                onClick={() => setZoteroModalOpen(true)}
                className="mt-2"
              >
                <Settings className="h-4 w-4 mr-2" />
                Manage Connection
              </Button>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-6 text-center">
              <Library className="h-12 w-12 text-muted-foreground mb-3" />
              <h3 className="font-medium mb-1">No Zotero Connection</h3>
              <p className="text-sm text-muted-foreground mb-4">
                Connect your Zotero account to sync your reference library
              </p>
              <Button onClick={() => setZoteroModalOpen(true)}>
                <Library className="h-4 w-4 mr-2" />
                Connect Zotero
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Zotero Modal */}
      <ConnectZoteroModal
        ragId={ragId}
        open={zoteroModalOpen}
        onOpenChange={setZoteroModalOpen}
        onSuccess={() => {
          fetchZoteroStatus();
        }}
      />

      {/* Project Settings */}
      <Card className="md:col-span-2">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Settings className="h-5 w-5" />
            Project Settings
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {error && (
            <div className="p-3 rounded-lg bg-red-50 text-red-600 text-sm">
              {error}
            </div>
          )}
          
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="name">Name</Label>
              <Input
                id="name"
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
              />
            </div>
            
            <div className="space-y-2">
              <Label htmlFor="slug">URL Slug (optional)</Label>
              <Input
                id="slug"
                value={editSlug}
                onChange={(e) => setEditSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "-"))}
                placeholder="my-knowledge-base"
              />
            </div>
          </div>
          
          <div className="space-y-2">
            <Label htmlFor="description">Description</Label>
            <Textarea
              id="description"
              value={editDescription}
              onChange={(e) => setEditDescription(e.target.value)}
              rows={2}
            />
          </div>
          
          <div className="flex items-center justify-between border rounded-lg p-4">
            <div className="flex items-center gap-3">
              {editIsPublic ? (
                <Globe className="h-5 w-5 text-green-600" />
              ) : (
                <Lock className="h-5 w-5" />
              )}
              <div>
                <p className="font-medium">
                  {editIsPublic ? "Public" : "Private"}
                </p>
                <p className="text-sm text-muted-foreground">
                  {editIsPublic 
                    ? "Anyone with the link can chat with this RAG"
                    : "Only you can access this RAG"}
                </p>
              </div>
            </div>
            <Switch
              checked={editIsPublic}
              onCheckedChange={setEditIsPublic}
            />
          </div>

          {editIsPublic && (
            <div className="flex items-center gap-2">
              <Input
                readOnly
                value={`${typeof window !== 'undefined' ? window.location.origin : ''}/r/${editSlug || ragId}`}
                className="flex-1"
              />
              <Button variant="outline" size="icon" onClick={copyShareUrl}>
                {copied ? (
                  <Check className="h-4 w-4 text-green-600" />
                ) : (
                  <Copy className="h-4 w-4" />
                )}
              </Button>
            </div>
          )}
          
          <Button onClick={handleSaveSettings} disabled={isSaving}>
            {isSaving ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Saving...
              </>
            ) : (
              "Save Changes"
            )}
          </Button>
        </CardContent>
      </Card>

      {/* LLM Configuration */}
      <Card className="md:col-span-2">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Cpu className="h-5 w-5" />
            LLM Configuration
          </CardTitle>
          <CardDescription>
            Choose which AI models power your RAG&apos;s responses. Different providers offer varying quality, speed, and cost trade-offs.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {modelConfigError && (
            <div className="p-3 rounded-lg bg-red-50 text-red-600 text-sm">
              {modelConfigError}
            </div>
          )}
          
          {/* Provider Selection */}
          <div className="space-y-2">
            <Label>AI Provider</Label>
            <Select
              value={modelConfig.provider}
              onValueChange={handleProviderChange}
            >
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(AVAILABLE_PROVIDERS).map(([key, provider]) => (
                  <SelectItem key={key} value={key}>
                    {provider.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          
          <div className="grid gap-4 md:grid-cols-2">
            {/* Fast Model */}
            <div className="space-y-2">
              <Label>Fast Model (Extraction)</Label>
              <Select
                value={modelConfig.model}
                onValueChange={(value) => setModelConfig({ ...modelConfig, model: value })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(
                    AVAILABLE_PROVIDERS[modelConfig.provider as ProviderKey]?.models || {}
                  ).map(([key, model]) => (
                    <SelectItem key={key} value={key}>
                      <span className="flex items-center gap-2">
                        {model.name}
                        <Badge variant={model.type === "fast" ? "secondary" : "outline"} className="text-xs">
                          {model.cost}
                        </Badge>
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                Used for quick tasks like claim extraction
              </p>
            </div>
            
            {/* Reasoning Model */}
            <div className="space-y-2">
              <Label>Reasoning Model (Synthesis)</Label>
              <Select
                value={modelConfig.reasoning_model}
                onValueChange={(value) => setModelConfig({ ...modelConfig, reasoning_model: value })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(
                    AVAILABLE_PROVIDERS[modelConfig.provider as ProviderKey]?.models || {}
                  ).map(([key, model]) => (
                    <SelectItem key={key} value={key}>
                      <span className="flex items-center gap-2">
                        {model.name}
                        <Badge variant={model.type === "reasoning" ? "default" : "outline"} className="text-xs">
                          {model.cost}
                        </Badge>
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                Used for generating comprehensive answers
              </p>
            </div>
          </div>
          
          {/* Temperature */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>Temperature</Label>
              <span className="text-sm text-muted-foreground font-mono">
                {modelConfig.temperature.toFixed(1)}
              </span>
            </div>
            <Slider
              value={[modelConfig.temperature * 10]}
              onValueChange={(values) => setModelConfig({ ...modelConfig, temperature: values[0] / 10 })}
              min={0}
              max={10}
              step={1}
              className="w-full"
            />
            <p className="text-xs text-muted-foreground">
              Lower = more consistent, higher = more creative. Recommended: 0.1 for factual research.
            </p>
          </div>
          
          <Button onClick={handleSaveModelConfig} disabled={isSavingModelConfig}>
            {isSavingModelConfig ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Saving...
              </>
            ) : (
              "Save Model Configuration"
            )}
          </Button>
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
            Destructive actions for this project. Click once to arm, click again to execute.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="p-4 rounded-lg border border-red-200 bg-red-50/50 dark:bg-red-950/20 flex flex-col justify-between min-h-[120px]">
              <div>
                <h4 className="font-medium text-red-700 dark:text-red-400">Reset Qdrant Vectors</h4>
                <p className="text-xs text-muted-foreground mt-1">Delete all vector embeddings for this project. Documents will need reprocessing.</p>
              </div>
              <Button 
                variant={dangerConfirm === "qdrant" ? "destructive" : "outline"}
                size="sm"
                onClick={resetQdrant}
                disabled={isResettingQdrant}
                className={`w-full mt-3 ${dangerConfirm === "qdrant" ? "" : "border-red-300 text-red-600 hover:bg-red-100"}`}
              >
                {isResettingQdrant ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Trash2 className="h-4 w-4 mr-2" />
                )}
                <span className="min-w-[100px]">
                  {dangerConfirm === "qdrant" ? "Confirm Reset" : "Reset Vectors"}
                </span>
              </Button>
            </div>

            <div className="p-4 rounded-lg border border-red-200 bg-red-50/50 dark:bg-red-950/20 flex flex-col justify-between min-h-[120px]">
              <div>
                <h4 className="font-medium text-red-700 dark:text-red-400">Clear R2 Storage</h4>
                <p className="text-xs text-muted-foreground mt-1">Delete PDFs and processed outputs for this project from R2.</p>
              </div>
              <Button 
                variant={dangerConfirm === "r2" ? "destructive" : "outline"}
                size="sm"
                onClick={clearR2}
                disabled={isResettingR2}
                className={`w-full mt-3 ${dangerConfirm === "r2" ? "" : "border-red-300 text-red-600 hover:bg-red-100"}`}
              >
                {isResettingR2 ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Trash2 className="h-4 w-4 mr-2" />
                )}
                <span className="min-w-[100px]">
                  {dangerConfirm === "r2" ? "Confirm Clear" : "Clear R2"}
                </span>
              </Button>
            </div>

            <div className="p-4 rounded-lg border border-red-200 bg-red-50/50 dark:bg-red-950/20 flex flex-col justify-between min-h-[120px]">
              <div>
                <h4 className="font-medium text-red-700 dark:text-red-400">Reset Documents</h4>
                <p className="text-xs text-muted-foreground mt-1">Delete all document records and metadata from the database.</p>
              </div>
              <Button 
                variant={dangerConfirm === "documents" ? "destructive" : "outline"}
                size="sm"
                onClick={resetDocuments}
                disabled={isResettingDocuments}
                className={`w-full mt-3 ${dangerConfirm === "documents" ? "" : "border-red-300 text-red-600 hover:bg-red-100"}`}
              >
                {isResettingDocuments ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Trash2 className="h-4 w-4 mr-2" />
                )}
                <span className="min-w-[100px]">
                  {dangerConfirm === "documents" ? "Confirm Reset" : "Reset Docs"}
                </span>
              </Button>
            </div>

            <div className="p-4 rounded-lg border border-red-500 bg-red-100/50 dark:bg-red-950/40 flex flex-col justify-between min-h-[120px]">
              <div>
                <h4 className="font-medium text-red-700 dark:text-red-400">⚠️ Delete Project</h4>
                <p className="text-xs text-muted-foreground mt-1">Permanently delete this project and ALL its data.</p>
              </div>
              <Button 
                variant={dangerConfirm === "delete" ? "destructive" : "outline"}
                size="sm"
                onClick={deleteProject}
                disabled={isDeleting}
                className={`w-full mt-3 ${dangerConfirm === "delete" ? "" : "border-red-500 text-red-700 hover:bg-red-200"}`}
              >
                {isDeleting ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Trash2 className="h-4 w-4 mr-2" />
                )}
                <span className="min-w-[100px]">
                  {dangerConfirm === "delete" ? "Confirm Delete" : "Delete Project"}
                </span>
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
