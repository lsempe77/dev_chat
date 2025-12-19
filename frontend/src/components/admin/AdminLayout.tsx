"use client";

import { useState, useEffect } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { 
  Upload, 
  FileText, 
  Activity, 
  Settings, 
  ArrowLeft,
  Database,
  Loader2,
  Tag
} from "lucide-react";
import Link from "next/link";
import { UploadTab } from "./UploadTab";
import { DocumentsTab } from "./DocumentsTab";
import { ProcessingTab } from "./ProcessingTab";
import { SettingsTab } from "./SettingsTab";
import { MetadataTab } from "./MetadataTab";
import { checkHealth, getCollectionInfo } from "@/lib/admin-api";

export function AdminLayout() {
  const [activeTab, setActiveTab] = useState("upload");
  const [connectionStatus, setConnectionStatus] = useState<{
    modal: boolean;
    qdrant: boolean;
    loading: boolean;
  }>({ modal: false, qdrant: false, loading: true });

  // Check connections on mount
  useEffect(() => {
    const checkConnections = async () => {
      try {
        const [healthResult, collectionResult] = await Promise.allSettled([
          checkHealth(),
          getCollectionInfo(),
        ]);
        
        setConnectionStatus({
          modal: healthResult.status === "fulfilled",
          qdrant: collectionResult.status === "fulfilled",
          loading: false,
        });
      } catch {
        setConnectionStatus({ modal: false, qdrant: false, loading: false });
      }
    };
    
    checkConnections();
  }, []);

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b bg-card">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Link href="/">
                <Button variant="ghost" size="sm" className="gap-2">
                  <ArrowLeft className="h-4 w-4" />
                  Back to Research
                </Button>
              </Link>
              <div className="h-6 w-px bg-border" />
              <div className="flex items-center gap-2">
                <Database className="h-5 w-5 text-primary" />
                <h1 className="text-xl font-semibold">Document Management</h1>
              </div>
            </div>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              {connectionStatus.loading ? (
                <span className="flex items-center gap-1">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  Checking connections...
                </span>
              ) : (
                <>
                  <span className="flex items-center gap-1">
                    <span className={`h-2 w-2 rounded-full ${connectionStatus.modal ? "bg-green-500" : "bg-red-500"}`} />
                    Backend {connectionStatus.modal ? "Online" : "Offline"}
                  </span>
                  <span className="text-border">|</span>
                  <span className="flex items-center gap-1">
                    <span className={`h-2 w-2 rounded-full ${connectionStatus.qdrant ? "bg-green-500" : "bg-red-500"}`} />
                    Qdrant {connectionStatus.qdrant ? "Online" : "Offline"}
                  </span>
                </>
              )}
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-4 py-6">
        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
          <TabsList className="grid w-full max-w-2xl grid-cols-5">
            <TabsTrigger value="upload" className="gap-2">
              <Upload className="h-4 w-4" />
              Upload
            </TabsTrigger>
            <TabsTrigger value="processing" className="gap-2">
              <Activity className="h-4 w-4" />
              Processing
            </TabsTrigger>
            <TabsTrigger value="documents" className="gap-2">
              <FileText className="h-4 w-4" />
              Documents
            </TabsTrigger>
            <TabsTrigger value="metadata" className="gap-2">
              <Tag className="h-4 w-4" />
              Metadata
            </TabsTrigger>
            <TabsTrigger value="settings" className="gap-2">
              <Settings className="h-4 w-4" />
              Settings
            </TabsTrigger>
          </TabsList>

          <TabsContent value="upload" className="space-y-4">
            <UploadTab />
          </TabsContent>

          <TabsContent value="processing" className="space-y-4">
            <ProcessingTab />
          </TabsContent>

          <TabsContent value="documents" className="space-y-4">
            <DocumentsTab />
          </TabsContent>

          <TabsContent value="metadata" className="space-y-4">
            <MetadataTab />
          </TabsContent>

          <TabsContent value="settings" className="space-y-4">
            <SettingsTab />
          </TabsContent>
        </Tabs>
      </main>
    </div>
  );
}
