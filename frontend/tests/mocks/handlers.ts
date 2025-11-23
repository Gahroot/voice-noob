import { http, HttpResponse } from "msw";
import { mockContacts, mockCRMStats } from "./data";

const API_URL = "http://localhost:8000";

export const handlers = [
  // Health check
  http.get(`${API_URL}/api/health`, () => {
    return HttpResponse.json({ status: "ok" });
  }),

  // List contacts
  http.get(`${API_URL}/crm/contacts`, () => {
    return HttpResponse.json(mockContacts);
  }),

  // Get single contact
  http.get(`${API_URL}/crm/contacts/:id`, ({ params }) => {
    const contact = mockContacts.find((c) => c.id === Number(params.id));

    if (!contact) {
      return HttpResponse.json(
        { detail: "Contact not found" },
        { status: 404 }
      );
    }

    return HttpResponse.json(contact);
  }),

  // Create contact
  http.post(`${API_URL}/crm/contacts`, async ({ request }) => {
    const body = (await request.json());

    return HttpResponse.json(
      {
        id: mockContacts.length + 1,
        user_id: 1,
        ...body,
      },
      { status: 201 }
    );
  }),

  // CRM stats
  http.get(`${API_URL}/crm/stats`, () => {
    return HttpResponse.json(mockCRMStats);
  }),

  // Error scenario: 404
  http.get(`${API_URL}/crm/contacts/999`, () => {
    return HttpResponse.json({ detail: "Contact not found" }, { status: 404 });
  }),

  // Error scenario: 401 Unauthorized
  http.get(`${API_URL}/api/unauthorized`, () => {
    return HttpResponse.json(
      { detail: "Not authenticated" },
      { status: 401 }
    );
  }),
];
