# Embeddable Voice Widget Implementation Plan

## Overview

Create a full embeddable JavaScript widget that allows customers to embed voice agents on their websites. The widget will be a Web Component (`<voice-agent>`) that connects to the backend via WebRTC and provides a complete voice conversation experience.

## Architecture

```
Customer's Website                    Your Platform
┌─────────────────┐                  ┌─────────────────────────┐
│ <voice-agent    │   WebRTC/WS      │  Backend API            │
│   agent-id="x"  │ ◄───────────────►│  /api/public/embed/*    │
│   public-key=   │                  │                         │
│   "pk_xxx"/>    │                  │  Public Embed Page      │
│                 │                  │  /embed/[agent_id]      │
│ <script src=    │                  │                         │
│  "widget.js"/>  │                  │  Widget Bundle          │
└─────────────────┘                  │  /widget/v1/widget.js   │
                                     └─────────────────────────┘
```

## Components to Build

### Phase 1: Backend (Public API & Security)

#### 1.1 Database Migration - Add Embed Settings to Agent Model

**File:** `backend/migrations/versions/014_add_embed_settings.py`

Add fields to the `agents` table:
- `public_id` (VARCHAR 32) - Short URL-safe ID for public access (e.g., `ag_xK9mN2pQ`)
- `embed_enabled` (BOOLEAN) - Whether embedding is allowed for this agent
- `allowed_domains` (JSON array) - List of domains allowed to embed (`["example.com", "*.mysite.com"]`)
- `embed_settings` (JSON) - Customization options for the widget:
  ```json
  {
    "theme": "light" | "dark" | "auto",
    "position": "bottom-right" | "bottom-left" | "custom",
    "primary_color": "#6366f1",
    "greeting_message": "Hi! How can I help you today?",
    "button_text": "Talk to us",
    "show_branding": true
  }
  ```

#### 1.2 Public Embed API Routes

**File:** `backend/app/api/embed.py`

New endpoints (no authentication required, but rate-limited and domain-validated):

```python
# GET /api/public/embed/{public_id}/config
# Returns agent config for widget initialization
# - Validates Origin header against allowed_domains
# - Returns: name, greeting, voice, theme settings
# - Does NOT expose: system_prompt, tools, internal IDs

# POST /api/public/embed/{public_id}/session
# Creates ephemeral session token for WebRTC
# - Validates Origin header
# - Rate limit: 10 sessions/minute per IP
# - Returns: ephemeral_token (expires in 5 minutes), session_id

# WebSocket: /ws/public/embed/{public_id}
# Public WebSocket for voice streaming
# - Validates session_id from query param
# - Routes to appropriate backend (GPT Realtime / Pipecat)
```

#### 1.3 Origin Validation Middleware

**File:** `backend/app/middleware/embed_security.py`

```python
# Validates Origin/Referer headers against agent's allowed_domains
# Supports wildcards: "*.example.com" matches "app.example.com"
# Logs embed access attempts for analytics
# Returns 403 if domain not allowed
```

#### 1.4 Public ID Generation Utility

**File:** `backend/app/core/public_id.py`

```python
# Generate URL-safe, short public IDs: "ag_xK9mN2pQ" (12 chars)
# Uses base62 encoding with prefix
# Collision-checked against database
```

### Phase 2: Frontend Widget

#### 2.1 Embed Page (Next.js)

**File:** `frontend/src/app/embed/[publicId]/page.tsx`

Full-page voice interface designed for iframe embedding:
- Minimal UI focused on voice interaction
- Handles microphone permissions
- Shows voice visualization
- Displays transcript (optional)
- Customizable via URL params or embed_settings

Features:
- `allow="microphone"` support
- PostMessage API for parent communication
- Responsive design (works in small iframes)
- Dark/light theme support

#### 2.2 Voice Widget Component

**File:** `frontend/src/components/embed/voice-widget.tsx`

Core React component containing:
- Microphone button (push-to-talk or always-on)
- Audio visualization (waveform)
- Connection status indicator
- Optional transcript display
- Minimize/maximize controls

#### 2.3 WebRTC Voice Hook

**File:** `frontend/src/hooks/use-embed-voice.ts`

Hook handling:
- Ephemeral token fetching
- WebRTC connection establishment
- Audio stream management
- Reconnection logic
- Error handling

#### 2.4 Standalone Widget Bundle

**Directory:** `frontend/src/widget/`

Files:
- `widget.ts` - Main entry point, registers Web Component
- `widget.css` - Minimal inlined styles
- `voice-agent-element.ts` - Custom Element class

The widget will be compiled to a standalone JS file using Vite (separate build):

```html
<!-- Customer embeds this -->
<script src="https://yourplatform.com/widget/v1/widget.js" defer></script>
<voice-agent
  agent-id="ag_xK9mN2pQ"
  position="bottom-right"
  theme="auto">
</voice-agent>
```

The Web Component will:
1. Create a floating button in the corner
2. On click, open an iframe to `/embed/{publicId}`
3. Handle postMessage communication with iframe
4. Support custom element attributes for configuration

### Phase 3: Dashboard Integration

#### 3.1 Embed Dialog (Modal from 3-dot Menu)

**File:** `frontend/src/components/embed-agent-dialog.tsx`

A modal dialog triggered from the agent card's 3-dot menu → "Embed" option.

Modal contents:
- Title: "Embed {Agent Name}"
- Brief instructions: "Add this voice agent to your website"
- Two tabs/sections:
  1. **Script Tag** (recommended)
     - Code snippet with syntax highlighting
     - Copy button
  2. **iframe** (alternative)
     - Code snippet
     - Copy button
- Instructions below code:
  - "Paste this code before the closing `</body>` tag on your website"
  - Link to docs for advanced configuration

```tsx
// Example modal UI
<Dialog>
  <DialogHeader>
    <DialogTitle>Embed Voice Agent</DialogTitle>
    <DialogDescription>
      Add "{agent.name}" to your website with one of these options
    </DialogDescription>
  </DialogHeader>
  <DialogContent>
    <Tabs defaultValue="script">
      <TabsList>
        <TabsTrigger value="script">Script Tag</TabsTrigger>
        <TabsTrigger value="iframe">iframe</TabsTrigger>
      </TabsList>
      <TabsContent value="script">
        <CodeBlock code={scriptCode} />
        <p className="text-sm text-muted-foreground mt-2">
          Paste before the closing </body> tag
        </p>
      </TabsContent>
      <TabsContent value="iframe">
        <CodeBlock code={iframeCode} />
      </TabsContent>
    </Tabs>
  </DialogContent>
</Dialog>
```

#### 3.2 Update Agent Card Dropdown Menu

**File:** `frontend/src/app/dashboard/agents/page.tsx` (modify)

Add "Embed" option to the existing 3-dot dropdown menu:

```tsx
<DropdownMenuContent>
  <DropdownMenuItem>Edit</DropdownMenuItem>
  <DropdownMenuItem>Test</DropdownMenuItem>
  <DropdownMenuItem>Make Call</DropdownMenuItem>
  <DropdownMenuItem>Duplicate</DropdownMenuItem>
  <DropdownMenuItem onSelect={() => handleEmbed(agent)}>
    Embed  {/* NEW */}
  </DropdownMenuItem>
  <DropdownMenuSeparator />
  <DropdownMenuItem className="text-destructive">Delete</DropdownMenuItem>
</DropdownMenuContent>
```

#### 3.3 Agent Edit Page - Advanced Embed Settings

**File:** `frontend/src/app/dashboard/agents/[id]/page.tsx` (extend Advanced tab)

Add a collapsible section in the Advanced tab for power users:
- Toggle: "Enable widget embedding"
- Allowed domains input (add/remove domains)
- Theme selector
- Regenerate public ID button (with warning)

#### 3.4 API Routes for Agent Embed Settings

**File:** `backend/app/api/agents.py` (extend)

```python
# GET /api/v1/agents/{agent_id}/embed
# Get embed code and public_id (auto-generates if not exists)

# PATCH /api/v1/agents/{agent_id}/embed
# Update embed settings (requires auth)
# Body: { enabled, allowed_domains, settings }

# POST /api/v1/agents/{agent_id}/embed/regenerate-id
# Generate new public_id (invalidates old embeds)
```

### Phase 4: Widget Build Pipeline

#### 4.1 Vite Build Configuration

**File:** `frontend/vite.widget.config.ts`

Separate Vite config for building standalone widget:
- Entry: `src/widget/widget.ts`
- Output: `public/widget/v1/widget.js` (IIFE bundle)
- Inline CSS
- Minified for production
- Source maps for debugging

#### 4.2 Build Script

**File:** `frontend/package.json` (scripts)

```json
{
  "scripts": {
    "build:widget": "vite build --config vite.widget.config.ts",
    "dev:widget": "vite build --config vite.widget.config.ts --watch"
  }
}
```

## Security Considerations

1. **Domain Allowlisting** - Strict Origin validation prevents unauthorized embedding
2. **Ephemeral Tokens** - Short-lived (5 min) tokens for session auth
3. **Rate Limiting** - Per-IP limits on session creation
4. **No Sensitive Data** - Public API never exposes system prompts, API keys, or internal IDs
5. **CSP Headers** - Proper Content-Security-Policy for embed page
6. **CORS Configuration** - Dynamic CORS based on allowed_domains

## File Summary

### Backend (New Files)
1. `migrations/versions/014_add_embed_settings.py` - DB migration
2. `app/api/embed.py` - Public embed API routes
3. `app/middleware/embed_security.py` - Origin validation
4. `app/core/public_id.py` - Public ID generation

### Backend (Modified Files)
1. `app/models/agent.py` - Add embed fields
2. `app/api/agents.py` - Add embed settings endpoints
3. `app/core/config.py` - Add EMBED_* settings
4. `app/main.py` - Register embed router

### Frontend (New Files)
1. `src/app/embed/[publicId]/page.tsx` - Embed page
2. `src/app/embed/[publicId]/layout.tsx` - Minimal layout
3. `src/components/embed/voice-widget.tsx` - Widget component
4. `src/components/embed/audio-visualizer.tsx` - Visualization
5. `src/components/embed-agent-dialog.tsx` - Embed modal (from 3-dot menu)
6. `src/hooks/use-embed-voice.ts` - Voice hook
7. `src/widget/widget.ts` - Web Component entry
8. `src/widget/voice-agent-element.ts` - Custom Element
9. `vite.widget.config.ts` - Widget build config

### Frontend (Modified Files)
1. `src/app/dashboard/agents/page.tsx` - Add "Embed" to 3-dot menu
2. `src/app/dashboard/agents/[id]/page.tsx` - Add embed settings to Advanced tab
3. `src/lib/api/agents.ts` - Add embed API functions
4. `package.json` - Add widget build scripts
5. `next.config.ts` - Add embed page headers

## Implementation Order

1. **Database & Model** (backend)
   - Migration for new fields
   - Update Agent model

2. **Public API** (backend)
   - Public ID generator
   - Embed config endpoint
   - Session creation endpoint
   - Origin validation middleware

3. **Embed Page** (frontend)
   - Basic embed page
   - Voice widget component
   - WebRTC integration

4. **Dashboard UI** (frontend)
   - Embed settings section
   - Code generator

5. **Standalone Widget** (frontend)
   - Web Component
   - Vite build
   - CDN deployment

6. **Testing & Polish**
   - Integration tests
   - Cross-browser testing
   - Documentation

## Dependencies (New)

### Frontend
- None new (uses existing: React, Next.js, Tailwind)
- Vite (devDependency for widget build - already available via Next.js)

### Backend
- None new (uses existing: FastAPI, SQLAlchemy)

## Design Decisions

1. **Pricing tier support**: All tiers (Budget, Balanced, Premium) can embed agents
2. **Branding**: "Powered by [Platform]" badge always shown on widget
3. **Analytics**: Track embed widget usage (sessions, duration) - future enhancement
4. **Customization**: Theme (light/dark/auto), position, primary color
