export const mockContacts = [
  {
    id: 1,
    user_id: 1,
    first_name: "John",
    last_name: "Doe",
    email: "john@example.com",
    phone_number: "+15551234567",
    company_name: "Acme Corp",
    status: "new",
    tags: "sales,vip",
    notes: "Interested in premium tier",
  },
  {
    id: 2,
    user_id: 1,
    first_name: "Jane",
    last_name: "Smith",
    email: "jane@techstartup.com",
    phone_number: "+15559876543",
    company_name: "Tech Startup Inc",
    status: "qualified",
    tags: "enterprise,hot-lead",
    notes: "Ready to sign up",
  },
  {
    id: 3,
    user_id: 1,
    first_name: "Bob",
    last_name: "Johnson",
    email: "bob@example.com",
    phone_number: "+15555555555",
    company_name: null,
    status: "contacted",
    tags: null,
    notes: null,
  },
];

export const mockCRMStats = {
  total_contacts: 42,
  total_appointments: 15,
  total_calls: 103,
};

export const mockPricingTiers = [
  {
    id: "budget",
    name: "Budget",
    costPerHour: 0.86,
    costPerMinute: 0.0143,
  },
  {
    id: "balanced",
    name: "Balanced",
    costPerHour: 1.35,
    costPerMinute: 0.0225,
    recommended: true,
  },
  {
    id: "premium",
    name: "Premium",
    costPerHour: 1.92,
    costPerMinute: 0.032,
  },
];
