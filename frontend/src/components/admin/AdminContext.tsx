"use client";

import { createContext, useContext, useState, ReactNode } from "react";
import { DocumentMetadataDetail, MetadataUpdateRequest } from "@/lib/admin-api";

// ============================================================================
// Upload Tab State
// ============================================================================

export interface FileToUpload {
  file: File;
  status: "pending" | "uploading" | "completed" | "error" | "duplicate";
  progress: number;
  error?: string;
  r2Key?: string;
  isDuplicate?: boolean;
  message?: string;
}

export interface UploadState {
  files: FileToUpload[];
  isUploading: boolean;
}

// ============================================================================
// Processing Tab State
// ============================================================================

export interface ProcessingJob {
  id: string;
  filename: string;
  status: "queued" | "processing" | "completed" | "failed";
  progress: number;
  startedAt?: string;
  completedAt?: string;
  error?: string;
  pages?: number;
  chunks?: number;
}

export interface ProcessingState {
  jobs: ProcessingJob[];
  triggerMessage: string | null;
  lastTriggeredAt: Date | null;
  triggeredJobCount: number;
  queuedCount: number;
  processingCount: number;
  completedCount: number;
  failedCount: number;
}

// ============================================================================
// Documents Tab State
// ============================================================================

export interface Document {
  id: string;
  title: string;
  filename: string;
  authors: string[];
  year?: number;
  status: "indexed" | "pending" | "error";
  pageCount: number;
  chunkCount: number;
  uploadedAt: string;
  processedAt?: string;
}

export interface DocumentsState {
  documents: Document[];
  searchQuery: string;
  selectedDocs: Set<string>;
  totalChunks: number;
}

// ============================================================================
// Metadata Tab State
// ============================================================================

export interface MetadataStats {
  needsReview: number;
  lowConfidence: number;
  total: number;
}

export interface MetadataState {
  documents: DocumentMetadataDetail[];
  filterType: "all" | "needs_review" | "low_confidence";
  searchQuery: string;
  stats: MetadataStats;
  editingDoc: DocumentMetadataDetail | null;
  editForm: MetadataUpdateRequest;
  viewingPdfDoc: DocumentMetadataDetail | null;
  pdfUrl: string | null;
}

// ============================================================================
// Settings Tab State
// ============================================================================

export interface ConnectionStatus {
  name: string;
  status: "connected" | "disconnected" | "checking";
  details?: string;
}

export interface StorageStats {
  bucket: string;
  inputPath: string;
  outputPath: string;
  storageUsedBytes: number;
  fileCount: number;
}

export interface SettingsState {
  connections: ConnectionStatus[];
  storageStats: StorageStats;
}

// ============================================================================
// Admin Context
// ============================================================================

interface AdminContextType {
  // Upload
  uploadState: UploadState;
  setUploadState: React.Dispatch<React.SetStateAction<UploadState>>;
  
  // Processing
  processingState: ProcessingState;
  setProcessingState: React.Dispatch<React.SetStateAction<ProcessingState>>;
  
  // Documents
  documentsState: DocumentsState;
  setDocumentsState: React.Dispatch<React.SetStateAction<DocumentsState>>;
  
  // Metadata
  metadataState: MetadataState;
  setMetadataState: React.Dispatch<React.SetStateAction<MetadataState>>;
  
  // Settings
  settingsState: SettingsState;
  setSettingsState: React.Dispatch<React.SetStateAction<SettingsState>>;
}

const AdminContext = createContext<AdminContextType | null>(null);

export function useAdminContext() {
  const context = useContext(AdminContext);
  if (!context) {
    throw new Error("useAdminContext must be used within AdminProvider");
  }
  return context;
}

// ============================================================================
// Initial States
// ============================================================================

const initialUploadState: UploadState = {
  files: [],
  isUploading: false,
};

const initialProcessingState: ProcessingState = {
  jobs: [],
  triggerMessage: null,
  lastTriggeredAt: null,
  triggeredJobCount: 0,
  queuedCount: 0,
  processingCount: 0,
  completedCount: 0,
  failedCount: 0,
};

const initialDocumentsState: DocumentsState = {
  documents: [],
  searchQuery: "",
  selectedDocs: new Set(),
  totalChunks: 0,
};

const initialMetadataState: MetadataState = {
  documents: [],
  filterType: "needs_review",
  searchQuery: "",
  stats: { needsReview: 0, lowConfidence: 0, total: 0 },
  editingDoc: null,
  editForm: {},
  viewingPdfDoc: null,
  pdfUrl: null,
};

const initialSettingsState: SettingsState = {
  connections: [
    { name: "Cloudflare R2", status: "checking", details: "Checking..." },
    { name: "Qdrant Cloud", status: "checking", details: "Checking..." },
    { name: "Modal", status: "checking", details: "Checking..." },
    { name: "Cohere API", status: "checking", details: "Checking..." },
  ],
  storageStats: {
    bucket: "devchat-pdfs",
    inputPath: "/input-pdfs/",
    outputPath: "/outputs/",
    storageUsedBytes: 0,
    fileCount: 0,
  },
};

// ============================================================================
// Provider Component
// ============================================================================

export function AdminProvider({ children }: { children: ReactNode }) {
  const [uploadState, setUploadState] = useState<UploadState>(initialUploadState);
  const [processingState, setProcessingState] = useState<ProcessingState>(initialProcessingState);
  const [documentsState, setDocumentsState] = useState<DocumentsState>(initialDocumentsState);
  const [metadataState, setMetadataState] = useState<MetadataState>(initialMetadataState);
  const [settingsState, setSettingsState] = useState<SettingsState>(initialSettingsState);

  return (
    <AdminContext.Provider
      value={{
        uploadState,
        setUploadState,
        processingState,
        setProcessingState,
        documentsState,
        setDocumentsState,
        metadataState,
        setMetadataState,
        settingsState,
        setSettingsState,
      }}
    >
      {children}
    </AdminContext.Provider>
  );
}
