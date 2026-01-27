"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Database,
  MessageSquare,
  Upload,
  Users,
  ArrowRight,
  Shield,
  Search,
  FileText,
  BookOpen,
  Zap,
  Target,
  BarChart3,
  Settings,
  Link2,
  CheckCircle2
} from "lucide-react";

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b bg-card">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <h1 className="text-2xl font-bold">RAG Platform</h1>
            <div className="flex items-center gap-4">
              <Link href="/auth">
                <Button variant="outline">Sign In</Button>
              </Link>
              <Link href="/auth">
                <Button>Get Started</Button>
              </Link>
            </div>
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <section className="py-20 px-4">
        <div className="container mx-auto text-center max-w-4xl">
          <Badge variant="secondary" className="mb-4">Enterprise-Grade RAG Platform</Badge>
          <h2 className="text-5xl font-bold mb-6">
            AI-Powered Research Workbench for Academic Literature
          </h2>
          <p className="text-xl text-muted-foreground mb-8 max-w-2xl mx-auto">
            Upload your PDFs and chat with your literature using state-of-the-art
            retrieval and citation-grounded responses. Built for researchers and
            evidence synthesis teams.
          </p>
          <div className="flex gap-4 justify-center">
            <Link href="/auth">
              <Button size="lg" className="gap-2">
                Create Your RAG <ArrowRight className="h-4 w-4" />
              </Button>
            </Link>
            <Link href="/auth">
              <Button size="lg" variant="outline">
                View Demo
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section className="py-16 px-4 bg-muted/50">
        <div className="container mx-auto max-w-6xl">
          <h3 className="text-3xl font-bold text-center mb-12">How It Works</h3>
          <div className="grid md:grid-cols-3 gap-8">
            <Card>
              <CardHeader>
                <div className="h-12 w-12 rounded-lg bg-primary/10 flex items-center justify-center mb-4">
                  <Upload className="h-6 w-6 text-primary" />
                </div>
                <CardTitle>1. Upload Documents</CardTitle>
                <CardDescription>
                  Upload PDFs, research papers, reports, or any documents you want
                  to make searchable.
                </CardDescription>
              </CardHeader>
            </Card>

            <Card>
              <CardHeader>
                <div className="h-12 w-12 rounded-lg bg-primary/10 flex items-center justify-center mb-4">
                  <Database className="h-6 w-6 text-primary" />
                </div>
                <CardTitle>2. AI Processing</CardTitle>
                <CardDescription>
                  Documents are automatically parsed, chunked, and indexed for
                  intelligent retrieval.
                </CardDescription>
              </CardHeader>
            </Card>

            <Card>
              <CardHeader>
                <div className="h-12 w-12 rounded-lg bg-primary/10 flex items-center justify-center mb-4">
                  <MessageSquare className="h-6 w-6 text-primary" />
                </div>
                <CardTitle>3. Chat & Search</CardTitle>
                <CardDescription>
                  Ask questions in natural language and get AI-synthesized answers
                  with citations.
                </CardDescription>
              </CardHeader>
            </Card>
          </div>
        </div>
      </section>

      {/* Core Features */}
      <section className="py-16 px-4" id="features">
        <div className="container mx-auto max-w-6xl">
          <div className="text-center mb-12">
            <Badge variant="outline" className="mb-4">Core Features</Badge>
            <h3 className="text-3xl font-bold mb-4">Powerful Capabilities</h3>
            <p className="text-muted-foreground max-w-2xl mx-auto">
              Built with state-of-the-art AI technology for accurate, citation-grounded responses
            </p>
          </div>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {/* Smart Document Ingestion */}
            <Card className="relative overflow-hidden">
              <CardHeader>
                <div className="h-10 w-10 rounded-lg bg-blue-500/10 flex items-center justify-center mb-2">
                  <FileText className="h-5 w-5 text-blue-500" />
                </div>
                <CardTitle className="text-lg">Smart Document Ingestion</CardTitle>
              </CardHeader>
              <CardContent className="pt-0">
                <ul className="space-y-2 text-sm text-muted-foreground">
                  <li className="flex items-start gap-2">
                    <CheckCircle2 className="h-4 w-4 text-green-500 mt-0.5 shrink-0" />
                    <span>MinerU GPU parsing for tables, figures & equations</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <CheckCircle2 className="h-4 w-4 text-green-500 mt-0.5 shrink-0" />
                    <span>Page-aware chunking with 256-word segments</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <CheckCircle2 className="h-4 w-4 text-green-500 mt-0.5 shrink-0" />
                    <span>CrossRef/OpenAlex metadata enrichment</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <CheckCircle2 className="h-4 w-4 text-green-500 mt-0.5 shrink-0" />
                    <span>Zotero collection sync & bibliography matching</span>
                  </li>
                </ul>
              </CardContent>
            </Card>

            {/* Hybrid Search */}
            <Card className="relative overflow-hidden">
              <CardHeader>
                <div className="h-10 w-10 rounded-lg bg-purple-500/10 flex items-center justify-center mb-2">
                  <Search className="h-5 w-5 text-purple-500" />
                </div>
                <CardTitle className="text-lg">Hybrid Search</CardTitle>
              </CardHeader>
              <CardContent className="pt-0">
                <ul className="space-y-2 text-sm text-muted-foreground">
                  <li className="flex items-start gap-2">
                    <CheckCircle2 className="h-4 w-4 text-green-500 mt-0.5 shrink-0" />
                    <span>Dense vectors with Cohere embed-v4 (1536d)</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <CheckCircle2 className="h-4 w-4 text-green-500 mt-0.5 shrink-0" />
                    <span>Sparse BM25-style keyword matching</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <CheckCircle2 className="h-4 w-4 text-green-500 mt-0.5 shrink-0" />
                    <span>HyDE hypothetical document expansion</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <CheckCircle2 className="h-4 w-4 text-green-500 mt-0.5 shrink-0" />
                    <span>Cohere rerank-v3.5 precision filtering</span>
                  </li>
                </ul>
              </CardContent>
            </Card>

            {/* Grounded Synthesis */}
            <Card className="relative overflow-hidden">
              <CardHeader>
                <div className="h-10 w-10 rounded-lg bg-green-500/10 flex items-center justify-center mb-2">
                  <Link2 className="h-5 w-5 text-green-500" />
                </div>
                <CardTitle className="text-lg">Citation-Grounded Synthesis</CardTitle>
              </CardHeader>
              <CardContent className="pt-0">
                <ul className="space-y-2 text-sm text-muted-foreground">
                  <li className="flex items-start gap-2">
                    <CheckCircle2 className="h-4 w-4 text-green-500 mt-0.5 shrink-0" />
                    <span>ALCE-style Claim Ledger two-pass extraction</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <CheckCircle2 className="h-4 w-4 text-green-500 mt-0.5 shrink-0" />
                    <span>Inline citations [Author, Year, p.X]</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <CheckCircle2 className="h-4 w-4 text-green-500 mt-0.5 shrink-0" />
                    <span>Click-to-navigate PDF viewer integration</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <CheckCircle2 className="h-4 w-4 text-green-500 mt-0.5 shrink-0" />
                    <span>MiniCheck NLI post-hoc verification</span>
                  </li>
                </ul>
              </CardContent>
            </Card>

            {/* Study Classification */}
            <Card className="relative overflow-hidden">
              <CardHeader>
                <div className="h-10 w-10 rounded-lg bg-orange-500/10 flex items-center justify-center mb-2">
                  <BookOpen className="h-5 w-5 text-orange-500" />
                </div>
                <CardTitle className="text-lg">Study Design Classification</CardTitle>
              </CardHeader>
              <CardContent className="pt-0">
                <ul className="space-y-2 text-sm text-muted-foreground">
                  <li className="flex items-start gap-2">
                    <CheckCircle2 className="h-4 w-4 text-green-500 mt-0.5 shrink-0" />
                    <span>Auto-classify 22 study types (RCT, DiD, RDD, etc.)</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <CheckCircle2 className="h-4 w-4 text-green-500 mt-0.5 shrink-0" />
                    <span>Filter evidence by study design</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <CheckCircle2 className="h-4 w-4 text-green-500 mt-0.5 shrink-0" />
                    <span>Contextual retrieval prefixes (49% fewer failures)</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <CheckCircle2 className="h-4 w-4 text-green-500 mt-0.5 shrink-0" />
                    <span>Parent-child chunking for full context</span>
                  </li>
                </ul>
              </CardContent>
            </Card>

            {/* Multi-Model Support */}
            <Card className="relative overflow-hidden">
              <CardHeader>
                <div className="h-10 w-10 rounded-lg bg-pink-500/10 flex items-center justify-center mb-2">
                  <Zap className="h-5 w-5 text-pink-500" />
                </div>
                <CardTitle className="text-lg">Multi-Model Support</CardTitle>
              </CardHeader>
              <CardContent className="pt-0">
                <ul className="space-y-2 text-sm text-muted-foreground">
                  <li className="flex items-start gap-2">
                    <CheckCircle2 className="h-4 w-4 text-green-500 mt-0.5 shrink-0" />
                    <span>Per-RAG model selection (GPT-4o, Claude, Gemini)</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <CheckCircle2 className="h-4 w-4 text-green-500 mt-0.5 shrink-0" />
                    <span>Custom system prompts per project</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <CheckCircle2 className="h-4 w-4 text-green-500 mt-0.5 shrink-0" />
                    <span>Prompt versioning (up to 10 versions)</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <CheckCircle2 className="h-4 w-4 text-green-500 mt-0.5 shrink-0" />
                    <span>OpenRouter unified LLM access</span>
                  </li>
                </ul>
              </CardContent>
            </Card>

            {/* Admin & Observability */}
            <Card className="relative overflow-hidden">
              <CardHeader>
                <div className="h-10 w-10 rounded-lg bg-cyan-500/10 flex items-center justify-center mb-2">
                  <Settings className="h-5 w-5 text-cyan-500" />
                </div>
                <CardTitle className="text-lg">Admin & Observability</CardTitle>
              </CardHeader>
              <CardContent className="pt-0">
                <ul className="space-y-2 text-sm text-muted-foreground">
                  <li className="flex items-start gap-2">
                    <CheckCircle2 className="h-4 w-4 text-green-500 mt-0.5 shrink-0" />
                    <span>Full admin dashboard with usage stats</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <CheckCircle2 className="h-4 w-4 text-green-500 mt-0.5 shrink-0" />
                    <span>Cost tracking per model & project</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <CheckCircle2 className="h-4 w-4 text-green-500 mt-0.5 shrink-0" />
                    <span>Langfuse LLM tracing & debugging</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <CheckCircle2 className="h-4 w-4 text-green-500 mt-0.5 shrink-0" />
                    <span>Quality metrics & baseline experiments</span>
                  </li>
                </ul>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      {/* Quality Metrics */}
      <section className="py-16 px-4 bg-muted/50">
        <div className="container mx-auto max-w-4xl">
          <div className="text-center mb-12">
            <Badge variant="outline" className="mb-4">Quality Assurance</Badge>
            <h3 className="text-3xl font-bold mb-4">Rigorous Citation Quality</h3>
            <p className="text-muted-foreground">
              Evaluated using MiniCheck NLI verification on golden queries
            </p>
          </div>
          <div className="grid md:grid-cols-3 gap-6">
            <Card className="text-center">
              <CardHeader>
                <div className="flex items-center justify-center mb-2">
                  <Target className="h-8 w-8 text-primary" />
                </div>
                <CardTitle className="text-4xl font-bold text-primary">66.5%</CardTitle>
                <CardDescription className="text-base">Faithfulness</CardDescription>
              </CardHeader>
              <CardContent className="pt-0">
                <p className="text-sm text-muted-foreground">
                  Claims grounded in retrieved documents
                </p>
              </CardContent>
            </Card>
            <Card className="text-center">
              <CardHeader>
                <div className="flex items-center justify-center mb-2">
                  <BookOpen className="h-8 w-8 text-green-500" />
                </div>
                <CardTitle className="text-4xl font-bold text-green-500">98.9%</CardTitle>
                <CardDescription className="text-base">Citation Recall</CardDescription>
              </CardHeader>
              <CardContent className="pt-0">
                <p className="text-sm text-muted-foreground">
                  All claims properly cited
                </p>
              </CardContent>
            </Card>
            <Card className="text-center">
              <CardHeader>
                <div className="flex items-center justify-center mb-2">
                  <CheckCircle2 className="h-8 w-8 text-green-500" />
                </div>
                <CardTitle className="text-4xl font-bold text-green-500">98.9%</CardTitle>
                <CardDescription className="text-base">Citation Precision</CardDescription>
              </CardHeader>
              <CardContent className="pt-0">
                <p className="text-sm text-muted-foreground">
                  Citations point to correct sources
                </p>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      {/* Tech Stack */}
      <section className="py-16 px-4">
        <div className="container mx-auto max-w-4xl">
          <div className="text-center mb-12">
            <Badge variant="outline" className="mb-4">Technology</Badge>
            <h3 className="text-3xl font-bold mb-4">Enterprise-Grade Stack</h3>
          </div>
          <div className="grid md:grid-cols-2 gap-4">
            <div className="flex items-center gap-3 p-4 rounded-lg border bg-card">
              <BarChart3 className="h-5 w-5 text-muted-foreground" />
              <div>
                <p className="font-medium">Frontend</p>
                <p className="text-sm text-muted-foreground">Next.js 15, TypeScript, Tailwind CSS</p>
              </div>
            </div>
            <div className="flex items-center gap-3 p-4 rounded-lg border bg-card">
              <Database className="h-5 w-5 text-muted-foreground" />
              <div>
                <p className="font-medium">Backend</p>
                <p className="text-sm text-muted-foreground">FastAPI, Python 3.12, Pydantic v2</p>
              </div>
            </div>
            <div className="flex items-center gap-3 p-4 rounded-lg border bg-card">
              <Shield className="h-5 w-5 text-muted-foreground" />
              <div>
                <p className="font-medium">Auth & Database</p>
                <p className="text-sm text-muted-foreground">Supabase (JWT + RLS), PostgreSQL</p>
              </div>
            </div>
            <div className="flex items-center gap-3 p-4 rounded-lg border bg-card">
              <Search className="h-5 w-5 text-muted-foreground" />
              <div>
                <p className="font-medium">Vector Search</p>
                <p className="text-sm text-muted-foreground">Qdrant Cloud (dense + sparse vectors)</p>
              </div>
            </div>
            <div className="flex items-center gap-3 p-4 rounded-lg border bg-card">
              <Zap className="h-5 w-5 text-muted-foreground" />
              <div>
                <p className="font-medium">LLM & Embeddings</p>
                <p className="text-sm text-muted-foreground">OpenRouter, Cohere embed-v4 & rerank-v3.5</p>
              </div>
            </div>
            <div className="flex items-center gap-3 p-4 rounded-lg border bg-card">
              <FileText className="h-5 w-5 text-muted-foreground" />
              <div>
                <p className="font-medium">PDF Processing</p>
                <p className="text-sm text-muted-foreground">MinerU 2.6.8 on Modal (T4 GPU)</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Use Cases */}
      <section className="py-16 px-4">
        <div className="container mx-auto max-w-6xl">
          <h3 className="text-3xl font-bold text-center mb-12">Use Cases</h3>
          <div className="grid md:grid-cols-2 gap-8">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Users className="h-5 w-5" />
                  Research Teams
                </CardTitle>
                <CardDescription>
                  Upload literature reviews, papers, and data. Team members can
                  quickly find relevant information across all documents.
                </CardDescription>
              </CardHeader>
            </Card>
            
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Shield className="h-5 w-5" />
                  Knowledge Management
                </CardTitle>
                <CardDescription>
                  Create internal knowledge bases for policies, procedures, and
                  documentation that employees can query naturally.
                </CardDescription>
              </CardHeader>
            </Card>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-20 px-4 bg-primary text-primary-foreground">
        <div className="container mx-auto text-center max-w-2xl">
          <h3 className="text-3xl font-bold mb-4">
            Ready to Build Your Knowledge Base?
          </h3>
          <p className="text-lg mb-8 opacity-90">
            Sign up for free and create your first RAG in minutes.
          </p>
          <Link href="/auth">
            <Button size="lg" variant="secondary" className="gap-2">
              Get Started <ArrowRight className="h-4 w-4" />
            </Button>
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-8 px-4 border-t">
        <div className="container mx-auto text-center text-sm text-muted-foreground">
          <p>© 2026 RAG Platform. Powered by AI.</p>
        </div>
      </footer>
    </div>
  );
}
