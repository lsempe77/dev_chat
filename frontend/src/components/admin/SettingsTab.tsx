"use client";

import { useState } from "react";
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
  Cpu
} from "lucide-react";

interface ConnectionStatus {
  name: string;
  status: "connected" | "disconnected" | "checking";
  details?: string;
}

export function SettingsTab() {
  const [isSaving, setIsSaving] = useState(false);
  const [connections, setConnections] = useState<ConnectionStatus[]>([
    { name: "Cloudflare R2", status: "connected", details: "devchat-pdfs bucket" },
    { name: "Qdrant Cloud", status: "connected", details: "1,234 vectors" },
    { name: "Modal", status: "connected", details: "2 workers available" },
    { name: "Cohere API", status: "connected", details: "embed-v4.0" },
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

  const testConnection = async (name: string) => {
    setConnections(prev => prev.map(c => 
      c.name === name ? { ...c, status: "checking" as const } : c
    ));
    
    // Simulate API call
    await new Promise(resolve => setTimeout(resolve, 1500));
    
    setConnections(prev => prev.map(c => 
      c.name === name ? { ...c, status: "connected" as const } : c
    ));
  };

  const saveSettings = async () => {
    setIsSaving(true);
    
    // TODO: Save to backend
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    setIsSaving(false);
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
    </div>
  );
}
