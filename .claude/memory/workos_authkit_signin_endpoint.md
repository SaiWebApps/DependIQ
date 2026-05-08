---
name: WorkOS AuthKit Sign-In Endpoint
description: AuthKit hosted UI (provider=authkit) requires a sign-in endpoint that matches the request origin
type: project
---

WorkOS's AuthKit hosted login UI requires a "Sign-in endpoint" in the dashboard. Only ONE can be configured. If set to production (https://dependiq.onrender.com/sign-in), localhost requests fail with `invalid-connection-selector`.

**Why:** The AuthKit flow redirects through WorkOS's hosted page, which uses the sign-in endpoint to route back. Origin mismatch = failure.

**How to apply:** Use direct OAuth (provider=GitHubOAuth, provider=GoogleOAuth) instead of provider=authkit. Direct OAuth bypasses the hosted UI and goes straight to the provider. The sign-in endpoint is irrelevant for direct OAuth flows.
