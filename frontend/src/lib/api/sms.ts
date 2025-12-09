/**
 * SMS API client for conversations, messages, and campaigns.
 */

import { api } from "@/lib/api";

// Types
export interface SMSConversation {
  id: string;
  contact_id: number | null;
  contact_name: string | null;
  from_number: string;
  to_number: string;
  status: string;
  unread_count: number;
  last_message_preview: string | null;
  last_message_at: string | null;
  last_message_direction: string | null;
  created_at: string;
}

export interface SMSMessage {
  id: string;
  direction: "inbound" | "outbound";
  from_number: string;
  to_number: string;
  body: string;
  status: string;
  is_read: boolean;
  sent_at: string | null;
  delivered_at: string | null;
  created_at: string;
  agent_id: string | null;
  error_message: string | null;
}

export interface SMSCampaign {
  id: string;
  name: string;
  description: string | null;
  status: string;
  from_phone_number: string;
  initial_message: string;
  ai_enabled: boolean;
  total_contacts: number;
  messages_sent: number;
  messages_delivered: number;
  replies_received: number;
  contacts_qualified: number;
  contacts_opted_out: number;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface SMSCampaignContact {
  id: string;
  contact_id: number;
  contact_name: string | null;
  contact_phone: string;
  status: string;
  messages_sent: number;
  messages_received: number;
  is_qualified: boolean;
  opted_out: boolean;
  first_sent_at: string | null;
  last_reply_at: string | null;
}

export interface CreateCampaignRequest {
  name: string;
  description?: string;
  from_phone_number: string;
  initial_message: string;
  agent_id?: string;
  ai_enabled?: boolean;
  ai_system_prompt?: string;
  qualification_criteria?: string;
  sending_hours_start?: string;
  sending_hours_end?: string;
  sending_days?: number[];
  timezone?: string;
  messages_per_minute?: number;
  follow_up_enabled?: boolean;
  follow_up_delay_hours?: number;
  follow_up_message?: string;
  max_follow_ups?: number;
  contact_ids?: number[];
}

export interface SendMessageRequest {
  to_number: string;
  from_number: string;
  body: string;
  conversation_id?: string;
}

// Conversation API
export async function listConversations(
  workspaceId: string,
  status?: string,
  limit = 50,
  offset = 0
): Promise<SMSConversation[]> {
  const params = new URLSearchParams({
    workspace_id: workspaceId,
    limit: limit.toString(),
    offset: offset.toString(),
  });
  if (status) params.append("status", status);

  const response = await api.get(`/api/v1/sms/conversations?${params}`);
  return response.data;
}

export async function getConversation(conversationId: string): Promise<SMSConversation> {
  const response = await api.get(`/api/v1/sms/conversations/${conversationId}`);
  return response.data;
}

export async function getConversationMessages(
  conversationId: string,
  limit = 100,
  offset = 0
): Promise<SMSMessage[]> {
  const params = new URLSearchParams({
    limit: limit.toString(),
    offset: offset.toString(),
  });
  const response = await api.get(`/api/v1/sms/conversations/${conversationId}/messages?${params}`);
  return response.data;
}

export async function markConversationRead(
  conversationId: string,
  workspaceId: string
): Promise<void> {
  await api.post(`/api/v1/sms/conversations/${conversationId}/read?workspace_id=${workspaceId}`);
}

// Message API
export async function sendMessage(
  request: SendMessageRequest,
  workspaceId: string
): Promise<SMSMessage> {
  const response = await api.post(`/api/v1/sms/messages?workspace_id=${workspaceId}`, request);
  return response.data;
}

// Campaign API
export async function listCampaigns(workspaceId: string, status?: string): Promise<SMSCampaign[]> {
  const params = new URLSearchParams({ workspace_id: workspaceId });
  if (status) params.append("status", status);

  const response = await api.get(`/api/v1/sms/campaigns?${params}`);
  return response.data;
}

export async function getCampaign(campaignId: string): Promise<SMSCampaign> {
  const response = await api.get(`/api/v1/sms/campaigns/${campaignId}`);
  return response.data;
}

export async function createCampaign(
  request: CreateCampaignRequest,
  workspaceId: string
): Promise<SMSCampaign> {
  const response = await api.post(`/api/v1/sms/campaigns?workspace_id=${workspaceId}`, request);
  return response.data;
}

export async function startCampaign(campaignId: string): Promise<void> {
  await api.post(`/api/v1/sms/campaigns/${campaignId}/start`);
}

export async function pauseCampaign(campaignId: string): Promise<void> {
  await api.post(`/api/v1/sms/campaigns/${campaignId}/pause`);
}

export async function getCampaignContacts(
  campaignId: string,
  status?: string,
  limit = 50,
  offset = 0
): Promise<SMSCampaignContact[]> {
  const params = new URLSearchParams({
    limit: limit.toString(),
    offset: offset.toString(),
  });
  if (status) params.append("status", status);

  const response = await api.get(`/api/v1/sms/campaigns/${campaignId}/contacts?${params}`);
  return response.data;
}

export async function addContactsToCampaign(
  campaignId: string,
  contactIds: number[]
): Promise<{ added: number }> {
  const response = await api.post(`/api/v1/sms/campaigns/${campaignId}/contacts`, contactIds);
  return response.data;
}
