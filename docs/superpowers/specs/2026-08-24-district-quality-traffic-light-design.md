# District quality percentage traffic light

## Goal

Report a district's inspection quality honestly for every selected period. A district whose latest inspection of every active site is clean must be green, even if legacy issue cards still need reconciliation.

## Evidence

On 2026-08-24 production data for `Молжаниновский` showed 94 active sites, 94 sites with a completed latest inspection, and 94 clean latest inspections. It also had 30 historical issue cards in work states. The former is site quality; the latter is workflow debt and must not colour a district red.

## Period semantics

- The UI, API payload, Excel, and PPTX explicitly label the timezone as `МСК (UTC+3)`. Calendar boundaries use `Europe/Moscow`, never the browser's local timezone or UTC.
- `day`, `week`, `month`, and custom ranges include DONE inspections whose `completed_at` is inside the selected MSK interval; `all_time` includes all DONE inspections.
- A site's result is its latest DONE inspection inside the selected interval. A later inspection cannot rewrite an earlier interval.
- `coverage_pct` remains distinct inspected active sites divided by active sites now. The project has no site-activity history, so this is current-inventory coverage rather than historical SLA.
- `clean_sites_pct` is clean latest-inspected sites divided by distinct inspected sites. `defect_sites_pct` is the inverse.
- If there are no completed inspections, both quality percentages are `null`, never `0`.

## Expanded percentage traffic light

For direct good metrics (`coverage_pct`, `clean_sites_pct`): 0–19 red `#E06666`, 20–39 coral `#F4B183`, 40–59 orange `#F9CB9C`, 60–74 yellow `#FFD966`, 75–89 light green `#A9D18E`, 90–100 green `#63BE7B`.

`defect_sites_pct` uses those bands in reverse, so 0% is green. Null is a neutral grey dash and the label `Нет завершённых обходов за период`.

## API contract

Add to `StatsDistrictRow`:

```
sites_latest_clean: int
sites_latest_with_defects: int
clean_sites_pct: int | null
defect_sites_pct: int | null
```

Totals sum the site counts and calculate percentages from them. The invariant is `sites_inspected = sites_latest_clean + sites_latest_with_defects`. Existing inspection event counts keep their current meanings.

## UI and exports

The `Обходы` table gains `Качество площадок`: `Чистые` and `С нарушениями`, each rendered as `X из Y · N%`. The overview makes `Чистые площадки` a primary KPI.

The `Устранение` tab remains workflow reporting. Old non-final cards alongside clean latest inspections become an uncoloured `Требуют сверки` count, never a district-quality colour.

Excel and PPTX receive the same two fields, colour palette, no-data convention, and explicit period labels.

## Tests and safety

- A 94/94-clean district with 30 historical open cards yields 100% coverage, 100% clean sites, 0% defect sites, and 30 cards requiring reconciliation.
- Later inspections do not affect earlier periods.
- Empty periods yield null quality percentages and neutral UI.
- Frontend tests cover every direct and reverse palette boundary.
- No migration or production-data mutation is required.
