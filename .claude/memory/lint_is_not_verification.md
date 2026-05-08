---
name: Lint Is Not Verification
description: make lint proves syntax/style only; make test proves behavior
type: feedback
---

Do not report `make lint` passing as evidence that a change works. Lint checks formatting and imports. It says nothing about whether the app starts, login works, or the database connects.

**Why:** The user called this out directly. Auth code passed lint all day while login was completely broken.

**How to apply:** After any change that affects behavior, run `make test` (all 293 tests). For auth/UI changes, also do a manual browser test. Only `make test` + manual verification = "it works."
