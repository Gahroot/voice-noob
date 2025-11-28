"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  AlertCircle,
  AlertTriangle,
  ExternalLink,
  Download,
  Shield,
  FileText,
  Clock,
  ChevronRight,
  Trash2,
  XCircle,
} from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import {
  fetchComplianceStatus,
  fetchPrivacySettings,
  updatePrivacySettings,
  recordConsent,
  exportUserData,
  ccpaOptOut,
  ccpaOptIn,
  withdrawConsent,
  deleteUserData,
  type ComplianceCheckItem,
  type ComplianceStatus,
} from "@/lib/api/compliance";

interface CompliancePanelProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialTab?: "gdpr" | "ccpa";
}

function StatusIcon({ status }: { status: string }) {
  if (status === "complete") {
    return (
      <div className="flex h-5 w-5 items-center justify-center rounded-full bg-emerald-500/20">
        <Check className="h-3 w-3 text-emerald-500" />
      </div>
    );
  }
  if (status === "warning") {
    return (
      <div className="flex h-5 w-5 items-center justify-center rounded-full bg-amber-500/20">
        <AlertTriangle className="h-3 w-3 text-amber-500" />
      </div>
    );
  }
  return (
    <div className="flex h-5 w-5 items-center justify-center rounded-full bg-red-500/20">
      <AlertCircle className="h-3 w-3 text-red-500" />
    </div>
  );
}

function ProgressBar({ percentage }: { percentage: number }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
      <div
        className={cn(
          "h-full transition-all duration-500",
          percentage === 100 ? "bg-emerald-500" : percentage >= 70 ? "bg-amber-500" : "bg-red-500"
        )}
        style={{ width: `${percentage}%` }}
      />
    </div>
  );
}

function ChecklistItem({ item, onAction }: { item: ComplianceCheckItem; onAction?: () => void }) {
  return (
    <div className="flex items-start gap-3 rounded-lg border bg-card p-3">
      <StatusIcon status={item.status} />
      <div className="flex-1 space-y-1">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium">{item.label}</span>
          {item.action_url && (
            <a
              href={item.action_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            >
              View
              <ExternalLink className="h-3 w-3" />
            </a>
          )}
        </div>
        <p className="text-xs text-muted-foreground">{item.description}</p>
        {item.action_label && item.status !== "complete" && onAction && (
          <Button variant="outline" size="sm" className="mt-2 h-7 text-xs" onClick={onAction}>
            {item.action_label}
            <ChevronRight className="ml-1 h-3 w-3" />
          </Button>
        )}
      </div>
    </div>
  );
}

function ComplianceSection({
  title,
  description,
  status,
  children,
}: {
  title: string;
  description: string;
  status: ComplianceStatus;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-4">
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold">{title}</h3>
            <p className="text-sm text-muted-foreground">{description}</p>
          </div>
          <div className="text-right">
            <div className="text-2xl font-bold">{status.percentage}%</div>
            <div className="text-xs text-muted-foreground">
              {status.completed}/{status.total} complete
            </div>
          </div>
        </div>
        <ProgressBar percentage={status.percentage} />
      </div>
      <div className="space-y-2">{children}</div>
    </div>
  );
}

export function CompliancePanel({ open, onOpenChange, initialTab = "gdpr" }: CompliancePanelProps) {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<"gdpr" | "ccpa">(initialTab);
  const [privacyPolicyUrl, setPrivacyPolicyUrl] = useState("");
  const [isExporting, setIsExporting] = useState(false);

  const { data: complianceStatus, isLoading: statusLoading } = useQuery({
    queryKey: ["compliance-status"],
    queryFn: fetchComplianceStatus,
    enabled: open,
    staleTime: 30000,
  });

  const { data: privacySettings } = useQuery({
    queryKey: ["privacy-settings"],
    queryFn: fetchPrivacySettings,
    enabled: open,
    staleTime: 30000,
  });

  const updateSettingsMutation = useMutation({
    mutationFn: updatePrivacySettings,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["compliance-status"] });
      void queryClient.invalidateQueries({ queryKey: ["privacy-settings"] });
    },
  });

  const recordConsentMutation = useMutation({
    mutationFn: ({ type, granted }: { type: string; granted: boolean }) =>
      recordConsent(type, granted),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["compliance-status"] });
    },
  });

  const ccpaOptOutMutation = useMutation({
    mutationFn: ccpaOptOut,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["compliance-status"] });
      void queryClient.invalidateQueries({ queryKey: ["privacy-settings"] });
    },
  });

  const ccpaOptInMutation = useMutation({
    mutationFn: ccpaOptIn,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["compliance-status"] });
      void queryClient.invalidateQueries({ queryKey: ["privacy-settings"] });
    },
  });

  const withdrawConsentMutation = useMutation({
    mutationFn: withdrawConsent,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["compliance-status"] });
    },
  });

  const deleteDataMutation = useMutation({
    mutationFn: deleteUserData,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["compliance-status"] });
      void queryClient.invalidateQueries({ queryKey: ["privacy-settings"] });
    },
  });

  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState("");

  const handleDeleteData = async () => {
    if (deleteConfirm !== "DELETE") return;
    setIsDeleting(true);
    try {
      await deleteDataMutation.mutateAsync();
      setDeleteConfirm("");
    } finally {
      setIsDeleting(false);
    }
  };

  const handleExportData = async () => {
    setIsExporting(true);
    try {
      const data = await exportUserData();
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `data-export-${new Date().toISOString().split("T")[0]}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      void queryClient.invalidateQueries({ queryKey: ["privacy-settings"] });
    } finally {
      setIsExporting(false);
    }
  };

  const handleSavePrivacyPolicy = () => {
    if (privacyPolicyUrl) {
      updateSettingsMutation.mutate({ privacy_policy_url: privacyPolicyUrl });
    }
  };

  const handleDpaSigned = (provider: string, signed: boolean) => {
    updateSettingsMutation.mutate({
      [`${provider}_dpa_signed`]: signed,
    });
  };

  const getActionHandler = (item: ComplianceCheckItem) => {
    if (item.id === "data_processing_consent") {
      return () => recordConsentMutation.mutate({ type: "data_processing", granted: true });
    }
    if (item.id === "recording_consent") {
      return () => recordConsentMutation.mutate({ type: "call_recording", granted: true });
    }
    return undefined;
  };

  if (statusLoading || !complianceStatus) {
    return (
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent side="right" className="w-full sm:max-w-lg">
          <div className="flex h-full items-center justify-center">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          </div>
        </SheetContent>
      </Sheet>
    );
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-lg">
        <SheetHeader className="space-y-1">
          <SheetTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            Compliance Center
          </SheetTitle>
          <SheetDescription>
            Track and manage your GDPR and CCPA compliance requirements
          </SheetDescription>
        </SheetHeader>

        <Tabs
          value={activeTab}
          onValueChange={(v) => setActiveTab(v as "gdpr" | "ccpa")}
          className="mt-6"
        >
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="gdpr" className="gap-2">
              <span
                className={cn(
                  "h-2 w-2 rounded-full",
                  complianceStatus.gdpr.percentage === 100 ? "bg-emerald-500" : "bg-amber-500"
                )}
              />
              GDPR
            </TabsTrigger>
            <TabsTrigger value="ccpa" className="gap-2">
              <span
                className={cn(
                  "h-2 w-2 rounded-full",
                  complianceStatus.ccpa.percentage === 100 ? "bg-emerald-500" : "bg-amber-500"
                )}
              />
              CCPA
            </TabsTrigger>
          </TabsList>

          <TabsContent value="gdpr" className="mt-6 space-y-6">
            <ComplianceSection
              title="GDPR Compliance"
              description="General Data Protection Regulation (EU)"
              status={complianceStatus.gdpr}
            >
              {complianceStatus.gdpr.checks.map((item) => (
                <ChecklistItem key={item.id} item={item} onAction={getActionHandler(item)} />
              ))}
            </ComplianceSection>

            {/* Privacy Policy Input */}
            <div className="space-y-3 rounded-lg border bg-card p-4">
              <div className="flex items-center gap-2">
                <FileText className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm font-medium">Privacy Policy URL</span>
              </div>
              <div className="flex gap-2">
                <Input
                  placeholder="https://yoursite.com/privacy"
                  value={privacyPolicyUrl ?? privacySettings?.privacy_policy_url ?? ""}
                  onChange={(e) => setPrivacyPolicyUrl(e.target.value)}
                  className="h-9"
                />
                <Button
                  size="sm"
                  onClick={handleSavePrivacyPolicy}
                  disabled={updateSettingsMutation.isPending}
                >
                  Save
                </Button>
              </div>
            </div>

            {/* DPA Toggles */}
            <div className="space-y-3 rounded-lg border bg-card p-4">
              <span className="text-sm font-medium">Data Processing Agreements</span>
              <p className="text-xs text-muted-foreground">
                Mark as signed after completing each DPA with your vendors
              </p>
              <div className="space-y-3 pt-2">
                {[
                  {
                    key: "openai",
                    label: "OpenAI",
                    url: "https://openai.com/policies/data-processing-addendum/",
                  },
                  {
                    key: "telnyx",
                    label: "Telnyx",
                    url: "https://telnyx.com/legal/data-processing-addendum",
                  },
                  {
                    key: "deepgram",
                    label: "Deepgram",
                    url: "https://developers.deepgram.com/docs/data-privacy-compliance",
                  },
                  {
                    key: "elevenlabs",
                    label: "ElevenLabs",
                    url: "https://elevenlabs.io/dpa",
                  },
                ].map((provider) => (
                  <div key={provider.key} className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-sm">{provider.label} DPA</span>
                      <a
                        href={provider.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                      >
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    </div>
                    <Switch
                      checked={
                        (privacySettings?.[
                          `${provider.key}_dpa_signed` as keyof typeof privacySettings
                        ] as boolean) ?? false
                      }
                      onCheckedChange={(checked) => handleDpaSigned(provider.key, checked)}
                    />
                  </div>
                ))}
              </div>
            </div>

            {/* Data Export */}
            <div className="space-y-3 rounded-lg border bg-card p-4">
              <div className="flex items-center gap-2">
                <Download className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm font-medium">Data Export</span>
              </div>
              <p className="text-xs text-muted-foreground">
                Download all your data in JSON format (GDPR Article 20)
              </p>
              {privacySettings?.last_data_export_at && (
                <p className="flex items-center gap-1 text-xs text-muted-foreground">
                  <Clock className="h-3 w-3" />
                  Last export: {new Date(privacySettings.last_data_export_at).toLocaleDateString()}
                </p>
              )}
              <Button
                variant="outline"
                size="sm"
                onClick={() => void handleExportData()}
                disabled={isExporting}
                className="w-full"
              >
                {isExporting ? "Exporting..." : "Export My Data"}
              </Button>
            </div>

            {/* Consent Withdrawal */}
            <div className="space-y-3 rounded-lg border bg-card p-4">
              <div className="flex items-center gap-2">
                <XCircle className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm font-medium">Withdraw Consent</span>
              </div>
              <p className="text-xs text-muted-foreground">
                Withdraw previously given consent (GDPR Article 7(3))
              </p>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => withdrawConsentMutation.mutate("data_processing")}
                  disabled={withdrawConsentMutation.isPending}
                >
                  Data Processing
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => withdrawConsentMutation.mutate("call_recording")}
                  disabled={withdrawConsentMutation.isPending}
                >
                  Call Recording
                </Button>
              </div>
            </div>

            {/* Danger Zone - Data Deletion */}
            <div className="space-y-3 rounded-lg border border-destructive/50 bg-card p-4">
              <div className="flex items-center gap-2">
                <Trash2 className="h-4 w-4 text-destructive" />
                <span className="text-sm font-medium text-destructive">Danger Zone</span>
              </div>
              <p className="text-xs text-muted-foreground">
                Delete all your data permanently (GDPR Article 17 - Right to Erasure)
              </p>
              <p className="text-xs text-destructive/80">
                This will delete all agents, workspaces, contacts, appointments, call records, and
                settings. This action cannot be undone.
              </p>
              <div className="flex gap-2">
                <Input
                  placeholder="Type DELETE to confirm"
                  value={deleteConfirm}
                  onChange={(e) => setDeleteConfirm(e.target.value)}
                  className="h-9"
                />
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => void handleDeleteData()}
                  disabled={isDeleting || deleteConfirm !== "DELETE"}
                >
                  {isDeleting ? "Deleting..." : "Delete All Data"}
                </Button>
              </div>
            </div>
          </TabsContent>

          <TabsContent value="ccpa" className="mt-6 space-y-6">
            <ComplianceSection
              title="CCPA Compliance"
              description="California Consumer Privacy Act"
              status={complianceStatus.ccpa}
            >
              {complianceStatus.ccpa.checks.map((item) => (
                <ChecklistItem key={item.id} item={item} />
              ))}
            </ComplianceSection>

            {/* CCPA Opt-Out */}
            <div className="space-y-3 rounded-lg border bg-card p-4">
              <span className="text-sm font-medium">Do Not Sell My Personal Information</span>
              <p className="text-xs text-muted-foreground">
                Exercise your CCPA right to opt out of the sale or sharing of your personal
                information
              </p>
              <div className="flex items-center justify-between pt-2">
                <span className="text-sm">
                  {privacySettings?.ccpa_opt_out ? "Opted out" : "Not opted out"}
                </span>
                <Button
                  variant={privacySettings?.ccpa_opt_out ? "outline" : "destructive"}
                  size="sm"
                  onClick={() =>
                    privacySettings?.ccpa_opt_out
                      ? ccpaOptInMutation.mutate()
                      : ccpaOptOutMutation.mutate()
                  }
                  disabled={ccpaOptOutMutation.isPending || ccpaOptInMutation.isPending}
                >
                  {privacySettings?.ccpa_opt_out ? "Opt Back In" : "Opt Out"}
                </Button>
              </div>
              {privacySettings?.ccpa_opt_out_at && (
                <p className="flex items-center gap-1 text-xs text-muted-foreground">
                  <Clock className="h-3 w-3" />
                  Opted out on: {new Date(privacySettings.ccpa_opt_out_at).toLocaleDateString()}
                </p>
              )}
            </div>

            {/* Data Export (also in CCPA) */}
            <div className="space-y-3 rounded-lg border bg-card p-4">
              <div className="flex items-center gap-2">
                <Download className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm font-medium">Request My Data</span>
              </div>
              <p className="text-xs text-muted-foreground">
                Download all data we have collected about you (CCPA Right to Know)
              </p>
              <Button
                variant="outline"
                size="sm"
                onClick={() => void handleExportData()}
                disabled={isExporting}
                className="w-full"
              >
                {isExporting ? "Exporting..." : "Download Data"}
              </Button>
            </div>
          </TabsContent>
        </Tabs>
      </SheetContent>
    </Sheet>
  );
}
