/**
 * API client for compliance endpoints (GDPR/CCPA)
 */

import { api } from "@/lib/api";

export interface ComplianceCheckItem {
  id: string;
  label: string;
  description: string;
  status: "complete" | "incomplete" | "warning";
  action_url?: string;
  action_label?: string;
}

export interface ComplianceStatus {
  completed: number;
  total: number;
  percentage: number;
  checks: ComplianceCheckItem[];
}

export interface ComplianceOverview {
  gdpr: ComplianceStatus;
  ccpa: ComplianceStatus;
}

export interface PrivacySettings {
  privacy_policy_url: string | null;
  privacy_policy_accepted_at: string | null;
  data_retention_days: number;
  openai_dpa_signed: boolean;
  openai_dpa_signed_at: string | null;
  telnyx_dpa_signed: boolean;
  telnyx_dpa_signed_at: string | null;
  deepgram_dpa_signed: boolean;
  deepgram_dpa_signed_at: string | null;
  elevenlabs_dpa_signed: boolean;
  elevenlabs_dpa_signed_at: string | null;
  ccpa_opt_out: boolean;
  ccpa_opt_out_at: string | null;
  last_data_export_at: string | null;
}

export interface UpdatePrivacySettingsRequest {
  privacy_policy_url?: string | null;
  data_retention_days?: number;
  openai_dpa_signed?: boolean;
  telnyx_dpa_signed?: boolean;
  deepgram_dpa_signed?: boolean;
  elevenlabs_dpa_signed?: boolean;
  ccpa_opt_out?: boolean;
}

export interface DataExport {
  user: Record<string, unknown>;
  settings: Record<string, unknown> | null;
  privacy_settings: Record<string, unknown> | null;
  agents: Record<string, unknown>[];
  workspaces: Record<string, unknown>[];
  contacts: Record<string, unknown>[];
  appointments: Record<string, unknown>[];
  call_records: Record<string, unknown>[];
  call_interactions: Record<string, unknown>[];
  consent_records: Record<string, unknown>[];
  exported_at: string;
}

/**
 * Get compliance status overview
 */
export async function fetchComplianceStatus(): Promise<ComplianceOverview> {
  const response = await api.get("/api/v1/compliance/status");
  return response.data;
}

/**
 * Get privacy settings
 */
export async function fetchPrivacySettings(): Promise<PrivacySettings> {
  const response = await api.get("/api/v1/compliance/privacy-settings");
  return response.data;
}

/**
 * Update privacy settings
 */
export async function updatePrivacySettings(
  settings: UpdatePrivacySettingsRequest
): Promise<PrivacySettings> {
  const response = await api.patch("/api/v1/compliance/privacy-settings", settings);
  return response.data;
}

/**
 * Record consent
 */
export async function recordConsent(
  consentType: string,
  granted: boolean
): Promise<{ message: string }> {
  const response = await api.post("/api/v1/compliance/consent", {
    consent_type: consentType,
    granted,
  });
  return response.data;
}

/**
 * Export all user data
 */
export async function exportUserData(): Promise<DataExport> {
  const response = await api.get("/api/v1/compliance/export");
  return response.data;
}

/**
 * CCPA opt-out of data sharing
 */
export async function ccpaOptOut(): Promise<{ message: string }> {
  const response = await api.post("/api/v1/compliance/ccpa/opt-out");
  return response.data;
}

/**
 * CCPA opt back in to data sharing
 */
export async function ccpaOptIn(): Promise<{ message: string }> {
  const response = await api.post("/api/v1/compliance/ccpa/opt-in");
  return response.data;
}

/**
 * Withdraw consent
 */
export async function withdrawConsent(consentType: string): Promise<{ message: string }> {
  const response = await api.post("/api/v1/compliance/consent/withdraw", {
    consent_type: consentType,
    granted: false,
  });
  return response.data;
}

export interface DataDeletionResponse {
  deleted_counts: Record<string, number>;
  deleted_at: string;
}

/**
 * Delete all user data (GDPR Article 17 / CCPA Right to Delete)
 */
export async function deleteUserData(): Promise<DataDeletionResponse> {
  const response = await api.delete("/api/v1/compliance/data");
  return response.data;
}
