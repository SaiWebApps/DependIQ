#!/usr/bin/env python
"""Mechanical verification of every major claim made in docs/team/*.

Run from repo root:  .venv/bin/python scripts/verify_claims.py
Each check executes REAL project code (real app object, real rendering
functions, real templates) and prints CONFIRMED / REFUTED / STATIC-ONLY.
STATIC-ONLY = code evidence shown, but runtime proof needs a live service
this script doesn't assume (Neo4j / prod) — the command to finish the
proof yourself is printed.

Zero app code is touched. This script only reads.
"""

import inspect
import re
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
results: list[tuple[str, str, str]] = []  # (claim_id, verdict, evidence)


def record(cid: str, verdict: str, evidence: str) -> None:
    results.append((cid, verdict, evidence))
    print(f"\n[{cid}] {verdict}")
    print(textwrap.indent(evidence.strip(), "    "))


def main() -> None:  # noqa: C901
    # ----------------------------------------------------------------- C1
    # Claim: workspaces.html POSTs {} but API requires `name` -> 422
    tpl = (ROOT / "templates/workspaces.html").read_text()
    sends_empty = "JSON.stringify({})" in tpl

    from fastapi.testclient import TestClient

    from app.api import workspaces as ws_mod
    from main import app

    app.dependency_overrides[ws_mod.get_current_user] = lambda: object()
    client = TestClient(app, raise_server_exceptions=False)
    r = client.post("/api/workspaces/", json={})
    app.dependency_overrides.clear()
    verdict = "CONFIRMED" if (sends_empty and r.status_code == 422) else "REFUTED"
    record(
        "C1 workspace creation broken",
        verdict,
        f"template sends JSON.stringify({{}}): {sends_empty}\n"
        f"REAL request POST /api/workspaces/ with body {{}} -> HTTP {r.status_code}\n"
        f"response: {r.text[:120]}",
    )

    # ----------------------------------------------------------------- C2
    # Claim: pages send 'Authorization: Bearer null'; cookie-auth app rejects
    counts = {
        f: (ROOT / "templates" / f).read_text().count("localStorage.getItem('access_token')")
        for f in ("projects.html", "jobs.html", "history.html", "base.html", "workspaces.html")
    }
    client = TestClient(app, raise_server_exceptions=False)
    r2 = client.get("/api/workspaces/", headers={"Authorization": "Bearer null"})
    bearer_rejected = r2.status_code in (303, 401, 403)
    pattern_present = all(counts[f] >= 1 for f in ("projects.html", "jobs.html", "history.html"))
    clean_pages = counts["base.html"] == 0 and counts["workspaces.html"] == 0
    record(
        "C2 Bearer-token-from-localStorage is dead auth",
        "CONFIRMED" if (bearer_rejected and pattern_present and clean_pages) else "REFUTED",
        f"access_token reads per template: {counts}\n"
        "(docs said projects.html had 7 — exact count is 6; the 7th localStorage read\n"
        " is sidebarCollapsed at projects.html:865. Claim substance unchanged.)\n"
        f"REAL request with 'Authorization: Bearer null', no cookie -> HTTP {r2.status_code} (not 200)",
    )

    # ----------------------------------------------------------------- C3
    # Claim: GitHub import creates ProjectLibrary without workspace_id;
    # pipeline then skips graph sync.
    proj_src = (ROOT / "app/api/projects.py").read_text()
    m = re.search(r"ProjectLibrary\((.*?)\)\n", proj_src, re.S)
    ctor = m.group(1) if m else "<not found>"
    pipe_src = (ROOT / "app/services/pipeline.py").read_text()
    skip = "if workspace_id is None" in pipe_src and "Skipping graph sync" in pipe_src
    record(
        "C3 import drops workspace_id -> graph sync skipped",
        "CONFIRMED (static)" if ("workspace_id" not in ctor and skip) else "REFUTED",
        f"ProjectLibrary(...) ctor args in app/api/projects.py mention workspace_id: "
        f"{'workspace_id' in ctor}\n"
        f"pipeline.py contains silent-skip branch ('if workspace_id is None' + log): {skip}\n"
        "runtime half: your own WIP test test_no_write_when_workspace_none encodes the skip",
    )

    # ----------------------------------------------------------------- C4
    # Claim: blast-radius Cypher leg1 hardcodes distance / discards OPTIONAL
    # MATCH; leg2 uses variable `direct` after a WITH that doesn't project it.
    from app.graph.service import GraphService

    src = inspect.getsource(GraphService.query_blast_radius)
    leg1_bad = "RETURN directly_affected as project, 1 as distance" in src
    with_line = next((line for line in src.splitlines() if "WITH indirect as project" in line), "")
    where_uses_direct = "WHERE project <> direct" in src
    direct_projected = " direct" in with_line.split("WITH", 1)[-1].split("as project")[0] or "direct," in with_line
    leg2_bad = where_uses_direct and not direct_projected
    record(
        "C4 blast-radius Cypher defects",
        "CONFIRMED (static)" if (leg1_bad and leg2_bad) else "REFUTED",
        f"leg1 returns hardcoded '1 as distance' (OPTIONAL MATCH result unused in RETURN): {leg1_bad}\n"
        f"leg2 WITH projects: {with_line.strip()!r}\n"
        f"leg2 then references out-of-scope `direct` in WHERE: {where_uses_direct}\n"
        "runtime proof needs Neo4j: make neo4j-start, then plan step S2.3's test",
    )

    # ----------------------------------------------------------------- C5
    # Claim: prompts contain Jinja blocks but are rendered via str.replace,
    # so {% ... %} reaches the LLM literally. EXECUTES the real functions.
    from app.services import blast_radius as br

    tpl_txt = br._load_prompt_template()
    rendered = br._render_prompt(
        tpl_txt, package_name="requests", ecosystem="pypi", from_version="1",
        to_version="2", project_name="svc", distance=1, impact_type="direct",
        dependency_path="a -> b",
    )
    br_broken = "{%" in rendered or "{{" in rendered
    from app.services import relationship_service as rs

    rs_tpl = rs._load_prompt_template()
    rs_has_jinja_or_vars = "{%" in rs_tpl
    record(
        "C5 prompt templates corrupt at runtime",
        "CONFIRMED" if br_broken else "REFUTED",
        f"REAL br._render_prompt() output still contains Jinja syntax: {br_broken}\n"
        f"sample leftover: {[seg for seg in re.findall(r'{[{%][^}]*[}%]}', rendered)][:3]}\n"
        f"relationship template contains {{% blocks %}} pre-render: {rs_has_jinja_or_vars}",
    )

    # ----------------------------------------------------------------- C6
    # Claim (my CORRECTION of backend audit F-05): Base.metadata knows ALL
    # tables, incl. workspaces/workspace_members/analysis_tasks.
    import importlib

    importlib.import_module("app.models")  # registers all models w/o shadowing `app`
    from app.database import Base

    tables = sorted(Base.metadata.tables)
    need = {"workspaces", "workspace_members", "analysis_tasks"}
    ok = need.issubset(set(tables))
    record(
        "C6 create_all covers workspace/analysis tables (audit F-05 was wrong)",
        "CONFIRMED" if ok else "REFUTED",
        f"Base.metadata.tables = {tables}",
    )

    # ----------------------------------------------------------------- C7
    # Claim: /api/user/projects EXISTS (frontend audit said it didn't).
    paths = {getattr(rt, "path", "") for rt in app.routes}
    exists = "/api/user/projects" in paths
    record(
        "C7 history.html's endpoint exists (audit overclaimed)",
        "CONFIRMED" if exists else "REFUTED",
        f"'/api/user/projects' in real app route table: {exists}",
    )

    # ----------------------------------------------------------------- C8
    # Claim: two pytest configs exist; pytest.ini wins.
    both = (ROOT / "pytest.ini").exists() and "[tool.pytest.ini_options]" in (ROOT / "pyproject.toml").read_text()
    out = subprocess.run(
        [PY, "-m", "pytest", "tests/test_utils.py", "--collect-only", "-p", "no:cacheprovider"],
        capture_output=True, text=True, cwd=ROOT, timeout=60,
    ).stdout
    cfg_line = next((line for line in out.splitlines() if "configfile" in line), "<none>")
    record(
        "C8 dual pytest config, pytest.ini wins",
        "CONFIRMED" if (both and "pytest.ini" in cfg_line) else "REFUTED",
        f"both config blocks present: {both}\npytest reports: {cfg_line.strip()}",
    )

    # ----------------------------------------------------------------- C9
    # Claim: --assert=plain (used by make test) destroys failure detail.
    import tempfile

    tmpdir = Path(tempfile.mkdtemp())
    snippet = tmpdir / "test_assert_demo.py"
    snippet.write_text("def test_demo():\n    x = 2\n    assert x == 3\n")
    try:
        plain = subprocess.run(
            [PY, "-m", "pytest", str(snippet), "--assert=plain", "-q", "-p", "no:cacheprovider"],
            capture_output=True, text=True, cwd=ROOT, timeout=60,
        ).stdout
        rich = subprocess.run(
            [PY, "-m", "pytest", str(snippet), "-q", "-p", "no:cacheprovider"],
            capture_output=True, text=True, cwd=ROOT, timeout=60,
        ).stdout
    finally:
        snippet.unlink()
    plain_line = next((line for line in plain.splitlines() if "AssertionError" in line or "assert" in line), "")
    rich_line = next((line for line in rich.splitlines() if "assert 2 == 3" in line), "")
    record(
        "C9 --assert=plain hides expected-vs-actual",
        "CONFIRMED" if (rich_line and "2 == 3" not in plain_line) else "REFUTED",
        f"with --assert=plain : {plain_line.strip() or '<bare AssertionError, no values>'}\n"
        f"without            : {rich_line.strip()}",
    )

    # ---------------------------------------------------------------- C10
    # Claim: prod has no Neo4j configured; /health reports healthy from
    # Postgres alone.
    render_yaml = (ROOT / "render.yaml").read_text()
    cfg = (ROOT / "app/config.py").read_text()
    main_src = (ROOT / "main.py").read_text()
    no_neo_in_render = "NEO4J" not in render_yaml
    local_default = 'NEO4J_URI", "bolt://localhost:7687' in cfg.replace("'", '"')
    healthy_pg_only = '"healthy" if pg_status == "connected"' in main_src
    record(
        "C10 production graph layer dead by configuration",
        "CONFIRMED (static)" if (no_neo_in_render and local_default and healthy_pg_only) else "REFUTED",
        f"render.yaml mentions NEO4J anywhere: {not no_neo_in_render}\n"
        f"config defaults NEO4J_URI to localhost: {local_default}\n"
        f"/health 'healthy' computed from Postgres only: {healthy_pg_only}\n"
        "live half: curl -s https://dependiq.onrender.com/health | jq .neo4j",
    )

    # ---------------------------------------------------------------- C11
    # Claim: Neo4j test password duplicated across Makefile + docker-compose.
    mk = (ROOT / "Makefile").read_text().count("dependiq_test_2026")
    dc = (ROOT / "docker-compose.yml").read_text().count("dependiq_test_2026")
    record(
        "C11 hardcoded Neo4j password copies",
        "CONFIRMED" if (mk + dc) >= 4 else "REFUTED",
        f"occurrences — Makefile: {mk}, docker-compose.yml: {dc}, total {mk + dc} "
        f"(docs said '4 places'; exact occurrence count is {mk + dc})",
    )

    # ---------------------------------------------------------------- C12
    # Claim: nothing regenerates/verifies requirements.txt from uv.lock.
    mk_txt = (ROOT / "Makefile").read_text() + (ROOT / "build.sh").read_text()
    record(
        "C12 requirements.txt sync is manual",
        "CONFIRMED" if "uv export" not in mk_txt else "REFUTED",
        f"'uv export' present in Makefile/build.sh: {'uv export' in mk_txt}",
    )

    # ---------------------------------------------------------------- summary
    print("\n" + "=" * 64)
    for cid, verdict, _ in results:
        print(f"  {verdict:22s} {cid}")
    bad = [c for c, v, _ in results if v == "REFUTED"]
    print(f"\n{len(results)} claims checked, {len(bad)} refuted.")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
