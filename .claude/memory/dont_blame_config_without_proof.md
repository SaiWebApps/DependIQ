---
name: Don't Blame Config Without Proof
description: Verify claims against the actual API/system before blaming external configuration
type: feedback
---

Do not tell the user "your WorkOS config is wrong" without evidence. Use the API (curl, SDK calls, diagnostic scripts) to verify before making claims.

**Why:** Spent hours blaming WorkOS dashboard config (redirect URIs, sign-in endpoint, providers) when the user's config was correct. The actual issues were: (1) AuthKit sign-in endpoint mismatch for localhost (architectural, not config), (2) empty migration creating no tables (our bug). Blaming config destroyed trust.

**How to apply:** Before saying "check your dashboard config," first: (1) make an API call to verify the claim, (2) use curl to test the actual URL, (3) read the server logs for the specific error. If you can't verify, say "I don't know" instead of guessing.
