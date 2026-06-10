"""Template <-> API contract tests (plan S0.3).

The bug class these catch: a template's fetch() disagreeing with the real
FastAPI route table (wrong path, wrong method, empty body against required
fields). Neither API tests (which post valid bodies directly) nor mocked
UI tests can see this gap — it produced the workspace-creation 422 and
three pages of dead Bearer-auth calls.

Scanner notes (kept deliberately simple):
- fetch URLs with template literals (`${...}`) are normalized to a path
  parameter and matched against FastAPI's `{param}` segments.
- methods are unioned across routes sharing a path (FastAPI registers one
  route object per method).
- trailing-slash variants are accepted (Starlette 307-redirects them).
"""

import re
from collections import defaultdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Known violations — the documented burn-down list. Every entry is a REAL,
# currently-shipped bug: a fetch targeting a route that does not exist.
# All six are remnants of the pre-WorkOS GitHub flow whose backend routes
# were removed. Fix or delete the page, then remove the entry. NEVER add
# an entry without a plan-step reference.
# ---------------------------------------------------------------------------
KNOWN_MISSING_ROUTES = {
    ("analysis.html", "POST", "/start-analysis/${sessionId}"),
    ("github_repositories.html", "GET",
     "/api/github/repositories?session=${sessionId}&page=${page}&per_page=20"),
    ("github_repositories.html", "GET",
     "/api/github/repositories?session=${sessionId}&search=${encodeURIComponent(currentSearch)}"),
    ("github_repositories.html", "POST",
     "/github/analyze/${owner}/${repo}?session=${sessionId}&ref=${branch}"),
    ("github_repositories.html", "POST", "/github/disconnect?session=${sessionId}"),
    ("github_repositories.html", "GET",
     "/api/github/repository/${repo.owner.login}/${repo.name}?session=${sessionId}"),
}

# Ratchet: fetch calls sending an empty JSON body. workspaces.html's
# createWorkspace() posts {} to an endpoint requiring {"name": str} -> 422.
# Plan step S2.1 zeroes this.
EMPTY_BODY_ALLOWLIST = {"workspaces.html": 1}


def _template_fetches():
    calls = []
    for tpl in sorted((ROOT / "templates").rglob("*.html")):
        txt = tpl.read_text()
        for m in re.finditer(
            r"fetch\(\s*[`'\"]([^`'\"]+)[`'\"]\s*(?:,\s*\{(.{0,400}?)\})?", txt, re.S
        ):
            url, opts = m.group(1), m.group(2) or ""
            method_m = re.search(r"method:\s*['\"](\w+)['\"]", opts)
            method = (method_m.group(1) if method_m else "GET").upper()
            if url.startswith("/"):
                calls.append((tpl.name, method, url))
    return calls


@pytest.fixture(scope="module")
def route_methods():
    from main import app

    table: dict[str, set] = defaultdict(set)
    for r in app.routes:
        if hasattr(r, "methods") and r.methods:
            table[r.path] |= set(r.methods)
    return dict(table)


def _allowed_methods(route_methods, url) -> set:
    path = re.sub(r"\$\{[^}]+\}", "PARAM", url.split("?")[0])
    found: set = set()
    for cand in (path, path.rstrip("/") or "/", path + "/"):
        for route_path, methods in route_methods.items():
            pattern = "^" + re.sub(r"\{[^}]+\}", "[^/]+", route_path) + "$"
            if re.match(pattern, cand):
                found |= methods
    return found


def test_every_template_fetch_targets_a_real_route(route_methods):
    unexpected, fixed = [], []
    for name, method, url in _template_fetches():
        methods = _allowed_methods(route_methods, url)
        is_broken = not methods or method not in methods
        is_known = (name, method, url) in KNOWN_MISSING_ROUTES
        if is_broken and not is_known:
            unexpected.append(
                f"{name}: {method} {url} -> "
                + ("no matching route" if not methods else f"route allows {sorted(methods)}")
            )
        elif not is_broken and is_known:
            fixed.append(f"{name}: {method} {url} now resolves — remove from KNOWN_MISSING_ROUTES")
    assert not unexpected, (
        "Template fetch() disagrees with the FastAPI route table:\n" + "\n".join(unexpected)
    )
    assert not fixed, "\n".join(fixed)


def test_no_new_empty_json_bodies():
    problems = []
    for tpl in sorted((ROOT / "templates").rglob("*.html")):
        count = tpl.read_text().count("JSON.stringify({})")
        allowed = EMPTY_BODY_ALLOWLIST.get(tpl.name, 0)
        if count > allowed:
            problems.append(
                f"{tpl.name}: {count} fetch call(s) sending empty JSON body "
                f"(allowed {allowed}) — if the endpoint has required fields this is a guaranteed 422"
            )
        elif count < allowed:
            problems.append(
                f"{tpl.name}: now {count} empty bodies, allowlist says {allowed} — "
                "lower EMPTY_BODY_ALLOWLIST in the same commit"
            )
    assert not problems, "\n".join(problems)


def test_workspace_create_contract_is_satisfiable(route_methods):
    """The specific shipped bug, pinned: POST /api/workspaces/ requires a
    body with `name`. (Backend half of the S2.1 fix; the template half is
    covered by the empty-body ratchet above.)"""
    from app.api.workspaces import WorkspaceCreateRequest

    assert "name" in WorkspaceCreateRequest.model_fields
    assert WorkspaceCreateRequest.model_fields["name"].is_required()
    assert "POST" in _allowed_methods(route_methods, "/api/workspaces")
