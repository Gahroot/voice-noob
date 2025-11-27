"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { fetchAgents } from "@/lib/api/agents";
import { listPhoneNumbers } from "@/lib/api/phone-numbers";
import { fetchComplianceStatus } from "@/lib/api/compliance";
import { Bot, FolderOpen, Calendar, Phone, Users, Shield } from "lucide-react";
import { cn } from "@/lib/utils";
import { CompliancePanel } from "@/components/compliance-panel";

interface StatItemProps {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: number | undefined;
  isLoading: boolean;
}

function StatItem({ icon: Icon, label, value, isLoading }: StatItemProps) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <Icon className="h-3.5 w-3.5 text-muted-foreground" />
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium text-foreground">{isLoading ? "–" : (value ?? 0)}</span>
    </div>
  );
}

interface ComplianceBadgeProps {
  label: string;
  percentage: number;
  onClick: () => void;
}

function ComplianceBadge({ label, percentage, onClick }: ComplianceBadgeProps) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium transition-colors",
        "border border-transparent hover:border-border/50",
        percentage === 100
          ? "bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20"
          : percentage >= 70
            ? "bg-amber-500/10 text-amber-500 hover:bg-amber-500/20"
            : "bg-red-500/10 text-red-500 hover:bg-red-500/20"
      )}
    >
      <span
        className={cn(
          "h-1.5 w-1.5 rounded-full",
          percentage === 100 ? "bg-emerald-500" : percentage >= 70 ? "bg-amber-500" : "bg-red-500"
        )}
      />
      {label}
      <span className="tabular-nums">{percentage}%</span>
    </button>
  );
}

export function TopBar() {
  const [compliancePanelOpen, setCompliancePanelOpen] = useState(false);
  const [complianceTab, setComplianceTab] = useState<"gdpr" | "ccpa">("gdpr");

  // Fetch agents count
  const { data: agents, isLoading: agentsLoading } = useQuery({
    queryKey: ["agents-count"],
    queryFn: fetchAgents,
    staleTime: 30000,
  });

  // Fetch workspaces count
  const { data: workspaces, isLoading: workspacesLoading } = useQuery({
    queryKey: ["workspaces-count"],
    queryFn: async () => {
      const response = await api.get("/api/v1/workspaces");
      return response.data;
    },
    staleTime: 30000,
  });

  // Fetch appointments count
  const { data: appointments, isLoading: appointmentsLoading } = useQuery({
    queryKey: ["appointments-count"],
    queryFn: async () => {
      const response = await api.get("/api/v1/crm/appointments");
      return response.data;
    },
    staleTime: 30000,
  });

  // Fetch phone numbers count
  const { data: phoneNumbersData, isLoading: phoneNumbersLoading } = useQuery({
    queryKey: ["phone-numbers-count"],
    queryFn: () => listPhoneNumbers(),
    staleTime: 30000,
  });

  // Fetch CRM contacts count
  const { data: contacts, isLoading: contactsLoading } = useQuery({
    queryKey: ["contacts-count"],
    queryFn: async () => {
      const response = await api.get("/api/v1/crm/contacts");
      return response.data;
    },
    staleTime: 30000,
  });

  // Fetch compliance status
  const { data: complianceStatus } = useQuery({
    queryKey: ["compliance-status"],
    queryFn: fetchComplianceStatus,
    staleTime: 60000,
  });

  const openCompliancePanel = (tab: "gdpr" | "ccpa") => {
    setComplianceTab(tab);
    setCompliancePanelOpen(true);
  };

  return (
    <>
      <div className="flex h-12 items-center justify-between bg-sidebar px-4">
        {/* Left side - Compliance badges */}
        <div className="flex items-center gap-2">
          {complianceStatus && (
            <>
              <Shield className="h-3.5 w-3.5 text-muted-foreground" />
              <ComplianceBadge
                label="GDPR"
                percentage={complianceStatus.gdpr.percentage}
                onClick={() => openCompliancePanel("gdpr")}
              />
              <ComplianceBadge
                label="CCPA"
                percentage={complianceStatus.ccpa.percentage}
                onClick={() => openCompliancePanel("ccpa")}
              />
            </>
          )}
        </div>

        {/* Right side - Stats */}
        <div className="flex items-center gap-6">
          <StatItem icon={Bot} label="Agents" value={agents?.length} isLoading={agentsLoading} />
          <StatItem
            icon={FolderOpen}
            label="Workspaces"
            value={workspaces?.length}
            isLoading={workspacesLoading}
          />
          <StatItem
            icon={Calendar}
            label="Appointments"
            value={appointments?.length}
            isLoading={appointmentsLoading}
          />
          <StatItem
            icon={Phone}
            label="Phone Numbers"
            value={phoneNumbersData?.total}
            isLoading={phoneNumbersLoading}
          />
          <StatItem
            icon={Users}
            label="Contacts"
            value={contacts?.length}
            isLoading={contactsLoading}
          />
        </div>
      </div>

      <CompliancePanel
        open={compliancePanelOpen}
        onOpenChange={setCompliancePanelOpen}
        initialTab={complianceTab}
      />
    </>
  );
}
