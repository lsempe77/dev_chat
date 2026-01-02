"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  ArrowLeft,
  Loader2,
  ExternalLink,
  Globe,
  Lock,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { RagMetadataTab } from "@/components/dashboard/RagMetadataTab";
import { RagSettingsTab } from "@/components/dashboard/RagSettingsTab";
import { RagUploadTab } from "@/components/dashboard/RagUploadTab";
import { RagDocumentsTab } from "@/components/dashboard/RagDocumentsTab";
import { RagProcessingTab } from "@/components/dashboard/RagProcessingTab";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface RAGProject {
  id: string;
  name: string;
  description: string | null;
  slug: string | null;
  qdrant_collection: string;
  is_public: boolean;
  status: string;
  document_count: number;
  chunk_count: number;
  created_at: string;
  updated_at: string;
}

export default function RAGAdminPage() {
  const params = useParams();
  const router = useRouter();
  const ragId = params.ragId as string;
  const { session, isLoading: authLoading, isConfigured } = useAuth();
  
  // Project state
  const [project, setProject] = useState<RAGProject | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchProject = useCallback(async () => {
    if (!session?.access_token) return;
    
    try {
      const response = await fetch(`${API_BASE_URL}/rags/${ragId}`, {
        headers: {
          Authorization: `Bearer ${session.access_token}`,
        },
      });
      
      if (!response.ok) {
        if (response.status === 404) {
          setError("Project not found");
        } else if (response.status === 403) {
          setError("You don't have access to this project");
        } else {
          setError("Failed to load project");
        }
        return;
      }
      
      const data = await response.json();
      setProject(data);
    } catch (err) {
      setError("Failed to connect to server");
    } finally {
      setIsLoading(false);
    }
  }, [ragId, session?.access_token]);

  // Initial load
  useEffect(() => {
    if (!authLoading && !session && isConfigured) {
      router.push("/auth");
      return;
    }
    
    if (session?.access_token) {
      fetchProject();
    }
  }, [authLoading, session, isConfigured, router, fetchProject]);

  const handleDeleteProject = async () => {
    // Called by RagSettingsTab after successful deletion - just redirect
    router.push("/dashboard");
  };

  // Loading state
  if (authLoading || isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          <span>Loading...</span>
        </div>
      </div>
    );
  }

  // Error state
  if (error || !project) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-center">
          <h1 className="text-2xl font-bold mb-2">{error || "Project not found"}</h1>
          <Link href="/dashboard">
            <Button className="mt-4">Back to Dashboard</Button>
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b bg-card">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Link href="/dashboard">
                <Button variant="ghost" size="sm" className="gap-1">
                  <ArrowLeft className="h-4 w-4" />
                  Back
                </Button>
              </Link>
              <div>
                <h1 className="text-2xl font-bold">{project.name}</h1>
                <p className="text-sm text-muted-foreground">
                  {project.document_count} documents • {project.chunk_count} chunks
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {project.is_public && (
                <Link href={`/r/${project.slug || ragId}`} target="_blank">
                  <Button variant="outline" size="sm" className="gap-1">
                    <ExternalLink className="h-4 w-4" />
                    View Public Page
                  </Button>
                </Link>
              )}
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-4 py-6">
        <Tabs defaultValue="documents" className="space-y-6">
          <TabsList>
            <TabsTrigger value="documents">Documents</TabsTrigger>
            <TabsTrigger value="metadata">Metadata</TabsTrigger>
            <TabsTrigger value="processing">Processing</TabsTrigger>
            <TabsTrigger value="settings">Settings</TabsTrigger>
          </TabsList>

          {/* Documents Tab - forceMount keeps component mounted to preserve upload state */}
          <TabsContent value="documents" className="space-y-6" forceMount>
            {/* Upload Section */}
            {session?.access_token && (
              <RagUploadTab
                ragId={ragId}
                accessToken={session.access_token}
                apiBaseUrl={API_BASE_URL}
                onUploadComplete={fetchProject}
              />
            )}

            {/* Documents List */}
            {session?.access_token && (
              <RagDocumentsTab
                ragId={ragId}
                accessToken={session.access_token}
                onDocumentsChanged={fetchProject}
              />
            )}
          </TabsContent>

          {/* Metadata Tab */}
          <TabsContent value="metadata" className="space-y-6">
            <RagMetadataTab ragId={ragId} />
          </TabsContent>

          {/* Processing Tab - forceMount to preserve auto-refresh state */}
          <TabsContent value="processing" className="space-y-6" forceMount>
            {session?.access_token && (
              <RagProcessingTab
                ragId={ragId}
                accessToken={session.access_token}
                onProcessingComplete={fetchProject}
              />
            )}
          </TabsContent>

          {/* Settings Tab */}
          <TabsContent value="settings" className="space-y-6">
            <RagSettingsTab 
              ragId={ragId}
              project={project}
              onProjectUpdated={fetchProject}
              onProjectDeleted={handleDeleteProject}
            />
          </TabsContent>
        </Tabs>
      </main>
    </div>
  );
}
