"""Auth invariants — .claude/memory lessons as executable tests (plan S0.2).

Every rule here was paid for with a production incident. If one of these
fails, you are about to repeat a documented mistake. Do not weaken a test
to make it pass; fix the code.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

TOKEN_PATTERN = "localStorage.getItem('access_token')"


def _cookie_call_spans(source: str) -> list[tuple[int, str]]:
    """Return (line_number, full_call_text) for set_cookie/delete_cookie calls."""
    spans = []
    for m in re.finditer(r"\.(?:set_cookie|delete_cookie)\(", source):
        depth, i = 1, m.end()
        while i < len(source) and depth:
            depth += {"(": 1, ")": -1}.get(source[i], 0)
            i += 1
        spans.append((source[: m.start()].count("\n") + 1, source[m.start():i]))
    return spans


def test_every_cookie_call_sets_path_root():
    """Memory lesson: cookie path must always be '/'.

    Cookies set from /api/auth/... callbacks without path='/' are scoped to
    that path and invisible to page routes — users appear logged out
    everywhere except the auth endpoints.
    """
    offenders = []
    for py in [ROOT / "main.py", *sorted((ROOT / "app").rglob("*.py"))]:
        for lineno, call in _cookie_call_spans(py.read_text()):
            if 'path="/"' not in call and "path='/'" not in call:
                offenders.append(f"{py.relative_to(ROOT)}:{lineno}")
    assert not offenders, (
        "set_cookie/delete_cookie without path='/' — this exact bug class "
        f"broke auth before (.claude/memory). Offenders: {offenders}"
    )


def test_no_localstorage_token_usage_anywhere():
    """Memory lesson (this session): localStorage Bearer auth is dead code.

    The app authenticates with WorkOS sealed cookies; localStorage never
    holds a token, so this pattern sends 'Authorization: Bearer null' and
    silently breaks every call. It was eradicated in S1.1-S1.3 (11 call
    sites across 3 templates). ZERO tolerance — use
    credentials: 'same-origin' instead. Do not add an allowlist.
    """
    offenders = [
        f"{tpl.name}: {tpl.read_text().count(TOKEN_PATTERN)} occurrence(s)"
        for tpl in sorted((ROOT / "templates").rglob("*.html"))
        if TOKEN_PATTERN in tpl.read_text()
    ]
    assert not offenders, (
        "The dead localStorage-Bearer pattern is back:\n" + "\n".join(offenders)
    )


def test_session_refresh_middleware_registered():
    """Memory lesson: without session refresh propagation, users are logged
    out in ~5 minutes when the JWT expires."""
    from main import app

    names = []
    for mw in app.user_middleware:
        dispatch = mw.kwargs.get("dispatch") if mw.kwargs else None
        names.append(getattr(dispatch, "__name__", mw.cls.__name__))
    assert "refresh_session_middleware" in names, (
        f"refresh_session_middleware not registered (found: {names}) — "
        "sessions will hard-expire instead of refreshing"
    )
