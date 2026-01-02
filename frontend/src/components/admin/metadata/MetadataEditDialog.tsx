"use client";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Check, Loader2, GripHorizontal } from "lucide-react";
import { useState, useEffect, useRef, useCallback } from "react";
import type { DocumentMetadataDetail, MetadataUpdateRequest } from "@/lib/admin-api";
import {
  ITEM_TYPES,
  THESIS_TYPES,
  REPORT_TYPES,
  STUDY_TYPES,
  SECTORS,
  FIELDS_BY_ITEM_TYPE,
} from "./constants";

interface MetadataEditDialogProps {
  document: DocumentMetadataDetail | null;
  editForm: MetadataUpdateRequest;
  setEditForm: (form: MetadataUpdateRequest) => void;
  onClose: () => void;
  onSave: () => void;
  isSaving: boolean;
}

export function MetadataEditDialog({
  document,
  editForm,
  setEditForm,
  onClose,
  onSave,
  isSaving,
}: MetadataEditDialogProps) {
  // Local state for authors string (allows spaces while typing)
  const [authorsText, setAuthorsText] = useState("");
  
  // Draggable dialog state
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const dragRef = useRef<{ startX: number; startY: number; initialX: number; initialY: number } | null>(null);
  
  // Reset position when dialog opens
  useEffect(() => {
    if (document) {
      setPosition({ x: 0, y: 0 });
    }
  }, [document?.id]);
  
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsDragging(true);
    dragRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      initialX: position.x,
      initialY: position.y,
    };
  }, [position]);
  
  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!isDragging || !dragRef.current) return;
    
    const deltaX = e.clientX - dragRef.current.startX;
    const deltaY = e.clientY - dragRef.current.startY;
    
    setPosition({
      x: dragRef.current.initialX + deltaX,
      y: dragRef.current.initialY + deltaY,
    });
  }, [isDragging]);
  
  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
    dragRef.current = null;
  }, []);
  
  // Add/remove event listeners for drag
  useEffect(() => {
    if (isDragging) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
    }
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging, handleMouseMove, handleMouseUp]);
  
  // Sync authorsText when document changes
  useEffect(() => {
    if (document) {
      setAuthorsText(editForm.authors?.join("; ") || "");
    }
  }, [document?.id]);
  
  // Update editForm.authors when authorsText changes (on blur)
  const syncAuthorsToForm = () => {
    const authors = authorsText
      .split(";")
      .map(a => a.trim())
      .filter(Boolean);
    setEditForm({ ...editForm, authors });
  };
  
  if (!document) return null;

  const itemType = editForm.item_type || "";
  const fieldsForType = FIELDS_BY_ITEM_TYPE[itemType] || [];

  // Helper to check if a field should be shown
  const showField = (field: string) => fieldsForType.includes(field);

  // Get section title based on item type
  const getSectionTitle = () => {
    switch (itemType) {
      case "journalArticle": return "Journal Information";
      case "book": return "Book Information";
      case "bookSection": return "Book Section Information";
      case "report": return "Report Information";
      case "workingPaper": return "Working Paper Information";
      case "thesis": return "Thesis Information";
      case "conferencePaper": return "Conference Paper Information";
      case "webpage": return "Web Page Information";
      case "dataset": return "Dataset Information";
      case "preprint": return "Preprint Information";
      default: return "Publication Information";
    }
  };

  return (
    <Dialog open={!!document} onOpenChange={(open) => !open && onClose()}>
      <DialogContent 
        className="sm:max-w-4xl max-h-[90vh] overflow-y-auto !translate-x-0 !translate-y-0"
        style={{ 
          left: `calc(50% + ${position.x}px)`,
          top: `calc(50% + ${position.y}px)`,
          transform: 'translate(-50%, -50%)',
        }}
      >
        {/* Drag handle */}
        <div 
          className="absolute top-0 left-0 right-0 h-10 cursor-move flex items-center justify-center"
          onMouseDown={handleMouseDown}
        >
          <GripHorizontal className="h-4 w-4 text-muted-foreground" />
        </div>
        
        <DialogHeader className="pt-4">
          <DialogTitle>Edit Document Metadata</DialogTitle>
          <DialogDescription>
            Update metadata fields for: {document.filename}
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          {/* === ITEM TYPE (always shown first) === */}
          <div className="grid grid-cols-4 items-center gap-4">
            <Label className="text-right font-semibold">Item Type</Label>
            <Select
              value={itemType}
              onValueChange={(value) => setEditForm({ ...editForm, item_type: value })}
            >
              <SelectTrigger className="col-span-3">
                <SelectValue placeholder="Select item type (Zotero-style)" />
              </SelectTrigger>
              <SelectContent>
                {ITEM_TYPES.map((type) => (
                  <SelectItem key={type} value={type}>
                    {type}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* === CORE FIELDS (always shown) === */}
          <div className="border-t pt-4 mt-2">
            <p className="text-sm font-medium text-muted-foreground mb-3">Core Information</p>
          </div>

          <div className="grid grid-cols-4 items-center gap-4">
            <Label className="text-right">Title</Label>
            <Input
              className="col-span-3"
              value={editForm.title || ""}
              onChange={(e) => setEditForm({ ...editForm, title: e.target.value })}
            />
          </div>

          <div className="grid grid-cols-4 items-center gap-4">
            <Label className="text-right">Authors</Label>
            <div className="col-span-3">
              <Input
                value={authorsText}
                onChange={(e) => setAuthorsText(e.target.value)}
                onBlur={syncAuthorsToForm}
                placeholder="Surname, Name; Surname, Name"
              />
              <p className="text-xs text-muted-foreground mt-1">
                Separate authors with semicolon (;). Format: Surname, Name
              </p>
            </div>
          </div>

          <div className="grid grid-cols-4 items-center gap-4">
            <Label className="text-right">Year</Label>
            <Input
              className="col-span-3"
              type="number"
              value={editForm.year || ""}
              onChange={(e) => setEditForm({ ...editForm, year: parseInt(e.target.value) || undefined })}
            />
          </div>

          {/* === DYNAMIC FIELDS BASED ON ITEM TYPE === */}
          {itemType && fieldsForType.length > 0 && (
            <>
              <div className="border-t pt-4 mt-2">
                <p className="text-sm font-medium text-muted-foreground mb-3">
                  {getSectionTitle()}
                </p>
              </div>

              {/* Publication/Journal */}
              {showField("publication") && (
                <div className="grid grid-cols-4 items-center gap-4">
                  <Label className="text-right">Publication</Label>
                  <Input
                    className="col-span-3"
                    value={editForm.publication || editForm.journal || ""}
                    onChange={(e) => setEditForm({ ...editForm, publication: e.target.value, journal: e.target.value })}
                    placeholder="Journal or magazine name"
                  />
                </div>
              )}

              {/* Volume */}
              {showField("volume") && (
                <div className="grid grid-cols-4 items-center gap-4">
                  <Label className="text-right">Volume</Label>
                  <Input
                    className="col-span-3"
                    value={editForm.volume || ""}
                    onChange={(e) => setEditForm({ ...editForm, volume: e.target.value })}
                    placeholder="e.g., 12"
                  />
                </div>
              )}

              {/* Issue */}
              {showField("issue") && (
                <div className="grid grid-cols-4 items-center gap-4">
                  <Label className="text-right">Issue</Label>
                  <Input
                    className="col-span-3"
                    value={editForm.issue || ""}
                    onChange={(e) => setEditForm({ ...editForm, issue: e.target.value })}
                    placeholder="e.g., 3"
                  />
                </div>
              )}

              {/* Pages */}
              {showField("pages") && (
                <div className="grid grid-cols-4 items-center gap-4">
                  <Label className="text-right">Pages</Label>
                  <Input
                    className="col-span-3"
                    value={editForm.pages || ""}
                    onChange={(e) => setEditForm({ ...editForm, pages: e.target.value })}
                    placeholder="e.g., 123-145"
                  />
                </div>
              )}

              {/* DOI */}
              {showField("doi") && (
                <div className="grid grid-cols-4 items-center gap-4">
                  <Label className="text-right">DOI</Label>
                  <Input
                    className="col-span-3"
                    value={editForm.doi || ""}
                    onChange={(e) => setEditForm({ ...editForm, doi: e.target.value })}
                    placeholder="10.xxxx/yyyy"
                  />
                </div>
              )}

              {/* ISSN */}
              {showField("issn") && (
                <div className="grid grid-cols-4 items-center gap-4">
                  <Label className="text-right">ISSN</Label>
                  <Input
                    className="col-span-3"
                    value={editForm.issn || ""}
                    onChange={(e) => setEditForm({ ...editForm, issn: e.target.value })}
                    placeholder="e.g., 1234-5678"
                  />
                </div>
              )}

              {/* ISBN */}
              {showField("isbn") && (
                <div className="grid grid-cols-4 items-center gap-4">
                  <Label className="text-right">ISBN</Label>
                  <Input
                    className="col-span-3"
                    value={editForm.isbn || ""}
                    onChange={(e) => setEditForm({ ...editForm, isbn: e.target.value })}
                    placeholder="e.g., 978-3-16-148410-0"
                  />
                </div>
              )}

              {/* Publisher */}
              {showField("publisher") && (
                <div className="grid grid-cols-4 items-center gap-4">
                  <Label className="text-right">Publisher</Label>
                  <Input
                    className="col-span-3"
                    value={editForm.publisher || ""}
                    onChange={(e) => setEditForm({ ...editForm, publisher: e.target.value })}
                    placeholder="Publisher name"
                  />
                </div>
              )}

              {/* Place */}
              {showField("place") && (
                <div className="grid grid-cols-4 items-center gap-4">
                  <Label className="text-right">Place</Label>
                  <Input
                    className="col-span-3"
                    value={editForm.place || ""}
                    onChange={(e) => setEditForm({ ...editForm, place: e.target.value })}
                    placeholder="Publication place (e.g., Washington, DC)"
                  />
                </div>
              )}

              {/* Edition */}
              {showField("edition") && (
                <div className="grid grid-cols-4 items-center gap-4">
                  <Label className="text-right">Edition</Label>
                  <Input
                    className="col-span-3"
                    value={editForm.edition || ""}
                    onChange={(e) => setEditForm({ ...editForm, edition: e.target.value })}
                    placeholder="e.g., 2 (for 2nd edition)"
                  />
                </div>
              )}

              {/* Series */}
              {showField("series") && (
                <div className="grid grid-cols-4 items-center gap-4">
                  <Label className="text-right">Series</Label>
                  <Input
                    className="col-span-3"
                    value={editForm.series || ""}
                    onChange={(e) => setEditForm({ ...editForm, series: e.target.value })}
                    placeholder="Series title"
                  />
                </div>
              )}

              {/* Series Number */}
              {showField("series_number") && (
                <div className="grid grid-cols-4 items-center gap-4">
                  <Label className="text-right">Series Number</Label>
                  <Input
                    className="col-span-3"
                    value={editForm.series_number || ""}
                    onChange={(e) => setEditForm({ ...editForm, series_number: e.target.value })}
                    placeholder="Number in series"
                  />
                </div>
              )}

              {/* # of Pages */}
              {showField("num_pages") && (
                <div className="grid grid-cols-4 items-center gap-4">
                  <Label className="text-right"># of Pages</Label>
                  <Input
                    className="col-span-3"
                    type="number"
                    value={editForm.num_pages || ""}
                    onChange={(e) => setEditForm({ ...editForm, num_pages: e.target.value || undefined })}
                    placeholder="Total pages"
                  />
                </div>
              )}

              {/* Book Title (for book sections) */}
              {showField("book_title") && (
                <div className="grid grid-cols-4 items-center gap-4">
                  <Label className="text-right">Book Title</Label>
                  <Input
                    className="col-span-3"
                    value={editForm.book_title || ""}
                    onChange={(e) => setEditForm({ ...editForm, book_title: e.target.value })}
                    placeholder="Title of the book containing this chapter"
                  />
                </div>
              )}

              {/* Institution (for reports/theses) */}
              {showField("institution") && (
                <div className="grid grid-cols-4 items-center gap-4">
                  <Label className="text-right">
                    {itemType === "thesis" ? "University" : "Institution"}
                  </Label>
                  <Input
                    className="col-span-3"
                    value={editForm.institution || ""}
                    onChange={(e) => setEditForm({ ...editForm, institution: e.target.value })}
                    placeholder={itemType === "thesis" ? "University name" : "Institution name"}
                  />
                </div>
              )}

              {/* Report Number */}
              {showField("report_number") && (
                <div className="grid grid-cols-4 items-center gap-4">
                  <Label className="text-right">Report Number</Label>
                  <Input
                    className="col-span-3"
                    value={editForm.report_number || ""}
                    onChange={(e) => setEditForm({ ...editForm, report_number: e.target.value })}
                    placeholder="e.g., WPS-2024-001"
                  />
                </div>
              )}

              {/* Report Type */}
              {showField("report_type") && (
                <div className="grid grid-cols-4 items-center gap-4">
                  <Label className="text-right">Report Type</Label>
                  <Select
                    value={editForm.report_type || ""}
                    onValueChange={(value) => setEditForm({ ...editForm, report_type: value })}
                  >
                    <SelectTrigger className="col-span-3">
                      <SelectValue placeholder="Select report type" />
                    </SelectTrigger>
                    <SelectContent>
                      {REPORT_TYPES.map((type) => (
                        <SelectItem key={type} value={type}>
                          {type}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}

              {/* Thesis Type */}
              {showField("thesis_type") && (
                <div className="grid grid-cols-4 items-center gap-4">
                  <Label className="text-right">Thesis Type</Label>
                  <Select
                    value={editForm.thesis_type || ""}
                    onValueChange={(value) => setEditForm({ ...editForm, thesis_type: value })}
                  >
                    <SelectTrigger className="col-span-3">
                      <SelectValue placeholder="Select thesis type" />
                    </SelectTrigger>
                    <SelectContent>
                      {THESIS_TYPES.map((type) => (
                        <SelectItem key={type} value={type}>
                          {type}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}

              {/* Conference Name */}
              {showField("conference_name") && (
                <div className="grid grid-cols-4 items-center gap-4">
                  <Label className="text-right">Conference Name</Label>
                  <Input
                    className="col-span-3"
                    value={editForm.conference_name || ""}
                    onChange={(e) => setEditForm({ ...editForm, conference_name: e.target.value })}
                    placeholder="Name of the conference"
                  />
                </div>
              )}

              {/* Proceedings Title */}
              {showField("proceedings_title") && (
                <div className="grid grid-cols-4 items-center gap-4">
                  <Label className="text-right">Proceedings Title</Label>
                  <Input
                    className="col-span-3"
                    value={editForm.proceedings_title || ""}
                    onChange={(e) => setEditForm({ ...editForm, proceedings_title: e.target.value })}
                    placeholder="Title of conference proceedings"
                  />
                </div>
              )}

              {/* URL */}
              {showField("url") && (
                <div className="grid grid-cols-4 items-center gap-4">
                  <Label className="text-right">URL</Label>
                  <Input
                    className="col-span-3"
                    value={editForm.url || ""}
                    onChange={(e) => setEditForm({ ...editForm, url: e.target.value })}
                    placeholder="https://..."
                  />
                </div>
              )}

              {/* Accessed Date */}
              {showField("accessed_date") && (
                <div className="grid grid-cols-4 items-center gap-4">
                  <Label className="text-right">Accessed</Label>
                  <Input
                    className="col-span-3"
                    value={editForm.accessed_date || ""}
                    onChange={(e) => setEditForm({ ...editForm, accessed_date: e.target.value })}
                    placeholder="YYYY-MM-DD"
                  />
                </div>
              )}
            </>
          )}

          {/* === 3ie CLASSIFICATION (always shown) === */}
          <div className="border-t pt-4 mt-2">
            <p className="text-sm font-medium text-muted-foreground mb-3">3ie Classification</p>
          </div>

          <div className="grid grid-cols-4 items-center gap-4">
            <Label className="text-right">Countries</Label>
            <Input
              className="col-span-3"
              value={editForm.countries?.join(", ") || ""}
              onChange={(e) => setEditForm({ 
                ...editForm, 
                countries: e.target.value.split(",").map(c => c.trim()).filter(Boolean) 
              })}
              placeholder="Comma-separated countries"
            />
          </div>

          <div className="grid grid-cols-4 items-center gap-4">
            <Label className="text-right">Sectors</Label>
            <div className="col-span-3 flex flex-wrap gap-2">
              {SECTORS.map((sector) => (
                <Badge
                  key={sector}
                  variant={editForm.sectors?.includes(sector) ? "default" : "outline"}
                  className="cursor-pointer"
                  onClick={() => {
                    const current = editForm.sectors || [];
                    if (current.includes(sector)) {
                      setEditForm({ ...editForm, sectors: current.filter(s => s !== sector) });
                    } else {
                      setEditForm({ ...editForm, sectors: [...current, sector] });
                    }
                  }}
                >
                  {sector}
                </Badge>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-4 items-center gap-4">
            <Label className="text-right">Study Type</Label>
            <Select
              value={editForm.study_type || ""}
              onValueChange={(value) => setEditForm({ ...editForm, study_type: value })}
            >
              <SelectTrigger className="col-span-3">
                <SelectValue placeholder="Select study type" />
              </SelectTrigger>
              <SelectContent>
                {STUDY_TYPES.map((type) => (
                  <SelectItem key={type} value={type}>
                    {type}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-4 items-center gap-4">
            <Label className="text-right">Intervention</Label>
            <Input
              className="col-span-3"
              value={editForm.intervention_type || ""}
              onChange={(e) => setEditForm({ ...editForm, intervention_type: e.target.value })}
              placeholder="e.g., cash transfer, training program"
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={onSave} disabled={isSaving}>
            {isSaving ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <Check className="h-4 w-4 mr-2" />
                Save Changes
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
