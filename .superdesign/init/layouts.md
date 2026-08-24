# Layouts

## Application shell

- Source: `frontend/src/App.tsx`
- The app renders a full-height flex column with `bg-gray-50`, lazy page routes, and an error boundary.
- Dashboard itself supplies its own blue header, period controls, tabs, and scrollable main region.

```tsx
<div className="h-full flex flex-col bg-gray-50">
  <Suspense fallback={<PageFallback />}><Routes>{/* protected routes */}</Routes></Suspense>
</div>
```
