# Telnyx Call Control Setup - Issue Summary

## Current Status

✅ **Completed:**
- Telnyx API key inserted into database
- Call Control Applications created with valid webhook URLs:
  - voice-agent-application-test (2840376094740186298)
  - voice-agent-application (2840375488327713956)
- Both apps have correct webhook: `https://unpiercing-undemonstrated-despina.ngrok-free.dev/webhooks/telnyx/answer`
- Webhook URL is reachable and responding (HTTP 405 on HEAD request, which is correct)
- Phone number `+12485546801` is active and owned

❌ **The Core Problem:**
The phone number `+12485546801` is configured for **Voice API** (using `connection_id`), NOT **Call Control API**.

When Telnyx rejects the call with error "Only Call Control Apps with valid webhook URL are accepted", it's because:
1. The phone number is associated with a Voice API connection (2840363967883249282)
2. Call Control API calls require the phone number to be configured for Call Control API at the account level
3. The `call_control_application_id` parameter is expecting a phone number that knows how to route to that app

## Telnyx Architecture

Telnyx offers TWO different call APIs:
1. **Voice API** - Uses SIP connections (`connection_id`)
2. **Call Control API** - Uses Call Control Applications (`call_control_application_id`)

They are different systems and a phone number can only be configured for one.

##Solution

**Option A (Recommended):** Buy a new phone number configured for Call Control API
- Would need to go through Telnyx UI/API to purchase a number specifically for Call Control
- Then configure the same Call Control Application to it

**Option B:** Switch backend to use Voice API
- Modify the TelnyxService to use Voice API instead of Call Control API
- Use the `connection_id` and proper Voice API endpoints
- This phone number already has the right connection configured

**Option C:** Check if the webhook configuration was actually applied
- The PATCH request accepted the `call_control_application_id` field, but it may not have actually taken effect
- The response showed `connection_id` field instead
- Might need to investigate Telnyx's API behavior more

## Next Steps

1. **Verify with Telnyx support** - Contact Telnyx to confirm if the phone number needs special configuration for Call Control API
2. **Try Voice API** - Consider switching to Voice API since the phone number is already configured for it
3. **Buy new number** - If Call Control API is required, purchase a new number configured for it
