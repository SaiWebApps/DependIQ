#!/usr/bin/env bash
# Read-only auth infrastructure diagnostic (plan step S0.1).
#
# Usage:  ./scripts/auth_check.sh [BASE_URL]     (default http://localhost:8000)
#         make auth-check
#         make auth-check BASE_URL=https://dependiq.onrender.com   # prod smoke
#
# Per .claude/memory: "curl the authorize URL first — if it 302s to the
# provider, infrastructure works; the bug is elsewhere." Run this BEFORE
# and AFTER any change that touches auth, cookies, sessions, or templates
# calling authed APIs. Exits non-zero on any failure. Changes nothing.

set -u
BASE="${1:-http://localhost:8000}"
FAILURES=0

probe() { # method url -> "HTTPCODE REDIRECT_URL"
    curl -s -o /dev/null -w "%{http_code} %{redirect_url}" -X "$1" "$2" --max-time 15
}

check() { # description, actual_code, expected_codes(space-sep), extra_info
    local desc="$1" actual="$2" expected="$3" extra="${4:-}"
    for e in $expected; do
        if [ "$actual" = "$e" ]; then
            echo "PASS  $desc -> $actual $extra"
            return
        fi
    done
    echo "FAIL  $desc -> got $actual, expected one of [$expected] $extra"
    FAILURES=$((FAILURES + 1))
}

echo "auth-check against $BASE"
echo "-----------------------------------------------------------"

# 1. Sign-in page renders for anonymous users
read -r code _ <<<"$(probe GET "$BASE/login")"
check "GET /login (sign-in page)" "$code" "200"

# 2. Protected page redirects anonymous users to /login
out="$(probe GET "$BASE/")"
code="${out%% *}"; loc="${out#* }"
check "GET /  (anon -> login redirect)" "$code" "303 302 307" "-> ${loc:-<no location>}"
case "$loc" in *"/login"*) : ;; "") : ;; *)
    echo "FAIL  redirect target is '$loc', expected */login"; FAILURES=$((FAILURES + 1));;
esac

# 3. THE memory-file check: authorize URL 302s to the provider
out="$(probe GET "$BASE/api/auth/login")"
code="${out%% *}"; loc="${out#* }"
check "GET /api/auth/login (provider redirect)" "$code" "302 303 307" "-> ${loc:0:80}"

# 4. Authed API rejects anonymous requests
read -r code _ <<<"$(probe GET "$BASE/api/workspaces/")"
check "GET /api/workspaces/ (anon rejected)" "$code" "401 403 303"

# 5. Session introspection rejects anonymous requests
read -r code _ <<<"$(probe GET "$BASE/api/auth/me")"
check "GET /api/auth/me (anon rejected)" "$code" "401 403"

echo "-----------------------------------------------------------"
if [ "$FAILURES" -gt 0 ]; then
    echo "auth-check: $FAILURES FAILURE(S) — auth infrastructure is NOT healthy."
    exit 1
fi
echo "auth-check: all 5 checks passed — auth infrastructure healthy."
