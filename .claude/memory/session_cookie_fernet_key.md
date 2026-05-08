---
name: Session Cookie Password Is Fernet Key
description: WORKOS_COOKIE_PASSWORD must be exactly 32 bytes URL-safe base64 from Fernet.generate_key()
type: project
---

The WorkOS sealed session uses cryptography.fernet.Fernet for symmetric encryption. The cookie password is NOT an arbitrary string — it must be a valid Fernet key (32 bytes, URL-safe base64, 44 characters).

**Why:** Passing an invalid key crashes with `ValueError: Fernet key must be 32 url-safe base64-encoded bytes`. The Makefile's `_ensure-env` target auto-generates this via `Fernet.generate_key()`.

**How to apply:** Never hand-type this value. Always generate with `from cryptography.fernet import Fernet; Fernet.generate_key().decode()`. The current .env already has a valid key.
