# Shared UI components

## ErrorBoundary

- Source: `frontend/src/components/ErrorBoundary.tsx`
- Purpose: catches unexpected rendering errors and presents a retry action.

```tsx
export class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { hasError: boolean }> {
  state = { hasError: false }
  static getDerivedStateFromError() { return { hasError: true } }
  render() { return this.state.hasError ? <div>Произошла ошибка</div> : this.props.children }
}
```

## Dashboard local primitives

`Kpi` and `ChartCard` live in `frontend/src/pages/DashboardPage.tsx`. Both use the shared `card` class and plain accessible HTML controls; preserve that pattern in the dashboard redesign.
