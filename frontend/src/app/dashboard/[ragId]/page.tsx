"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  ArrowLeft,
  Upload,
  FileText,
  Trash2,
  Loader2,
  Settings,
  ExternalLink,
  RefreshCw,
  Play,
  Copy,
  Check,
  Globe,
  Lock,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { RagMetadataTab } from "@/components/dashboard/RagMetadataTab";
import { RagSettingsTab } from "@/components/dashboard/RagSettingsTab";

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

interface Document {
  id: string;
  filename: string;
  original_filename: string;
  title?: string;
  authors?: string;
  year?: number;
  doi?: string;
  status: "pending" | "processing" | "completed" | "failed";
  error_message: string | null;
  chunk_count: number;
  created_at: string;
  processed_at: string | null;
}

interface ProcessingJob {
  id: string;
  job_type: string;
  status: string;
  progress: number;
  message: string | null;
  created_at: string;
}

export default function RAGAdminPage() {
  const params = useParams();
  const router = useRouter();
  const ragId = params.ragId as string;
  const { session, isLoading: authLoading, isConfigured } = useAuth();
  
  // Project state
  const [project, setProject] = useState<RAGProject | null>(null);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [jobs, setJobs] = useState<ProcessingJob[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Settings state
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editSlug, setEditSlug] = useState("");
  const [editIsPublic, setEditIsPublic] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  
  // Upload state
  const [uploadingFiles, setUploadingFiles] = useState<File[]>([]);
  const [uploadProgress, setUploadProgress] = useState<Record<string, number>>({});
  const [isUploading, setIsUploading] = useState(false);
  
  // Delete dialog
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  
  // Copied state
  const [copied, setCopied] = useState(false);

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
      setEditName(data.name);
      setEditDescription(data.description || "");
      setEditSlug(data.slug || "");
      setEditIsPublic(data.is_public);
    } catch (err) {
      setError("Failed to connect to server");
    } finally {
      setIsLoading(false);
    }
  }, [ragId, session?.access_token]);

  const fetchDocuments = useCallback(async () => {
    if (!session?.access_token) return;
    
    try {
      const response = await fetch(`${API_BASE_URL}/rags/${ragId}/documents`, {
        headers: {
          Authorization: `Bearer ${session.access_token}`,
        },
      });
      
      if (response.ok) {
        const data = await response.json();
        setDocuments(data.documents || []);
      }
    } catch (err) {
      console.error("Failed to fetch documents:", err);
    }
  }, [ragId, session?.access_token]);

  const fetchJobs = useCallback(async () => {
    if (!session?.access_token) return;
    
    try {
      const response = await fetch(`${API_BASE_URL}/rags/${ragId}/jobs`, {
        headers: {
          Authorization: `Bearer ${session.access_token}`,
        },
      });
      
      if (response.ok) {
        const data = await response.json();
        setJobs(data.jobs || []);
      }
    } catch (err) {
      console.error("Failed to fetch jobs:", err);
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
      fetchDocuments();
      fetchJobs();
    }
  }, [authLoading, session, isConfigured, router, fetchProject, fetchDocuments, fetchJobs]);

  // Poll for job updates
  useEffect(() => {
    const hasActiveJobs = jobs.some(j => j.status === "pending" || j.status === "running");
    if (!hasActiveJobs) return;
    
    const interval = setInterval(() => {
      fetchJobs();
      fetchDocuments();
      fetchProject();
    }, 5000);
    
    return () => clearInterval(interval);
  }, [jobs, fetchJobs, fetchDocuments, fetchProject]);

  const handleSaveSettings = async () => {
    if (!session?.access_token || !project) return;
    
    setIsSaving(true);
    try {
      const response = await fetch(`${API_BASE_URL}/rags/${ragId}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({
          name: editName,
          description: editDescription || null,
          slug: editSlug || null,
          is_public: editIsPublic,
        }),
      });
      
      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || "Failed to save");
      }
      
      await fetchProject();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save settings");
    } finally {
      setIsSaving(false);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    setUploadingFiles(files);
  };

  const handleUpload = async () => {
    if (!session?.access_token || uploadingFiles.length === 0) return;
    
    setIsUploading(true);
    
    for (const file of uploadingFiles) {
      try {
        const formData = new FormData();
        formData.append("file", file);
        
        setUploadProgress(prev => ({ ...prev, [file.name]: 0 }));
        
        const response = await fetch(`${API_BASE_URL}/rags/${ragId}/documents/upload`, {
          method: "POST",
          headers: {
            Authorization: `Bearer ${session.access_token}`,
          },
          body: formData,
        });
        
        if (!response.ok) {
          console.error(`Failed to upload ${file.name}`);
        }
        
        setUploadProgress(prev => ({ ...prev, [file.name]: 100 }));
      } catch (err) {
        console.error(`Error uploading ${file.name}:`, err);
      }
    }
    
    setIsUploading(false);
    setUploadingFiles([]);
    setUploadProgress({});
    fetchDocuments();
  };

  const handleProcessAll = async () => {
    if (!session?.access_token) return;
    
    try {
      const response = await fetch(`${API_BASE_URL}/rags/${ragId}/process`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${session.access_token}`,
        },
      });
      
      if (response.ok) {
        fetchJobs();
      }
    } catch (err) {
      console.error("Failed to start processing:", err);
    }
  };

  const handleDeleteDocument = async (docId: string) => {
    if (!session?.access_token) return;
    
    try {
      await fetch(`${API_BASE_URL}/rags/${ragId}/documents/${docId}`, {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${session.access_token}`,
        },
      });
      
      fetchDocuments();
      fetchProject();
    } catch (err) {
      console.error("Failed to delete document:", err);
    }
  };

  const handleDeleteProject = async () => {
    if (!session?.access_token) return;
    
    setIsDeleting(true);
    try {
      const response = await fetch(`${API_BASE_URL}/rags/${ragId}`, {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${session.access_token}`,
        },
      });
      
      if (response.ok) {
        router.push("/dashboard");
      }
    } catch (err) {
      setError("Failed to delete project");
    } finally {
      setIsDeleting(false);
    }
  };

  const copyShareUrl = () => {
    const url = project?.slug 
      ? `${window.location.origin}/r/${project.slug}`
      : `${window.location.origin}/r/${ragId}`;
    navigator.clipboard.writeText(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
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

  const pendingDocs = documents.filter(d => d.status === "pending");
  const processingDocs = documents.filter(d => d.status === "processing");
  const completedDocs = documents.filter(d => d.status === "completed");
  const failedDocs = documents.filter(d => d.status === "failed");

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

          {/* Documents Tab */}
          <TabsContent value="documents" className="space-y-6">
            {/* Upload Section */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Upload className="h-5 w-5" />
                  Upload Documents
                </CardTitle>
                <CardDescription>
                  Upload PDF files to add to your knowledge base
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <Input
                    type="file"
                    accept=".pdf"
                    multiple
                    onChange={handleFileSelect}
                    disabled={isUploading}
                  />
                  
                  {uploadingFiles.length > 0 && (
                    <div className="space-y-2">
                      {uploadingFiles.map(file => (
                        <div key={file.name} className="flex items-center gap-2 text-sm">
                          <FileText className="h-4 w-4" />
                          <span className="flex-1 truncate">{file.name}</span>
                          {uploadProgress[file.name] !== undefined && (
                            <Progress value={uploadProgress[file.name]} className="w-20" />
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                  
                  <Button onClick={handleUpload} disabled={isUploading || uploadingFiles.length === 0}>
                    {isUploading ? (
                      <>
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                        Uploading...
                      </>
                    ) : (
                      <>
                        <Upload className="h-4 w-4 mr-2" />
                        Upload {uploadingFiles.length} file(s)
                      </>
                    )}
                  </Button>
                </div>
              </CardContent>
            </Card>

            {/* Process Button */}
            {pendingDocs.length > 0 && (
              <Alert>
                <AlertDescription className="flex items-center justify-between">
                  <span>
                    {pendingDocs.length} document(s) ready to process
                  </span>
                  <Button size="sm" onClick={handleProcessAll}>
                    <Play className="h-4 w-4 mr-2" />
                    Process All
                  </Button>
                </AlertDescription>
              </Alert>
            )}

            {/* Document List */}
            <Card>
              <CardHeader>
                <CardTitle>Documents ({documents.length})</CardTitle>
              </CardHeader>
              <CardContent>
                {documents.length === 0 ? (
                  <p className="text-muted-foreground text-center py-8">
                    No documents yet. Upload some PDFs to get started.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {documents.map(doc => (
                      <div
                        key={doc.id}
                        className="flex items-center justify-between p-3 border rounded-lg"
                      >
                        <div className="flex items-center gap-3 flex-1 min-w-0">
                          <FileText className="h-5 w-5 flex-shrink-0" />
                          <div className="min-w-0">
                            <p className="font-medium truncate">{doc.original_filename}</p>
                            <p className="text-sm text-muted-foreground">
                              {doc.chunk_count} chunks
                            </p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <Badge
                            variant={
                              doc.status === "completed" ? "default" :
                              doc.status === "processing" ? "secondary" :
                              doc.status === "failed" ? "destructive" :
                              "outline"
                            }
                          >
                            {doc.status}
                          </Badge>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleDeleteDocument(doc.id)}
                          >
                            <Trash2 className="h-4 w-4 text-destructive" />
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Metadata Tab */}
          <TabsContent value="metadata" className="space-y-6">
            <RagMetadataTab ragId={ragId} />
          </TabsContent>

          {/* Processing Tab */}
          <TabsContent value="processing" className="space-y-6">
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle>Processing Jobs</CardTitle>
                  <Button variant="outline" size="sm" onClick={fetchJobs}>
                    <RefreshCw className="h-4 w-4 mr-2" />
                    Refresh
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                {jobs.length === 0 ? (
                  <p className="text-muted-foreground text-center py-8">
                    No processing jobs
                  </p>
                ) : (
                  <div className="space-y-4">
                    {jobs.map(job => (
                      <div key={job.id} className="border rounded-lg p-4">
                        <div className="flex items-center justify-between mb-2">
                          <span className="font-medium">{job.job_type}</span>
                          <Badge
                            variant={
                              job.status === "completed" ? "default" :
                              job.status === "running" ? "secondary" :
                              job.status === "failed" ? "destructive" :
                              "outline"
                            }
                          >
                            {job.status}
                          </Badge>
                        </div>
                        {job.status === "running" && (
                          <Progress value={job.progress} className="mb-2" />
                        )}
                        {job.message && (
                          <p className="text-sm text-muted-foreground">{job.message}</p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
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
