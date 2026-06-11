# DependIQ — Claude Code Execution Runbook

**Contract:** One step per session. One step = one commit. Every step has a verification battery — unit (U), integration (I), functional (F), manual (M) — and the step is NOT done until every listed command has been run and its REAL output pasted into the conversation. "The code looks correct" is a critical failure. A red result means STOP and report; it never means improvise.

**How to use:** paste the Session Preamble below into Claude Code, replacing N with the step number. The index table is the map; the Step Details sections below it are the law. On any conflict, Step Details win.

---

## Session Preamble (paste this to start every Claude Code session)

```
Read RUNBOOK.md and CLAUDE.md and .claude/memory/MEMORY.md in full.
Execute ONLY Step N of RUNBOOK.md. Scope is the step's file whitelist —
if you believe another file must change, STOP and ask first.
Before any change: run the step's BASELINE commands and paste raw output.
After the change: run the step's VERIFY commands and paste raw output.
If any verify command does not match its expected result: STOP, report,
revert your working changes. Do not weaken a test, do not edit guard
files, do not add skips/xfails/|| true, do not push.
End by printing: the one-commit diffstat, and the SHOW step for Sairam.
```

---

## Standing rules (violating any of these = critical failure)

1. **Guard files are read-only** except where a step explicitly says to update a sentinel: `tests/auth/test_auth_invariants.py`, `tests/test_template_contracts.py`, `scripts/verify_claims.py`, `scripts/auth_check.sh`. If a guard fails, the CODE is wrong.
2. **Never** add `pytest.ini`, `--assert=plain`, `--disable-warnings`, `|| true`, `2>/dev/null` on critical paths, `generateValue:` in render.yaml, or a second pytest config block.
3. **Never** run `git push` unless the step says so AND `make test` is fully green (0 failed, 0 errors) locally. Never `--force`. Never rewrite history older than the current step's commit.
4. **Never** run `DROP`, `db-reset`, `delete_*` against any database without Sairam typing the confirmation himself. **Never** point tests at an `*.databases.neo4j.io` URI — tests use local Docker Neo4j only.
5. **Never** edit `.env`. Never print its values. `.env.example` is the editable documentation twin.
6. Commit messages: `Sx.y: <what>` + 2-5 lines including the RED and GREEN evidence one-liners.
7. Baseline truth (verified 2026-06-10 on agent sandbox, no Neo4j/Postgres services): suite = **507 passed + 9 failed/10 errors, ALL from ConnectionRefused 127.0.0.1:7687**. On Sairam's machine under `make test` (Neo4j auto-started): expected **fully green**. Any other failure signature = regression you introduced.

---

## Index

| # | Action Item | Verification (Unit + Integration + Functional + Manual) — PROVE IT WORKS |
|---|---|---|
| 0 | **GATE: machine sanity.** No code changes. | U+I: `make test` → 0 failed. F: `make auth-check` → 5/5 PASS; `.venv/bin/python scripts/verify_claims.py` → `12 claims checked, 0 refuted`, exit 0. M: create workspace in browser; /projects, /jobs, /history load data. |
| 1 | Push the 21 local commits (HUMAN decision, after Gate 0). | F: `git rev-list --count origin/main..main` → 0 after push; `make render ARGS='logs ... --limit 20 --confirm'` → no startup errors. F: `make auth-check BASE_URL=https://dependiq.onrender.com` → 5/5. M: log in on prod. |
| 2 | S0.4 — real-Neo4j test fixture (`graph_integration` marker). | U: `pytest tests/graph_integration -v` → roundtrip test PASSED against real bolt. I: `make test` green, new test included. F: `pytest --markers \| grep graph_integration` → registered. |
| 3 | S2.3 — failing blast-radius traversal test (xfail strict). PROVES the Cypher bug on real Neo4j. | I: `pytest tests/graph_integration/test_blast_radius_traversal.py -v` → **XFAIL** (paste reason). I: `make test` still green. M: none. |
| 4 | S2.4 — fix `query_blast_radius` Cypher; flip Step 3 test to pass. | I: same test → **PASSED**; `make test` fully green. F: seed script (in step details) prints indirect projects with correct distances. M: blast radius on real workspace shows >0 indirect. |
| 5 | S2.5 — Neo4j constraints/indexes at startup (idempotent). | I: new `graph_integration` test asserts `SHOW CONSTRAINTS` ≥ 2. I: `make run` twice → no errors (idempotent). M: `cypher-shell "SHOW CONSTRAINTS"` → rows pasted. |
| 6 | S2.2 — `workspace_id` flows through GitHub import → graph sync runs. | U: new `test_import_sets_workspace_id` green. I: `make test` green. F: import a repo → `psql` row shows UUID not NULL; server log shows graph sync ran (paste both). M: blast radius non-empty for that project. |
| 7 | S2.6 — prompt templates rendered with Jinja2 (kill str.replace). | U: new test: rendered output contains no `{%`/`{{` for BOTH templates. I: `make test` green. F: `verify_claims.py` C5 flipped to sentinel in same commit → still `0 refuted`, exit 0. M: rendered prompt printed, reads as English. |
| 8 | S3.1 — split external-network tests out of `make test`. | I: `make test` green offline (Wi-Fi off — M). I: `make test-integration` runs the npm/PyPI tests. F: `grep -n 'not integration' Makefile` pasted. |
| 9 | S3.2 — GitHub Actions CI (adapt YAML in docs/team/07 §7) + branch protection. | F: deliberately-broken test on a branch → red X on PR (paste link/screenshot — M); revert → green check. F: CI run shows Neo4j service container + `make test` + `verify_claims.py`. |
| 10 | S3.3 — `make smoke` (auth-check vs prod + log check). | F: `make smoke` → 5/5 PASS against prod, exit 0 (paste). M: run it after any deploy. |
| 11 | S4.9b — prod hardening: startup fails loudly on default Neo4j creds in production; `/health` overall status includes Neo4j. | U: new test — `ENVIRONMENT=production` + default password → startup raises with clear message. U: dev mode unaffected. I: `make test` green; `make run` locally fine. F: after deploy, `curl prod/health` → overall reflects neo4j (paste JSON). F: flip verify_claims C10 same commit. |
| 12 | Aura prod hookup (HUMAN creates instance; agent does repo/API side). | F: `NEO4J_URI=neo4j+s://… make neo4j-check` → `OK : connected` (paste). F: 3 × Render API PUT env-var calls → 200s. F: `curl prod/health` → neo4j connected. M: console shows instance in DependIQ project. Cost: free slot if unused, else Professional **$0.09/GB-hr ≈ $66/mo @ 1 GB**. |
| 13 | S4.3+S4.4 — Makefile rewrite (docs/team/09 target file) + Neo4j password single-source. | F: `make -n test/run/migrate` before vs after → identical underlying commands (paste diff). F: every target executed once, output pasted. F: `grep -rc dependiq_test_2026 Makefile docker-compose.yml` → exactly 1 occurrence. M: `make help` renders grouped, generated. |
| 14 | S4.5 — `make lock` + `check-lock` gate in CI. | F: add a dep to pyproject WITHOUT exporting → `make check-lock` exits 1 with instruction (paste); after `make lock` → passes. I: CI job includes check-lock. |
| 15 | S4.6 — retire legacy root files (`prompt_templates.py`, `test_prompt_templates.py`, `prompts/`). **REQUIRES Sairam's explicit sign-off — deletions.** | F: `grep -rn "prompt_templates\|prompts/" app/ main.py` → no imports (paste BEFORE deleting; if hits, step becomes migration, stop and report). I: `make test` green with Makefile no longer referencing the legacy test file. M: `ls *.py` → `main.py` only. |

---

## Step Details

### Step 0 — GATE: machine sanity (no changes)
**Whitelist:** none. Read-only.
**Commands:** `make test` · `make run` then `make auth-check` in second shell · `.venv/bin/python scripts/verify_claims.py`
**Expected:** test fully green (the 19 graph tests MUST pass here — first time verified anywhere with live Neo4j); auth-check `5/5`; verify_claims `12 checked, 0 refuted`.
**If the 19 graph tests fail here:** the WIP snapshot (`ed6610d`) has a real bug. STOP. Report the exact failure. Do not patch around it.

### Step 2 — S0.4 fixture
**Whitelist:** `tests/graph_integration/` (new), `pyproject.toml` (markers list only).
Fixture connects to `bolt://localhost:7687` with creds from env (same resolution as app Config); creates nodes under a `workspace_id` of `test-{uuid4}`; teardown deletes ONLY that workspace's nodes (`MATCH (n {workspace_id: $ws}) DETACH DELETE n`). One roundtrip test: write project node → read it back.
**Forbidden:** touching `app/`, global `DETACH DELETE` without workspace filter.

### Step 3 — S2.3 xfail test
**Whitelist:** `tests/graph_integration/test_blast_radius_traversal.py` (new).
Seed: `lib-core` DEPENDS_ON `requests(pypi)`; `service-a` RELATES_TO→ `lib-core`; `service-b` RELATES_TO→ `service-a` (all same test workspace). Call real `GraphService.query_blast_radius`. Assert service-a (distance 2-ish) and service-b appear as indirect. Mark `@pytest.mark.xfail(strict=True, reason="leg1 returns hardcoded distance/drops OPTIONAL MATCH; leg2 references out-of-scope `direct` after WITH — app/graph/service.py:197-213")`.
**Expected now:** XFAIL. **Forbidden:** changing `app/graph/service.py` in this step.

### Step 4 — S2.4 Cypher fix
**Whitelist:** `app/graph/service.py` (the one query), Step 3 test file (remove xfail only).
Requirements for the new query: direct hits via `DEPENDS_ON`; indirect via variable-length `RELATES_TO` with bounded depth (keep `*1..5`); `workspace_id` filter on EVERY node pattern; dedupe to min distance per project; deterministic ordering. No other method touched.
**Verify extras (F):** one-off seed script run via `uv run python - <<EOF` printing the result dict for the Step 3 topology — paste output showing both indirect projects.

### Step 6 — S2.2 import workspace_id
**Whitelist:** `app/api/projects.py` (import endpoint), the import-side template wiring for passing `workspace_id`, one new test file.
**Baseline (RED, paste first):** import → `psql $DATABASE_URL -c "SELECT project_name, workspace_id FROM project_library ORDER BY created_at DESC LIMIT 1"` → NULL; log line `Skipping graph sync`.
**After (GREEN):** same query → UUID; log shows sync ran. Update `verify_claims.py` C3 → sentinel in same commit; rerun → 0 refuted.

### Step 7 — S2.6 Jinja2 rendering
**Whitelist:** `app/services/blast_radius.py` (`_render_prompt`), `app/services/relationship_service.py` (`_render_prompt`), new unit test file, `scripts/verify_claims.py` C5 sentinel flip.
Use `jinja2.Template` (already a dependency — add NOTHING to pyproject). `autoescape=False` is correct here (LLM prompt, not HTML) — leave a comment saying so.

### Step 9 — S3.2 CI
**Whitelist:** `.github/workflows/test.yml` (new).
Must include: Postgres + Neo4j service containers, uv with cache, `make test` equivalent incl. `graph_integration`, `-m "not integration"`, `ruff check .`, `scripts/verify_claims.py`. Secrets: NONE required (tests use sqlite + service containers; if a test demands a real secret, that test is wrong — report it).

### Step 11 — S4.9b prod hardening
**Whitelist:** `app/config.py` (or startup validation in `main.py`), `main.py` `/health`, one new test file, `verify_claims.py` C10 flip.
Behavior: `ENVIRONMENT != development` AND (`NEO4J_PASSWORD == "password"` OR unset) → raise at startup with message naming the three env vars. `/health`: overall `"healthy"` only if Postgres AND Neo4j connected; degraded state names which one failed.

### Step 12 — Aura hookup (split human/agent)
**Human:** create instance in the existing (empty) DependIQ Aura project; download credentials (password shown once).
**Agent:** `make neo4j-check` with the Aura URI (paste OK); Render API:
```
export RENDER_API_KEY=$(grep -o 'rnd_[A-Za-z0-9]*' ~/.render/cli.yaml | head -1)
curl -s -X PUT "https://api.render.com/v1/services/$SRV/env-vars/NEO4J_URI" \
  -H "Authorization: Bearer $RENDER_API_KEY" -H "Content-Type: application/json" \
  -d '{"value":"neo4j+s://XXXX.databases.neo4j.io"}'
# repeat: NEO4J_USER, NEO4J_PASSWORD (values typed by HUMAN, never logged)
```
**Never** paste the password into chat or commit it anywhere.

### Step 13 — Makefile rewrite
The complete target file is in `docs/team/09_infrastructure_plan.md` ("The target Makefile"). Behavior-preserving except flags already changed by earlier steps. Parity proof method: capture `make -n <target>` for test/run/migrate/lint before and after; paste the diff (expected: cosmetic only).

### Step 15 — legacy retirement
**Gate:** Sairam types "yes, delete the legacy prompt files" in the session. Without that exact confirmation: do not delete; report and stop.

---

## Failure protocol

Any verify mismatch → paste the full failing output, `git checkout -- .` (working changes only — never reset committed history), state in one line what you believe broke, STOP. Sairam decides the next move. An honest red report is success; a fake green is the firing offense.
