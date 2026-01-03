"use client";

import { useEffect, useState, useCallback } from "react";
import { createClient } from "@/lib/supabase";
import type { RealtimeChannel } from "@supabase/supabase-js";

export interface ProcessingJob {
  id: string;
  rag_project_id: string;
  job_type: string;
  status: "pending" | "processing" | "running" | "completed" | "failed";
  progress: number;  // 0-100 percentage
  message: string | null;
  error_message: string | null;
  created_at: string;
  updated_at?: string;
  started_at?: string;
  completed_at?: string;
}

export interface DocumentStatus {
  id: string;
  filename: string;
  status: "pending" | "processing" | "completed" | "failed";
  chunk_count: number;
  error_message: string | null;
}

interface UseProcessingRealtimeOptions {
  ragId: string;
  onJobUpdate?: (job: ProcessingJob) => void;
  onDocumentUpdate?: (doc: DocumentStatus) => void;
  onProcessingComplete?: () => void;
}

/**
 * Hook for real-time processing status updates via Supabase Realtime.
 * Subscribes to processing_jobs and documents tables for live updates.
 */
export function useProcessingRealtime({
  ragId,
  onJobUpdate,
  onDocumentUpdate,
  onProcessingComplete,
}: UseProcessingRealtimeOptions) {
  const [activeJob, setActiveJob] = useState<ProcessingJob | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  // Callback when job status changes
  const handleJobChange = useCallback(
    (payload: { new: ProcessingJob; old?: ProcessingJob; eventType: string }) => {
      const job = payload.new;
      
      // Only care about jobs for this RAG project
      if (job.rag_project_id !== ragId) return;

      console.log("[Realtime] Job update:", job.status, `${job.progress}%`);
      
      setActiveJob(job);
      onJobUpdate?.(job);

      // Check if processing just completed
      if (
        payload.old?.status === "running" &&
        (job.status === "completed" || job.status === "failed")
      ) {
        onProcessingComplete?.();
      }
    },
    [ragId, onJobUpdate, onProcessingComplete]
  );

  // Callback when document status changes
  const handleDocumentChange = useCallback(
    (payload: { new: DocumentStatus }) => {
      const doc = payload.new;
      console.log("[Realtime] Document update:", doc.filename, doc.status);
      onDocumentUpdate?.(doc);
    },
    [onDocumentUpdate]
  );

  useEffect(() => {
    const supabase = createClient();
    if (!supabase) {
      setConnectionError("Supabase not configured");
      return;
    }

    let jobChannel: RealtimeChannel | null = null;
    let docChannel: RealtimeChannel | null = null;

    const setupSubscriptions = async () => {
      try {
        // Subscribe to processing_jobs table changes for this RAG
        jobChannel = supabase
          .channel(`processing-jobs-${ragId}`)
          .on(
            "postgres_changes",
            {
              event: "*", // INSERT, UPDATE, DELETE
              schema: "public",
              table: "processing_jobs",
              filter: `rag_project_id=eq.${ragId}`,
            },
            (payload) => {
              handleJobChange({
                new: payload.new as ProcessingJob,
                old: payload.old as ProcessingJob | undefined,
                eventType: payload.eventType,
              });
            }
          )
          .subscribe((status) => {
            console.log("[Realtime] Jobs channel status:", status);
            if (status === "SUBSCRIBED") {
              setIsConnected(true);
              setConnectionError(null);
            } else if (status === "CHANNEL_ERROR") {
              setConnectionError("Failed to connect to realtime");
            }
          });

        // Subscribe to documents table changes for this RAG
        docChannel = supabase
          .channel(`documents-${ragId}`)
          .on(
            "postgres_changes",
            {
              event: "UPDATE", // Only care about status updates
              schema: "public",
              table: "documents",
              filter: `rag_project_id=eq.${ragId}`,
            },
            (payload) => {
              handleDocumentChange({
                new: payload.new as DocumentStatus,
              });
            }
          )
          .subscribe((status) => {
            console.log("[Realtime] Documents channel status:", status);
          });

      } catch (err) {
        console.error("[Realtime] Subscription error:", err);
        setConnectionError(err instanceof Error ? err.message : "Connection failed");
      }
    };

    setupSubscriptions();

    // Cleanup on unmount
    return () => {
      console.log("[Realtime] Cleaning up subscriptions");
      if (jobChannel) {
        supabase.removeChannel(jobChannel);
      }
      if (docChannel) {
        supabase.removeChannel(docChannel);
      }
    };
  }, [ragId, handleJobChange, handleDocumentChange]);

  return {
    activeJob,
    isConnected,
    connectionError,
  };
}
