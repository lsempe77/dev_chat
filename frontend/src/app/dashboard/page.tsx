"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Database,
  Plus,
  FileText,
  Settings,
  Trash2,
  Loader2,
  LogOut,
  ArrowLeft,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

interface RAGProject {
  id: string;
  name: string;
  description: string | null;
  qdrant_collection: string;
  status: string;
  document_count: number;
  chunk_count: number;
  created_at: string;
  updated_at: string;
}

export default function DashboardPage() {
  const router = useRouter();
  const { user, session, isLoading: authLoading, signOut, isConfigured } = useAuth();
  
  const [projects, setProjects] = useState<RAGProject[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Create project dialog
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [newProjectDescription, setNewProjectDescription] = useState("");
  const [isCreating, setIsCreating] = useState(false);

  // Redirect if not authenticated
  useEffect(() => {
    if (!authLoading && !user && isConfigured) {
      router.push("/auth");
    }
  }, [authLoading, user, router, isConfigured]);

  // Fetch projects
  useEffect(() => {
    if (session?.access_token) {
      fetchProjects();
    }
  }, [session]);

  const fetchProjects = async () => {
    if (!session?.access_token) return;
    
    setIsLoading(true);
    setError(null);
    
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/rags`,
        {
          headers: {
            Authorization: `Bearer ${session.access_token}`,
          },
        }
      );
      
      if (!response.ok) {
        throw new Error("Failed to fetch projects");
      }
      
      const data = await response.json();
      setProjects(data.projects || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load projects");
    } finally {
      setIsLoading(false);
    }
  };

  const createProject = async () => {
    if (!session?.access_token || !newProjectName.trim()) return;
    
    setIsCreating(true);
    setError(null);
    
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/rags`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${session.access_token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            name: newProjectName.trim(),
            description: newProjectDescription.trim() || null,
          }),
        }
      );
      
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || "Failed to create project");
      }
      
      // Refresh projects
      await fetchProjects();
      
      // Close dialog and reset form
      setShowCreateDialog(false);
      setNewProjectName("");
      setNewProjectDescription("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create project");
    } finally {
      setIsCreating(false);
    }
  };

  const deleteProject = async (projectId: string) => {
    if (!session?.access_token) return;
    if (!confirm("Are you sure you want to delete this RAG project? This cannot be undone.")) {
      return;
    }
    
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/rags/${projectId}`,
        {
          method: "DELETE",
          headers: {
            Authorization: `Bearer ${session.access_token}`,
          },
        }
      );
      
      if (!response.ok) {
        throw new Error("Failed to delete project");
      }
      
      // Refresh projects
      await fetchProjects();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete project");
    }
  };

  const handleLogout = async () => {
    await signOut();
    router.push("/");
  };

  // Loading state
  if (authLoading || (!user && isConfigured)) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          <span>Loading...</span>
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
              <Link href="/">
                <Button variant="ghost" size="sm" className="gap-2">
                  <ArrowLeft className="h-4 w-4" />
                  Research Chat
                </Button>
              </Link>
              <div className="h-6 w-px bg-border" />
              <div className="flex items-center gap-2">
                <Database className="h-5 w-5 text-primary" />
                <h1 className="text-xl font-semibold">My RAG Projects</h1>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <span className="text-sm text-muted-foreground">
                {user?.email}
              </span>
              <Button variant="outline" size="sm" onClick={handleLogout} className="gap-2">
                <LogOut className="h-4 w-4" />
                Logout
              </Button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-4 py-8">
        {error && (
          <Alert variant="destructive" className="mb-6">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {/* Create Project Button */}
        <div className="flex justify-between items-center mb-6">
          <div>
            <h2 className="text-2xl font-bold">Your Knowledge Bases</h2>
            <p className="text-muted-foreground">
              Create and manage your RAG projects
            </p>
          </div>
          
          <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
            <DialogTrigger asChild>
              <Button className="gap-2">
                <Plus className="h-4 w-4" />
                New RAG Project
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Create New RAG Project</DialogTitle>
                <DialogDescription>
                  Create a new knowledge base to upload documents and chat with your data.
                </DialogDescription>
              </DialogHeader>
              
              <div className="space-y-4 py-4">
                <div className="space-y-2">
                  <Label htmlFor="project-name">Project Name</Label>
                  <Input
                    id="project-name"
                    placeholder="My Research Papers"
                    value={newProjectName}
                    onChange={(e) => setNewProjectName(e.target.value)}
                    disabled={isCreating}
                  />
                </div>
                
                <div className="space-y-2">
                  <Label htmlFor="project-description">Description (optional)</Label>
                  <Textarea
                    id="project-description"
                    placeholder="A collection of academic papers on..."
                    value={newProjectDescription}
                    onChange={(e) => setNewProjectDescription(e.target.value)}
                    disabled={isCreating}
                  />
                </div>
              </div>
              
              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={() => setShowCreateDialog(false)}
                  disabled={isCreating}
                >
                  Cancel
                </Button>
                <Button
                  onClick={createProject}
                  disabled={isCreating || !newProjectName.trim()}
                >
                  {isCreating ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Creating...
                    </>
                  ) : (
                    "Create Project"
                  )}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>

        {/* Projects Grid */}
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : projects.length === 0 ? (
          <Card className="py-12">
            <CardContent className="text-center">
              <Database className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
              <h3 className="text-lg font-semibold mb-2">No RAG Projects Yet</h3>
              <p className="text-muted-foreground mb-4">
                Create your first knowledge base to get started.
              </p>
              <Button onClick={() => setShowCreateDialog(true)} className="gap-2">
                <Plus className="h-4 w-4" />
                Create Your First Project
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {projects.map((project) => (
              <Card key={project.id} className="hover:shadow-md transition-shadow">
                <CardHeader>
                  <div className="flex items-start justify-between">
                    <div>
                      <CardTitle className="text-lg">{project.name}</CardTitle>
                      <CardDescription className="line-clamp-2">
                        {project.description || "No description"}
                      </CardDescription>
                    </div>
                    <div className="flex gap-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => deleteProject(project.id)}
                        className="text-destructive hover:text-destructive"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="flex gap-4 text-sm text-muted-foreground mb-4">
                    <span className="flex items-center gap-1">
                      <FileText className="h-4 w-4" />
                      {project.document_count} docs
                    </span>
                    <span>
                      {project.chunk_count} chunks
                    </span>
                  </div>
                  
                  <div className="flex gap-2">
                    <Link href={`/dashboard/${project.id}`} className="flex-1">
                      <Button variant="outline" className="w-full gap-2">
                        <Settings className="h-4 w-4" />
                        Manage
                      </Button>
                    </Link>
                    <Link href={`/?rag=${project.id}`} className="flex-1">
                      <Button className="w-full">
                        Chat
                      </Button>
                    </Link>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
