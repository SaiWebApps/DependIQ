---
name: Test The Real Flow First
description: Before writing code, verify the provider/API URL works in a browser
type: feedback
---

Before writing or rewriting auth code, paste the authorization URL directly in a browser and verify the provider responds correctly. This catches configuration issues before wasting time on code.

**Why:** The WorkOS authorize URL actually worked (302 to GitHub) but we spent hours rewriting code. A single curl command at the start would have shown the URL was fine and the issue was elsewhere (database tables not created).

**How to apply:** For any OAuth integration: (1) construct the authorize URL, (2) curl it or paste in browser, (3) confirm you get a redirect to the provider. Only then write/modify code. This is the verification-first approach — prove the infrastructure works before building on it.
