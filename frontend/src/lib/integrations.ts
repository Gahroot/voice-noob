export type IntegrationType = "crm" | "calendar" | "database" | "productivity" | "communication" | "other";

export type AuthType = "oauth" | "api_key" | "basic" | "none";

export interface Integration {
  id: string;
  name: string;
  slug: string;
  description: string;
  category: IntegrationType;
  authType: AuthType;
  icon: string;
  enabled: boolean;
  isPopular?: boolean;
  fields?: IntegrationField[];
  scopes?: string[];
  documentationUrl?: string;
}

export interface IntegrationField {
  name: string;
  label: string;
  type: "text" | "password" | "url" | "email";
  placeholder?: string;
  required: boolean;
  description?: string;
}

export const AVAILABLE_INTEGRATIONS: Integration[] = [
  // CRM
  {
    id: "salesforce",
    name: "Salesforce",
    slug: "salesforce",
    description: "Access customer data, create leads, update opportunities",
    category: "crm",
    authType: "oauth",
    icon: "https://cdn.simpleicons.org/salesforce",
    enabled: true,
    isPopular: true,
    scopes: ["api", "refresh_token", "offline_access"],
    documentationUrl: "https://developer.salesforce.com/docs/",
  },
  {
    id: "hubspot",
    name: "HubSpot",
    slug: "hubspot",
    description: "Manage contacts, deals, and customer interactions",
    category: "crm",
    authType: "oauth",
    icon: "https://cdn.simpleicons.org/hubspot",
    enabled: true,
    isPopular: true,
    scopes: ["crm.objects.contacts.read", "crm.objects.deals.read"],
  },
  {
    id: "pipedrive",
    name: "Pipedrive",
    slug: "pipedrive",
    description: "Sales pipeline and deal management",
    category: "crm",
    authType: "api_key",
    icon: "https://cdn.simpleicons.org/pipedrive",
    enabled: true,
    fields: [
      {
        name: "api_token",
        label: "API Token",
        type: "password",
        required: true,
        description: "Found in Settings > Personal > API",
      },
      {
        name: "domain",
        label: "Domain",
        type: "text",
        placeholder: "yourcompany.pipedrive.com",
        required: true,
      },
    ],
  },
  {
    id: "zoho-crm",
    name: "Zoho CRM",
    slug: "zoho-crm",
    description: "Customer relationship management",
    category: "crm",
    authType: "oauth",
    icon: "https://cdn.simpleicons.org/zoho",
    enabled: true,
  },

  // Calendar
  {
    id: "google-calendar",
    name: "Google Calendar",
    slug: "google-calendar",
    description: "Schedule meetings, check availability, create events",
    category: "calendar",
    authType: "oauth",
    icon: "https://cdn.simpleicons.org/googlecalendar",
    enabled: true,
    isPopular: true,
    scopes: ["https://www.googleapis.com/auth/calendar", "https://www.googleapis.com/auth/calendar.events"],
  },
  {
    id: "microsoft-calendar",
    name: "Microsoft Calendar",
    slug: "microsoft-calendar",
    description: "Outlook calendar integration",
    category: "calendar",
    authType: "oauth",
    icon: "https://cdn.simpleicons.org/microsoftoutlook",
    enabled: true,
    isPopular: true,
    scopes: ["Calendars.ReadWrite", "offline_access"],
  },
  {
    id: "cal-com",
    name: "Cal.com",
    slug: "cal-com",
    description: "Open-source scheduling platform",
    category: "calendar",
    authType: "api_key",
    icon: "https://cdn.simpleicons.org/caldotcom",
    enabled: true,
    fields: [
      {
        name: "api_key",
        label: "API Key",
        type: "password",
        required: true,
      },
    ],
  },

  // Database & Storage
  {
    id: "airtable",
    name: "Airtable",
    slug: "airtable",
    description: "Access and update database records",
    category: "database",
    authType: "oauth",
    icon: "https://cdn.simpleicons.org/airtable",
    enabled: true,
    scopes: ["data.records:read", "data.records:write"],
  },
  {
    id: "notion",
    name: "Notion",
    slug: "notion",
    description: "Query and update Notion databases",
    category: "database",
    authType: "oauth",
    icon: "https://cdn.simpleicons.org/notion",
    enabled: true,
    isPopular: true,
  },
  {
    id: "google-sheets",
    name: "Google Sheets",
    slug: "google-sheets",
    description: "Read and write spreadsheet data",
    category: "database",
    authType: "oauth",
    icon: "https://cdn.simpleicons.org/googlesheets",
    enabled: true,
    isPopular: true,
    scopes: ["https://www.googleapis.com/auth/spreadsheets"],
  },

  // Productivity
  {
    id: "slack",
    name: "Slack",
    slug: "slack",
    description: "Send messages, notifications, and alerts",
    category: "communication",
    authType: "oauth",
    icon: "https://cdn.simpleicons.org/slack",
    enabled: true,
    isPopular: true,
    scopes: ["chat:write", "channels:read"],
  },
  {
    id: "gmail",
    name: "Gmail",
    slug: "gmail",
    description: "Send emails and search inbox",
    category: "communication",
    authType: "oauth",
    icon: "https://cdn.simpleicons.org/gmail",
    enabled: true,
    isPopular: true,
    scopes: ["https://www.googleapis.com/auth/gmail.send"],
  },
  {
    id: "sendgrid",
    name: "SendGrid",
    slug: "sendgrid",
    description: "Transactional email sending",
    category: "communication",
    authType: "api_key",
    icon: "https://cdn.simpleicons.org/sendgrid",
    enabled: true,
    fields: [
      {
        name: "api_key",
        label: "API Key",
        type: "password",
        required: true,
      },
    ],
  },

  // Other Tools
  {
    id: "stripe",
    name: "Stripe",
    slug: "stripe",
    description: "Payment processing and subscription management",
    category: "other",
    authType: "api_key",
    icon: "https://cdn.simpleicons.org/stripe",
    enabled: true,
    isPopular: true,
    fields: [
      {
        name: "api_key",
        label: "Secret Key",
        type: "password",
        required: true,
        placeholder: "sk_...",
      },
    ],
  },
  {
    id: "github",
    name: "GitHub",
    slug: "github",
    description: "Repository and issue management",
    category: "productivity",
    authType: "oauth",
    icon: "https://cdn.simpleicons.org/github",
    enabled: true,
    scopes: ["repo", "read:org"],
  },
  {
    id: "jira",
    name: "Jira",
    slug: "jira",
    description: "Project management and issue tracking",
    category: "productivity",
    authType: "oauth",
    icon: "https://cdn.simpleicons.org/jira",
    enabled: true,
  },
  {
    id: "zendesk",
    name: "Zendesk",
    slug: "zendesk",
    description: "Customer support ticketing",
    category: "crm",
    authType: "oauth",
    icon: "https://cdn.simpleicons.org/zendesk",
    enabled: true,
  },
  {
    id: "intercom",
    name: "Intercom",
    slug: "intercom",
    description: "Customer messaging and support",
    category: "communication",
    authType: "oauth",
    icon: "https://cdn.simpleicons.org/intercom",
    enabled: true,
  },
];

export interface UserIntegration {
  id: string;
  integrationId: string;
  userId: string;
  isConnected: boolean;
  connectedAt?: Date;
  credentials?: Record<string, string>;
  metadata?: Record<string, any>;
}
