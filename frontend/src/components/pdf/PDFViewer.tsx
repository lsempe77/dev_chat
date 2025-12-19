"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { 
  Loader2, 
  AlertCircle, 
  X,
  Maximize2,
  Minimize2,
  ExternalLink
} from "lucide-react";

interface PDFViewerProps {
  url: string;
  initialPage?: number;
  highlightText?: string;
  onClose?: () => void;
  className?: string;
}

/**
 * PDF Viewer using browser's native PDF viewer via iframe.
 * This approach is compatible with Next.js Turbopack and all browsers.
 * 
 * The URL can include a page parameter: url#page=5
 */
export function PDFViewer({ 
  url, 
  initialPage = 1, 
  onClose,
  className = "",
}: PDFViewerProps) {
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  // Append page parameter to URL for initial page
  const pdfUrl = initialPage > 1 
    ? `${url}#page=${initialPage}` 
    : url;

  const handleLoad = () => {
    setIsLoading(false);
  };

  const handleError = () => {
    setError("Failed to load PDF. The file may be unavailable or your browser may not support PDF viewing.");
    setIsLoading(false);
  };

  const toggleFullscreen = () => {
    setIsFullscreen(!isFullscreen);
  };

  const openInNewTab = () => {
    window.open(pdfUrl, '_blank');
  };

  return (
    <div className={`relative flex flex-col bg-gray-100 rounded-lg overflow-hidden ${isFullscreen ? 'fixed inset-4 z-50 shadow-2xl' : className}`}>
      {/* Toolbar */}
      <div className="flex items-center justify-between px-3 py-2 bg-white border-b">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-gray-700">PDF Viewer</span>
          {initialPage > 1 && (
            <span className="text-xs text-gray-500">(Page {initialPage})</span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={openInNewTab}
            title="Open in new tab"
          >
            <ExternalLink className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={toggleFullscreen}
            title={isFullscreen ? "Exit fullscreen" : "Fullscreen"}
          >
            {isFullscreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
          </Button>
          {onClose && (
            <Button
              variant="ghost"
              size="sm"
              onClick={onClose}
              title="Close"
            >
              <X className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>

      {/* PDF Content */}
      <div className="flex-1 relative min-h-[500px]">
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-gray-50 z-10">
            <div className="flex flex-col items-center gap-2">
              <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
              <span className="text-sm text-gray-500">Loading PDF...</span>
            </div>
          </div>
        )}

        {error && (
          <div className="absolute inset-0 flex items-center justify-center bg-gray-50">
            <div className="flex flex-col items-center gap-3 text-red-600 max-w-md text-center p-4">
              <AlertCircle className="h-8 w-8" />
              <span className="text-sm">{error}</span>
              <Button variant="outline" size="sm" onClick={openInNewTab}>
                <ExternalLink className="h-4 w-4 mr-2" />
                Try opening in new tab
              </Button>
            </div>
          </div>
        )}

        <iframe
          src={pdfUrl}
          className="w-full h-full border-0"
          style={{ minHeight: '500px' }}
          onLoad={handleLoad}
          onError={handleError}
          title="PDF Document"
        />
      </div>
    </div>
  );
}

/**
 * Simple PDF viewer - same as PDFViewer but exported for compatibility
 */
export const SimplePDFViewer = PDFViewer;

export default PDFViewer;
