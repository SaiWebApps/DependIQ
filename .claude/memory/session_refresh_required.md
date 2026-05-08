---
name: Session Refresh Required
description: WorkOS JWT expires in ~5-15 min; must call session.refresh() or users get silently logged out
type: project
---

WorkOS access tokens have a short lifetime. The SDK's Session.authenticate() is LOCAL only (Fernet decrypt + JWT validation). When the JWT expires, it returns INVALID_JWT. The app must call session.refresh() to get a new sealed session.

**Why:** Without refresh, users appear unauthenticated after 5-15 minutes despite having a 400-day cookie. The refresh_token is stored inside the sealed cookie and the SDK's refresh() method uses it automatically.

**How to apply:** The verify_or_refresh_session() function in workos_auth.py handles this: authenticate() → if INVALID_JWT → refresh() → return new cookie. The middleware in main.py propagates the refreshed cookie back to the response.
