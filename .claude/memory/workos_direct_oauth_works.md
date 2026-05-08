---
name: WorkOS Direct OAuth Works
description: provider=GitHubOAuth bypasses AuthKit hosted UI and goes directly to GitHub
type: project
---

WorkOS's get_authorization_url with provider=GitHubOAuth redirects directly to GitHub's OAuth page. Verified by curl: returns 302 to github.com/login/oauth/authorize.

**Why:** The "Sign in with GitHub" button in the DependIQ login page uses this path. The "Sign in with Email" button uses provider=authkit which requires the sign-in endpoint (broken on localhost).

**How to apply:** For social OAuth (GitHub, Google, GitLab, Bitbucket), always use the specific provider value. Never use provider=authkit unless the sign-in endpoint matches the current environment.
