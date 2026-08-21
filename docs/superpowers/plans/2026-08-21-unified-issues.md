# Unified Issues Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make issues the only operational violation record, preserve legacy checklist history, and align all-time and total-row statistics.

**Architecture:** New inspections use the existing `issues` table and category reference directly. Checklist tables remain read-only historical data; a forward-only migration relinks old source photographs to their issues without deleting evidence. Statistics and exports use issue aggregates and weighted total percentages.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic/PostgreSQL, React/TypeScript, TanStack Query, pytest, Vitest.

**Spec:** `docs/superpowers/specs/2026-08-21-unified-issues-design.md`

## Global Constraints

- Preserve all checklist rows and old photographs; no destructive migration.
- Require an active issue category for every new issue.
- Derive a completed inspection status on the server from persisted issues.
- Use `ROUND_HALF_UP` and zero-denominator `0%` for every percentage.
- Start `all_time` on 2026-06-01 in Moscow time.
- Preserve role, district-scope and self-review protections.

---

### Task 1: Lock down period and weighted total contracts

**Files:**
- Modify: `backend/tests/test_stats_v2.py`
- Modify: `frontend/src/lib/statistics.test.ts`
- Modify: `backend/app/services/statistics/filters.py`
- Modify: `frontend/src/pages/DashboardPage.tsx`

**Interfaces:**
- Produces: `ALL_TIME_START == date(2026, 6, 1)` and a visible `ИТОГО` district row.

- [ ] **Step 1: Write failing backend contract tests**

```python
assert build_filter(user, None, None, None, all_time=True).date_from == date(2026, 6, 1)
assert payload["totals"]["coverage_pct"] == percent(3, 4)
assert payload["totals"]["coverage_pct"] != round((100 + 50) / 2)
```

- [ ] **Step 2: Run the targeted test to verify it fails**

Run: `pytest -q tests/test_stats_v2.py -k all_time_or_totals`

- [ ] **Step 3: Write failing frontend test**

```ts
expect(screen.getByText('ИТОГО')).toBeInTheDocument()
expect(screen.getByText('75%')).toBeInTheDocument()
```

- [ ] **Step 4: Change the period constant and render `dashboard.totals` after district rows**

Use the aggregate returned by the API. Do not sum or average values in React.

- [ ] **Step 5: Run targeted backend and frontend tests**

Run: `pytest -q tests/test_stats_v2.py` and `npm test -- --run src/lib/statistics.test.ts`

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/statistics/filters.py backend/tests/test_stats_v2.py frontend/src/pages/DashboardPage.tsx frontend/src/lib/statistics.test.ts
git commit -m "fix: align all-time period and dashboard total"
```

### Task 2: Add direct-issue inspection contracts

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/routers/issues.py`
- Modify: `backend/app/routers/inspections.py`
- Create: `backend/tests/test_direct_issue_inspections.py`

**Interfaces:**
- Consumes: `IssueCreate(inspection_id, category_id, title, criticality)`.
- Produces: category-validated issue creation and server-derived inspection completion status.

- [ ] **Step 1: Write failing API tests**

```python
missing_category = await client.post('/api/v1/issues/', json={
    'inspection_id': inspection_id, 'title': 'Трещина', 'criticality': 'medium'
}, headers=inspector_headers)
assert missing_category.status_code == 422

await create_issue(inspection_id, category_id, 'Трещина')
completed = await client.patch(f'/api/v1/inspections/{inspection_id}', json={'status': 'completed'}, headers=inspector_headers)
assert completed.json()['status'] == 'issues_found'
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest -q tests/test_direct_issue_inspections.py`

- [ ] **Step 3: Require active categories in `IssueCreate` and reject inactive IDs**

Remove the implicit `Прочее` fallback from the create writer; return validation errors for omitted, unknown or inactive categories.

- [ ] **Step 4: Derive final inspection state in the inspection router**

On an owner completion request, count persisted issues for the inspection. Set `critical` if one has criticality `critical`, `issues_found` if any exist, otherwise `completed`.

- [ ] **Step 5: Re-run direct-issue and review-workflow tests**

Run: `pytest -q tests/test_direct_issue_inspections.py tests/test_review_workflow_integrity.py`

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/issues.py backend/app/routers/inspections.py backend/tests/test_direct_issue_inspections.py
git commit -m "feat: make direct issues drive inspection outcome"
```

### Task 3: Preserve and relink historical source photos

**Files:**
- Create: `backend/alembic/versions/<revision>_preserve_legacy_checklist_history.py`
- Modify: `backend/app/models.py`
- Modify: `backend/app/routers/inspections.py`
- Modify: `backend/app/routers/pdf_report.py`
- Create: `backend/tests/test_legacy_checklist_history.py`

**Interfaces:**
- Produces: direct issue photo uploads and read-only rendering for legacy inspections.

- [ ] **Step 1: Write a migration/API regression test**

```python
assert migrated_defect_photo.issue_id == linked_issue.id
assert migrated_defect_photo.target_type == 'issue'
assert migrated_defect_photo.checklist_answer_id == legacy_answer.id
assert general_legacy_photo.issue_id is None
assert general_legacy_photo.target_type == 'inspection'
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest -q tests/test_legacy_checklist_history.py`

- [ ] **Step 3: Write one forward-only Alembic migration**

Update photographs having `checklist_answer_id` and a linked `issues.checklist_answer_id` to use that issue. Update remaining checklist-answer photographs to inspection photos. Preserve all source IDs and use conditional SQL so reruns are harmless.

- [ ] **Step 4: Make photo read paths use issue photos for new inspections**

Do not accept `checklist_answer_id` from new inspection UI. For historical inspections, retain the old answer/photo renderer; for direct-issue inspections, render issue cards and their photos.

- [ ] **Step 5: Run migration and rendering tests**

Run: `alembic upgrade head` followed by `pytest -q tests/test_legacy_checklist_history.py tests/test_direct_issue_inspections.py`

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions backend/app/models.py backend/app/routers/inspections.py backend/app/routers/pdf_report.py backend/tests/test_legacy_checklist_history.py
git commit -m "feat: preserve legacy checklist evidence"
```

### Task 4: Replace the new-inspection checklist interface

**Files:**
- Modify: `frontend/src/pages/InspectionPage.tsx`
- Modify: `frontend/src/pages/SummaryPage.tsx`
- Modify: `frontend/src/pages/AdminPanelPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/types/index.ts`
- Create: `frontend/src/pages/InspectionPage.test.tsx`

**Interfaces:**
- Consumes: issue category list, inspection issue list and direct issue/photo APIs.
- Produces: issue-first editing for new inspections and read-only checklist history for old ones.

- [ ] **Step 1: Write a failing component test**

```tsx
expect(screen.getByText('Добавить нарушение')).toBeInTheDocument()
expect(screen.queryByText('✓ ОК')).not.toBeInTheDocument()
await user.selectOptions(screen.getByLabelText('Категория'), equipmentCategoryId)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npm test -- --run src/pages/InspectionPage.test.tsx`

- [ ] **Step 3: Build the direct-issue editor and issue photo flow**

The category selector is required. Existing issues list category, description, criticality and source photos. General inspection photos remain available.

- [ ] **Step 4: Gate legacy rendering on existing checklist answers**

Old inspections render their checklist read-only; new inspections do not fetch templates or expose editable answers. Remove checklist administration from navigation, not historical route resolution.

- [ ] **Step 5: Run component and frontend regression tests**

Run: `npm test -- --run src/pages/InspectionPage.test.tsx` then `npm test -- --run`

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages frontend/src/App.tsx frontend/src/lib/api.ts frontend/src/types/index.ts
git commit -m "feat: replace new inspection checklist with issues"
```

### Task 5: Make reports issue-only and verify the release path

**Files:**
- Modify: `backend/app/routers/reports.py`
- Modify: `backend/app/services/statistics/service.py`
- Modify: `backend/app/services/statistics/pptx.py`
- Modify: `backend/tests/test_reports_export_overview.py`
- Modify: `backend/tests/test_reports_export_charts.py`
- Modify: `docs/STATS_MODEL_V2.md`

**Interfaces:**
- Produces: reports and category charts derived exclusively from `Issue.category_id` and the central statistics service.

- [ ] **Step 1: Write failing report tests**

```python
assert 'Найдено дефектов по чек-листу' not in overview_labels
assert category_chart_rows == [('Оборудование', 2), ('Покрытие', 1)]
assert total_row['issues_closed_pct'] == percent(total_row['issues_closed'], total_row['issues_found'])
```

- [ ] **Step 2: Run report tests to verify failure**

Run: `pytest -q tests/test_reports_export_overview.py tests/test_reports_export_charts.py`

- [ ] **Step 3: Replace checklist aggregate queries**

Use `Issue.category_id` and category names from `IssueCategory`. Rename user-facing labels to “Нарушения”; keep no separate checklist-defect number.

- [ ] **Step 4: Verify the complete backend and frontend suite**

Run: `pytest -q`; `npm test -- --run`; `npm run lint`; `npm run build`; `npm audit --omit=dev --json`.

- [ ] **Step 5: Verify migration and deployment instructions**

Run: `alembic upgrade head` on a restored production-like backup, inspect counts before/after, then run the same tests. Document the exact production command in `deploy/README.md`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/reports.py backend/app/services/statistics backend/tests docs/STATS_MODEL_V2.md deploy/README.md
git commit -m "refactor: report unified issues"
```
