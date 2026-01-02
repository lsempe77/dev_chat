"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Loader2, Lock, LogOut } from "lucide-react";
import { 
  adminLogin, 
  adminLogout, 
  checkAuthStatus,
  getSessionToken,
} from "@/lib/admin-api";

interface AdminAuthGuardProps {
  children: React.ReactNode;
}

export function AdminAuthGuard({ children }: AdminAuthGuardProps) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [authRequired, setAuthRequired] = useState(true);
  const [isLoading, setIsLoading] = useState(true);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoggingIn, setIsLoggingIn] = useState(false);

  // Check auth status on mount
  useEffect(() => {
    const checkAuth = async () => {
      try {
        const status = await checkAuthStatus();
        setIsAuthenticated(status.authenticated);
        setAuthRequired(status.auth_required);
      } catch {
        // If check fails and we have a token, try it anyway
        setIsAuthenticated(!!getSessionToken());
      } finally {
        setIsLoading(false);
      }
    };

    checkAuth();
  }, []);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoggingIn(true);

    try {
      const response = await adminLogin(password);
      if (response.success) {
        setIsAuthenticated(true);
        setPassword("");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setIsLoggingIn(false);
    }
  };

  const handleLogout = async () => {
    await adminLogout();
    setIsAuthenticated(false);
  };

  // Loading state
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          <span>Checking authentication...</span>
        </div>
      </div>
    );
  }

  // If no auth required (dev mode), show content directly
  if (!authRequired) {
    return <>{children}</>;
  }

  // Not authenticated - show login form
  if (!isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background p-4">
        <Card className="w-full max-w-md">
          <CardHeader className="text-center">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
              <Lock className="h-6 w-6 text-primary" />
            </div>
            <CardTitle className="text-2xl">Admin Login</CardTitle>
            <CardDescription>
              Enter your admin password to access document management.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleLogin} className="space-y-4">
              {error && (
                <Alert variant="destructive">
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}
              
              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  type="password"
                  placeholder="Enter admin password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={isLoggingIn}
                  autoFocus
                />
              </div>

              <Button 
                type="submit" 
                className="w-full" 
                disabled={isLoggingIn || !password}
              >
                {isLoggingIn ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Logging in...
                  </>
                ) : (
                  "Log In"
                )}
              </Button>
            </form>

            <p className="mt-4 text-center text-xs text-muted-foreground">
              Contact your administrator if you need access.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Authenticated - show content with logout option
  return (
    <div className="relative">
      {/* Logout button in header area */}
      <div className="fixed top-4 right-4 z-50">
        <Button
          variant="outline"
          size="sm"
          onClick={handleLogout}
          className="gap-2"
        >
          <LogOut className="h-4 w-4" />
          Logout
        </Button>
      </div>
      {children}
    </div>
  );
}
