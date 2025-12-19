"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { 
  Loader2, 
  AlertCircle, 
  ExternalLink
} from "lucide-react";

interface PDFViewerProps {
  url: string;
  initialPage?: number;
  searchText?: string;  // Text to search and highlight in PDF
  onClose?: () => void;
  className?: string;
  /** Hide the toolbar for embedded use */
  hideToolbar?: boolean;
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
  searchText,
  onClose,
  className = "",
  hideToolbar = false,
}: PDFViewerProps) {
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Build URL with page and search parameters
  // Chrome/Edge PDF viewer supports: #page=X&search=text
  // Firefox uses: #page=X (search requires different approach)
  const buildPdfUrl = () => {
    const params: string[] = [];
    
    if (initialPage > 1) {
      params.push(`page=${initialPage}`);
    }
    
    // Add search text for highlighting (works in Chrome/Edge)
    if (searchText) {
      // Encode the search text and take first ~50 chars for better matching
      const trimmedSearch = searchText.slice(0, 50).trim();
      params.push(`search=${encodeURIComponent(trimmedSearch)}`);
    }
    
    return params.length > 0 ? `${url}#${params.join('&')}` : url;
  };
  
  const pdfUrl = buildPdfUrl();

  // Reset loading state when URL changes
  useEffect(() => {
    setIsLoading(true);
    setError(null);
  }, [pdfUrl]);

  const handleLoad = () => {
    setIsLoading(false);
  };

  const handleError = () => {
    setError("Failed to load PDF");
    setIsLoading(false);
  };

  const openInNewTab = () => {
    window.open(pdfUrl, '_blank');
  };

  return (
    <div className={`relative flex flex-col h-full w-full ${className}`}>
      {/* PDF Content - full size */}
      <div className="flex-1 relative">
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
                Open in new tab
              </Button>
            </div>
          </div>
        )}

        <iframe
          key={pdfUrl}
          src={pdfUrl}
          className="w-full h-full border-0 absolute inset-0"
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
