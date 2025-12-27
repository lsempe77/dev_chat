"use client";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Check, Loader2, X, Eye } from "lucide-react";
import { useState, useEffect } from "react";
import type { DocumentMetadataDetail, MetadataUpdateRequest } from "@/lib/admin-api";
import {
  ITEM_TYPES,
  THESIS_TYPES,
  REPORT_TYPES,
  STUDY_TYPES,
  SECTORS,
  FIELDS_BY_ITEM_TYPE,
} from "./constants";

interface MetadataEditPanelProps {
  document: DocumentMetadataDetail | null;
  editForm: MetadataUpdateRequest;
  setEditForm: (form: MetadataUpdateRequest) => void;
  onClose: () => void;
  onSave: () => void;
  onViewPdf: () => void;
  isSaving: boolean;
  isPdfOpen: boolean;
}

export function MetadataEditPanel({
  document,
  editForm,
  setEditForm,
  onClose,
  onSave,
  onViewPdf,
  isSaving,
  isPdfOpen,
}: MetadataEditPanelProps) {
  // Local state for authors string (allows spaces while typing)
  const [authorsText, setAuthorsText] = useState("");
  
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

  return (
    <div className="flex flex-col h-full border rounded-lg overflow-hidden bg-background">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b bg-muted/30">
        <div className="flex items-center gap-2">
          <h3 className="font-semibold text-sm">Edit Metadata</h3>
          <Badge variant="outline" className="text-xs">{document.filename}</Badge>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={onViewPdf}
            disabled={isPdfOpen}
          >
            <Eye className="h-4 w-4 mr-1" />
            {isPdfOpen ? "PDF Open" : "View PDF"}
          </Button>
          <Button 
            variant="ghost" 
            size="sm"
            onClick={onClose}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>
      
      {/* Scrollable Form */}
      <ScrollArea className="flex-1">
        <div className="p-4 space-y-4">
          {/* === ITEM TYPE (always shown first) === */}
          <div className="space-y-2">
            <Label className="text-xs font-semibold text-muted-foreground uppercase">Item Type</Label>
            <Select
              value={itemType}
              onValueChange={(value) => setEditForm({ ...editForm, item_type: value })}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select item type" />
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

          {/* === CORE FIELDS === */}
          <div className="space-y-3 pt-2 border-t">
            <Label className="text-xs font-semibold text-muted-foreground uppercase">Core Information</Label>
            
            <div className="space-y-1">
              <Label className="text-xs">Title</Label>
              <Input
                value={editForm.title || ""}
                onChange={(e) => setEditForm({ ...editForm, title: e.target.value })}
              />
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Authors (semicolon-separated)</Label>
              <Input
                value={authorsText}
                onChange={(e) => setAuthorsText(e.target.value)}
                onBlur={syncAuthorsToForm}
                placeholder="Author One; Author Two; Author Three"
              />
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1">
                <Label className="text-xs">Year</Label>
                <Input
                  type="number"
                  value={editForm.year || ""}
                  onChange={(e) => setEditForm({ ...editForm, year: parseInt(e.target.value) || undefined })}
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">DOI</Label>
                <Input
                  value={editForm.doi || ""}
                  onChange={(e) => setEditForm({ ...editForm, doi: e.target.value })}
                  placeholder="10.1000/example"
                />
              </div>
            </div>
          </div>

          {/* === PUBLICATION INFO (conditional) === */}
          {(showField("journal") || showField("publication") || showField("volume")) && (
            <div className="space-y-3 pt-2 border-t">
              <Label className="text-xs font-semibold text-muted-foreground uppercase">Publication Info</Label>
              
              {showField("journal") && (
                <div className="space-y-1">
                  <Label className="text-xs">Journal</Label>
                  <Input
                    value={editForm.journal || editForm.publication || ""}
                    onChange={(e) => setEditForm({ ...editForm, journal: e.target.value, publication: e.target.value })}
                  />
                </div>
              )}
              
              {showField("publication") && !showField("journal") && (
                <div className="space-y-1">
                  <Label className="text-xs">Publication</Label>
                  <Input
                    value={editForm.publication || ""}
                    onChange={(e) => setEditForm({ ...editForm, publication: e.target.value })}
                  />
                </div>
              )}
              
              <div className="grid grid-cols-3 gap-2">
                {showField("volume") && (
                  <div className="space-y-1">
                    <Label className="text-xs">Volume</Label>
                    <Input
                      value={editForm.volume || ""}
                      onChange={(e) => setEditForm({ ...editForm, volume: e.target.value })}
                    />
                  </div>
                )}
                {showField("issue") && (
                  <div className="space-y-1">
                    <Label className="text-xs">Issue</Label>
                    <Input
                      value={editForm.issue || ""}
                      onChange={(e) => setEditForm({ ...editForm, issue: e.target.value })}
                    />
                  </div>
                )}
                {showField("pages") && (
                  <div className="space-y-1">
                    <Label className="text-xs">Pages</Label>
                    <Input
                      value={editForm.pages || ""}
                      onChange={(e) => setEditForm({ ...editForm, pages: e.target.value })}
                      placeholder="1-25"
                    />
                  </div>
                )}
              </div>
            </div>
          )}

          {/* === PUBLISHER INFO === */}
          {(showField("publisher") || showField("place")) && (
            <div className="space-y-3 pt-2 border-t">
              <Label className="text-xs font-semibold text-muted-foreground uppercase">Publisher</Label>
              <div className="grid grid-cols-2 gap-2">
                {showField("publisher") && (
                  <div className="space-y-1">
                    <Label className="text-xs">Publisher</Label>
                    <Input
                      value={editForm.publisher || ""}
                      onChange={(e) => setEditForm({ ...editForm, publisher: e.target.value })}
                    />
                  </div>
                )}
                {showField("place") && (
                  <div className="space-y-1">
                    <Label className="text-xs">Place</Label>
                    <Input
                      value={editForm.place || ""}
                      onChange={(e) => setEditForm({ ...editForm, place: e.target.value })}
                    />
                  </div>
                )}
              </div>
            </div>
          )}

          {/* === INSTITUTION (Reports/Thesis) === */}
          {showField("institution") && (
            <div className="space-y-3 pt-2 border-t">
              <Label className="text-xs font-semibold text-muted-foreground uppercase">Institution</Label>
              <div className="space-y-1">
                <Label className="text-xs">Institution</Label>
                <Input
                  value={editForm.institution || ""}
                  onChange={(e) => setEditForm({ ...editForm, institution: e.target.value })}
                />
              </div>
              
              {showField("report_type") && (
                <div className="space-y-1">
                  <Label className="text-xs">Report Type</Label>
                  <Select
                    value={editForm.report_type || ""}
                    onValueChange={(value) => setEditForm({ ...editForm, report_type: value })}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select type" />
                    </SelectTrigger>
                    <SelectContent>
                      {REPORT_TYPES.map((type) => (
                        <SelectItem key={type} value={type}>{type}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}
              
              {showField("thesis_type") && (
                <div className="space-y-1">
                  <Label className="text-xs">Thesis Type</Label>
                  <Select
                    value={editForm.thesis_type || ""}
                    onValueChange={(value) => setEditForm({ ...editForm, thesis_type: value })}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select type" />
                    </SelectTrigger>
                    <SelectContent>
                      {THESIS_TYPES.map((type) => (
                        <SelectItem key={type} value={type}>{type}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}
            </div>
          )}

          {/* === CLASSIFICATION (Always shown) === */}
          <div className="space-y-3 pt-2 border-t">
            <Label className="text-xs font-semibold text-muted-foreground uppercase">Classification</Label>
            
            <div className="space-y-1">
              <Label className="text-xs">Countries (comma-separated)</Label>
              <Input
                value={editForm.countries?.join(", ") || ""}
                onChange={(e) => setEditForm({ 
                  ...editForm, 
                  countries: e.target.value.split(",").map(c => c.trim()).filter(Boolean) 
                })}
                placeholder="Kenya, Uganda, Tanzania"
              />
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Sectors</Label>
              <Select
                value={editForm.sectors?.[0] || ""}
                onValueChange={(value) => setEditForm({ ...editForm, sectors: [value] })}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select sector" />
                </SelectTrigger>
                <SelectContent>
                  {SECTORS.map((sector) => (
                    <SelectItem key={sector} value={sector}>{sector}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Study Type</Label>
              <Select
                value={editForm.study_type || ""}
                onValueChange={(value) => setEditForm({ ...editForm, study_type: value })}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select study type" />
                </SelectTrigger>
                <SelectContent>
                  {STUDY_TYPES.map((type) => (
                    <SelectItem key={type} value={type}>{type}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Intervention</Label>
              <Input
                value={editForm.intervention_type || ""}
                onChange={(e) => setEditForm({ ...editForm, intervention_type: e.target.value })}
                placeholder="e.g., cash transfer, training program"
              />
            </div>
          </div>
        </div>
      </ScrollArea>

      {/* Footer with Save/Cancel */}
      <div className="flex items-center justify-end gap-2 px-4 py-3 border-t bg-muted/30">
        <Button variant="outline" size="sm" onClick={onClose}>
          Cancel
        </Button>
        <Button size="sm" onClick={onSave} disabled={isSaving}>
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
      </div>
    </div>
  );
}
