"use client";

import { useState, useEffect } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { 
  ArrowLeft,
  BarChart3,
  Users,
  Loader2,
  Shield,
} from "lucide-react";
import Link from "next/link";
import { OverviewTab } from "./OverviewTab";
import { UsersTab } from "./UsersTab";
import { checkHealth } from "@/lib/admin-api";

function AdminLayoutInner() {
  const [activeTab, setActiveTab] = useState("overview");
  const [connectionStatus, setConnectionStatus] = useState<{
    backend: boolean;
    loading: boolean;
  }>({ backend: false, loading: true });

  // Check connections on mount
  useEffect(() => {
    const checkConnections = async () => {
      try {
        const healthResult = await checkHealth();
        setConnectionStatus({
          backend: !!healthResult,
          loading: false,
        });
      } catch {
        setConnectionStatus({ backend: false, loading: false });
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
                  Back to App
                </Button>
              </Link>
              <div className="h-6 w-px bg-border" />
              <div className="flex items-center gap-2">
                <Shield className="h-5 w-5 text-primary" />
                <h1 className="text-xl font-semibold">3ie Admin</h1>
              </div>
            </div>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              {connectionStatus.loading ? (
                <span className="flex items-center gap-1">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  Checking...
                </span>
              ) : (
                <span className="flex items-center gap-1">
                  <span className={`h-2 w-2 rounded-full ${connectionStatus.backend ? "bg-green-500" : "bg-red-500"}`} />
                  Backend {connectionStatus.backend ? "Online" : "Offline"}
                </span>
              )}
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-4 py-6">
        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
          <TabsList className="grid w-full max-w-md grid-cols-2">
            <TabsTrigger value="overview" className="gap-2">
              <BarChart3 className="h-4 w-4" />
              Overview
            </TabsTrigger>
            <TabsTrigger value="users" className="gap-2">
              <Users className="h-4 w-4" />
              Users & RAGs
            </TabsTrigger>
          </TabsList>

          <TabsContent value="overview" className="space-y-4">
            <OverviewTab />
          </TabsContent>

          <TabsContent value="users" className="space-y-4">
            <UsersTab />
          </TabsContent>
        </Tabs>
      </main>
    </div>
  );
}

export function AdminLayout() {
  return <AdminLayoutInner />;
}
