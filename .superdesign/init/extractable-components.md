# Extractable components

## DashboardHeader
- Source: `frontend/src/pages/DashboardPage.tsx`
- Category: layout
- Description: blue statistics heading with back and refresh actions.
- Extractable props: title, generatedAt.
- Hardcoded: existing blue palette and icons.

## StatisticsPeriodControls
- Source: `frontend/src/pages/DashboardPage.tsx`
- Category: basic
- Description: district selector and day/week/month/all-time controls.
- Extractable props: districtId, dateFrom, dateTo, periodMode.
- Hardcoded: Russian labels and existing control styles.

## PercentageCell
- Source: proposed Dashboard table change.
- Category: basic
- Description: count-plus-percentage cell using the expanded direct or inverse traffic-light scale.
- Extractable props: numerator, denominator, percentage, direction, noDataLabel.
- Hardcoded: six approved colour bands and neutral no-data state.
