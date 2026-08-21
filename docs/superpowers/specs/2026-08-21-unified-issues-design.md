# Unified Issues Design

## Goal

Make `issues` the only operational record of a violation. New inspections must
create and manage issues directly, while checklist data remains readable only
as historical evidence.

## Scope

This design also applies the already approved statistics corrections:

- the `all_time` period starts on 2026-06-01 (MSK);
- district tables and exports show a weighted `ИТОГО` row.

## Terminology

- **Inspection** records that a site was visited.
- **Issue** records one detected violation and is the only unit assigned,
  repaired, reviewed, counted and reported.
- **Issue category** is the controlled category assigned to every issue.
- **Legacy checklist** is a historical questionnaire and its answers. It is
  not used for inspections created after this rollout.

## Data model

`issue_categories` already matches the required schema and seed data:
`Оборудование`, `Покрытие`, `Ограждения`, `МАФ`, `Санитарное состояние`,
`Безопасность`, `Документация`, `Освещение`, `Прочее`.

No replacement category table is created. `issues.category_id` stays `NOT
NULL`; all new writers must require an active category rather than silently
defaulting to `Прочее`.

The tables `checklist_templates`, `checklist_items` and `checklist_answers`,
and fields `inspections.template_id`, `issues.checklist_answer_id` remain in
the database as legacy read-only data. This rollout does not drop a table,
column, foreign key or photograph.

## New inspection flow

1. An inspector starts an inspection without loading a checklist template.
2. The inspection screen has a list of issues and an explicit “Добавить
   нарушение” action.
3. Creating an issue requires: active `category_id`, nonempty `title`, and
   criticality. Description and source photographs are optional unless a
   separate policy later requires them.
4. Source photographs attach to the issue using `target_type = 'issue'` and
   `issue_id`; general site photographs remain attached to the inspection.
5. On completion the server derives the inspection status from persisted
   issues: no issues -> `completed`; one or more noncritical issues ->
   `issues_found`; at least one critical issue -> `critical`. The client cannot
   declare an inspection green contrary to its issues.
6. Issue remediation remains the current issue state machine: `open`,
   `assigned`, `in_work`, `fixed`, `control`, `revision_needed`, `closed`.
   Source and repair photographs, due date, executor and status history stay
   attached to the same issue.

## Historical compatibility and photo migration

The migration copies references, never deletes source rows:

- a legacy `checklist_answer` photograph with exactly one linked issue is
  re-linked to that issue and marked `target_type = 'issue'`;
- a legacy checklist photograph without a linked issue remains associated with
  the inspection as an inspection photograph;
- `checklist_answer_id` remains populated on converted photographs for audit
  traceability;
- legacy inspection detail and PDF render from checklist answers only for
  inspections that have legacy answers; new inspections render from issues.

Before and after migration, counts of photographs, issues and linked legacy
answers must be recorded and equal where no intentional relink occurs.

## API and interface compatibility

- New inspection payloads no longer accept or return editable `answers`.
- `POST /issues` becomes the supported write path during an in-progress
  inspection. `category_id` is required and must reference an active category.
- The checklist management route and UI are removed from navigation and new
  writers. Legacy GET routes may remain internally available only for old
  inspection rendering until archival removal is separately approved.
- Read models return the issues of an inspection, including category and source
  photographs, so inspection summary and PDF have one source of truth.

## Reporting and statistics

All new reports count violations exclusively from `issues`:

- found: issues created within the selected MSK interval;
- closed: those issues whose current status is `closed`;
- not fixed: found minus closed;
- coverage: distinct sites with a completed inspection divided by active sites;
- elimination percentage: closed divided by found;
- zero denominator: `0%`;
- rounding: existing `ROUND_HALF_UP` helper;
- total-row percentages are calculated from total numerators and denominators,
  never averaged from district percentages.

Legacy `checklist_defects` is not presented as a separate metric in new UI or
exports. Compatibility DTOs may temporarily expose it as the same `issues`
count while callers are migrated.

## Release and safety constraints

- One forward-only Alembic migration, compatible with the current production
  head; downgrade must not delete history automatically.
- Migration must be idempotent and run with transaction-safe SQL.
- Run migration and application tests against a database containing both old
  checklist inspections and new direct-issue inspections.
- Preserve permission checks: inspectors may change only their own inspections;
  reviewers remain district-scoped; self-review remains forbidden.
- Existing reports/PDFs for historical inspections must remain readable after
  deployment.
