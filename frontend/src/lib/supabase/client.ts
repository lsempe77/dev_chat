import { createBrowserClient } from "@supabase/ssr";

// These are safe to expose - they're public keys
const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL || "";
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "";

/**
 * Create a Supabase client for browser use.
 * 
 * Uses @supabase/ssr for proper cookie handling in Next.js.
 */
export function createClient() {
  if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
    console.warn("Supabase not configured - multi-tenant features disabled");
    return null;
  }
  
  return createBrowserClient(SUPABASE_URL, SUPABASE_ANON_KEY);
}

/**
 * Check if Supabase is configured
 */
export function isSupabaseConfigured(): boolean {
  return Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);
}
