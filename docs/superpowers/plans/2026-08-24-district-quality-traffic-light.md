# District Quality Traffic Light Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add period-correct site-quality percentages and a six-band traffic light without allowing historical issue cards to grade a district.

**Architecture:** StatisticsService selects the latest DONE inspection per site inside the selected period, aggregates clean and defect site counts, and exposes nullable percentages. Dashboard, Excel, and PPTX render the same direct/reverse palette.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, React, TypeScript, Vitest, openpyxl, python-pptx.

**Spec:** `docs/superpowers/specs/2026-08-24-district-quality-traffic-light-design.md`

## Global Constraints

- Use existing MSK boundaries from `StatisticsFilter`.
- Label every statistics surface `МСК (UTC+3)`; do not derive calendar dates from the browser timezone.
- `null` quality percentage is no data, not 0%.
- Do not mutate issue or production data.
- Preserve existing event-based inspection and remediation metrics.

---

### Task 1: Site-quality API contract

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/services/statistics/service.py`
- Test: `backend/tests/test_stats_v2.py`

**Produces:** `sites_latest_clean`, `sites_latest_with_defects`, `clean_sites_pct: int | None`, `defect_sites_pct: int | None`.

- [x] **Step 1: Write a failing regression test**

```python
assert row['sites_inspected'] == 94
assert row['sites_latest_clean'] == 94
assert row['sites_latest_with_defects'] == 0
assert row['clean_sites_pct'] == 100
assert row['defect_sites_pct'] == 0
assert row['issues_requires_work_current'] == 30
```

- [x] **Step 2: Verify red**

Run: `cd backend && pytest tests/test_stats_v2.py -k site_quality -v`

Expected: failure because the response does not yet have the new fields.

- [x] **Step 3: Implement one latest DONE inspection per site**

Use a `row_number().over(partition_by=Inspection.site_id, order_by=(Inspection.completed_at.desc(), Inspection.created_at.desc()))` subquery filtered by `DONE_STATUSES` and the selected interval. Aggregate rank-one rows by district with the existing defect and issue EXISTS logic. Set percentages to `None` when no sites were inspected.

- [x] **Step 4: Verify green**

Run: `cd backend && pytest tests/test_stats_v2.py -v`

- [x] **Step 5: Commit**

```bash
git add backend/app/schemas.py backend/app/services/statistics/service.py backend/tests/test_stats_v2.py
git commit -m "feat: add period site quality statistics"
```

### Task 2: Six-band frontend presentation

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/statistics.ts`
- Test: `frontend/src/lib/statistics.test.ts`
- Modify: `frontend/src/pages/DashboardPage.tsx`

**Produces:** `qualityColor(value, direction)` with direct, inverse, and null states plus the `Качество площадок` table group.

- [x] **Step 1: Write failing palette tests**

```ts
expect(qualityColor(0, 'direct')).toBe('#E06666')
expect(qualityColor(90, 'direct')).toBe('#63BE7B')
expect(qualityColor(0, 'inverse')).toBe('#63BE7B')
expect(qualityColor(null, 'direct')).toBeUndefined()
```

- [x] **Step 2: Verify red**

Run: `cd frontend && npm test -- statistics.test.ts`

- [x] **Step 3: Implement the shared palette and table cells**

Add direct and inverse six-band mapping. Render `Чистые` and `С нарушениями` as `X из Y · N%`; render null as `—` with the no-data label. Do not use historical workflow-card counts to set a row colour.

- [x] **Step 4: Verify green**

Run: `cd frontend && npm test -- statistics.test.ts && npm run lint && npm run build`

- [x] **Step 5: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/lib/statistics.ts frontend/src/lib/statistics.test.ts frontend/src/pages/DashboardPage.tsx
git commit -m "feat: show district quality traffic light"
```

### Task 3: Export parity and period snapshot

**Files:**
- Modify: `backend/app/routers/reports.py`
- Modify: `backend/app/services/statistics/pptx.py`
- Modify: `backend/app/services/statistics/service.py`
- Modify: `backend/tests/test_stats_v2.py`
- Modify: `docs/STATS_MODEL_V2.md`

**Produces:** Excel/PPTX quality columns and a period-end remediation snapshot.

- [x] **Step 1: Write failing export and period-isolation assertions**

```python
assert 'Чистые площадки' in worksheet_headers
assert july_row['clean_sites_pct'] == 0
assert august_row['clean_sites_pct'] == 100
```

- [x] **Step 2: Verify red**

Run: `cd backend && pytest tests/test_stats_v2.py -k 'xlsx or pptx or period_quality' -v`

- [x] **Step 3: Implement export fields and state reconstruction**

Render quality columns using the same palette. For the remediation snapshot, include only issues created by the selected end and use each Issue's last `IssueStatusHistory.new_status` at or before that end; without history use its initial `open` state. Do not use today's Issue.status for past periods.

- [ ] **Step 4: Verify release matrix**

Run: `cd backend && pytest -v` (pending full-suite completion; focused statistics suite is green)

Run: `cd frontend && npm test && npm run lint && npm run build`

- [x] **Step 5: Review and commit**

```bash
git diff --check
git add backend/app/routers/reports.py backend/app/services/statistics/pptx.py backend/app/services/statistics/service.py backend/tests/test_stats_v2.py docs/STATS_MODEL_V2.md
git commit -m "feat: align quality exports with dashboard"
```
