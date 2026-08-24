# Штаб: качество обходов и устранение замечаний — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Дать штабу две честные периодные таблицы: качество обходов и устранение замечаний с процентами, которые используют сопоставимые числитель и знаменатель.

**Architecture:** `StatisticsService.dashboard()` расширяет районный контракт когортным результатом замечаний и снимком остатка на конец периода. React-экран, Excel и PPTX рендерят один и тот же контракт: поток — счётчики, процент результата — когорта периода, процент остатка — снимок на конец периода.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, React, TypeScript, Vitest, openpyxl, python-pptx.

**Spec:** `docs/superpowers/specs/2026-08-24-shtab-remediation-percentages-design.md`

## Global Constraints

- Границы всех периодов берутся только из `StatisticsFilter` / `Europe/Moscow`; подписи — `МСК (UTC+3)`.
- Не использовать `issues_closed_events / issues_found` как процент: это разные когорты.
- `issues_cohort_closed_as_of / issues_found` — прямой процент результата когорты периода.
- `issues_requires_work_current / issues_snapshot_total` — обратный процент остатка на конец периода.
- Нулевой знаменатель отдаёт `null` и рендерится нейтральным `—`, не красным 0%.
- «ИТОГО» считает проценты по общим числителю и знаменателю.
- Существующие потоковые и snapshot-счётчики сохраняются; production-данные и миграции не меняются.

---

### Task 1: Контракт когортного результата и остатка

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/services/statistics/service.py`
- Test: `backend/tests/test_stats_v2.py`

**Interfaces:**
- Produces `StatsDistrictRow.issues_cohort_closed_as_of: int`, `issues_cohort_closed_pct: int | None`, `issues_snapshot_total: int`, `issues_requires_work_pct: int | None`.
- Consumed by React, Excel and PPTX in Tasks 2–3.

- [ ] **Step 1: Write failing period-isolation tests**

```python
assert july_row["issues_found"] == 2
assert july_row["issues_cohort_closed_as_of"] == 1
assert july_row["issues_cohort_closed_pct"] == 50
assert july_row["issues_snapshot_total"] == 2
assert july_row["issues_requires_work_pct"] == 50
assert empty_row["issues_cohort_closed_pct"] is None
assert empty_row["issues_requires_work_pct"] is None
```

Use one July-created issue closed before 31 July, one closed in August, and an August-created issue. Query July and prove that only the first issue is closed as of July end and the August issue is absent from July snapshot.

- [ ] **Step 2: Verify red**

Run: `cd backend && pytest tests/test_stats_v2.py -k 'period_end_issue_snapshot or cohort' -v`

Expected: response lacks the four new contract fields.

- [ ] **Step 3: Implement rank-one snapshot aggregation**

In `StatisticsService.dashboard()`, reuse `latest_issue_status` joined at rank one. Add a cohort aggregation with `Issue.created_at >= f.start_utc` and `< f.end_utc`; count status `closed` as of the selected end. Add `snapshot_total` for issues created `< f.end_utc`. Derive nullable percentages with `percent()` only when their denominators are positive. Exclude the two new percentage fields from `totals_values` and calculate totals from summed numerator/denominator.

- [ ] **Step 4: Verify green**

Run: `cd backend && pytest tests/test_stats_v2.py -k 'period_end_issue_snapshot or cohort' -v`

Expected: PASS with July/August isolation and no-denominator behaviour.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas.py backend/app/services/statistics/service.py backend/tests/test_stats_v2.py
git commit -m "feat: add remediation cohort percentages"
```

### Task 2: Две таблицы штаба в интерфейсе

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/statistics.ts`
- Test: `frontend/src/lib/statistics.test.ts`
- Modify: `frontend/src/pages/DashboardPage.tsx`

**Interfaces:**
- Consumes the four Task 1 fields in `StatsDistrictRow`.
- Produces `remediationMetricLabel(numerator, denominator, percentage)` for neutral or `X из Y · N%` cells.

- [ ] **Step 1: Write failing label tests**

```ts
expect(remediationMetricLabel(5, 10, 50)).toBe('5 из 10 · 50%')
expect(remediationMetricLabel(0, 0, null)).toBe('—')
```

- [ ] **Step 2: Verify red**

Run: `cd frontend && npm test -- statistics.test.ts`

Expected: FAIL because `remediationMetricLabel` is not exported.

- [ ] **Step 3: Implement neutral metric helper and headquarters remediation table**

Add the helper in `statistics.ts`. Add a `ShtabRemediationTable` below `DistrictTable` in `Shtab`, with grouped headers exactly: `Поток за период`, `Результат по замечаниям периода`, `Состояние на конец периода`. Render `Устранено` using direct `qualityColor`; render `Доля требующих устранения` using inverse `qualityColor`; use slate-neutral cells and `title="Нет замечаний для расчёта"` for `null`. Retain `RemediationTable` but add the same two percentage columns so the tab and headquarters do not diverge. Explain the denominators and `МСК (UTC+3)` above each table.

- [ ] **Step 4: Verify green**

Run: `cd frontend && npm test -- statistics.test.ts && npm run lint && npm run build`

Expected: PASS, no lint errors, successful production build.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/lib/statistics.ts frontend/src/lib/statistics.test.ts frontend/src/pages/DashboardPage.tsx
git commit -m "feat: show remediation percentages in headquarters"
```

### Task 3: Excel, PPTX and operating documentation

**Files:**
- Modify: `backend/app/routers/reports.py`
- Modify: `backend/app/services/statistics/pptx.py`
- Modify: `backend/tests/test_stats_v2.py`
- Modify: `docs/STATS_MODEL_V2.md`

**Interfaces:**
- Consumes all Task 1 fields; no new API fields.
- Produces Excel/PPTX representations matching the two-table headquarters contract.

- [ ] **Step 1: Write failing export assertions**

```python
assert "Устранено из выявленных" in worksheet_headers
assert "Доля требующих устранения" in worksheet_headers
assert "Устранено из выявленных" in first_slide_text
assert "Доля требующих устранения" in second_slide_text
```

- [ ] **Step 2: Verify red**

Run: `cd backend && pytest tests/test_stats_v2.py -k 'stats_contract_and_pptx' -v`

Expected: FAIL because the exported representations lack the new result and backlog percentage labels.

- [ ] **Step 3: Implement parity**

In Excel add labelled columns after the remediation raw counts, use the direct/reverse six-band fill functions and neutral slate fill for `None`. In PPTX make slide 1 quality-only and slide 2 remediation-only; on slide 2 include the three grouped sections and `X из Y · N%` fields. Update `STATS_MODEL_V2.md` to name the two new denominator contracts and prohibit mixing events with cohort percent.

- [ ] **Step 4: Verify green**

Run: `cd backend && pytest tests/test_stats_v2.py -v`

Expected: PASS, including XLSX/PPTX structural checks.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/reports.py backend/app/services/statistics/pptx.py backend/tests/test_stats_v2.py docs/STATS_MODEL_V2.md
git commit -m "feat: align remediation exports with headquarters"
```

### Task 4: Release verification

**Files:**
- Modify: `docs/superpowers/plans/2026-08-24-shtab-remediation-percentages.md`

- [ ] **Step 1: Run complete backend suite**

Run: `cd backend && pytest -v` with `TEST_DATABASE_URL` pointing at the isolated local PostGIS database.

- [ ] **Step 2: Run complete frontend suite**

Run: `cd frontend && npm test -- --run && npm run lint && npm run build && npm audit --omit=dev --audit-level=high`

- [ ] **Step 3: Review commit range and update plan**

Run: `git diff --check origin/main...HEAD` and check that the plan has all completed steps marked `[x]` only after their tests are green.

- [ ] **Step 4: Commit verification record**

```bash
git add docs/superpowers/plans/2026-08-24-shtab-remediation-percentages.md
git commit -m "docs: verify headquarters remediation release"
```
