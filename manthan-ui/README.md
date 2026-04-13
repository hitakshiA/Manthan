# manthan-ui/ — Layer 3: React Workspace

The frontend that renders Manthan's agent output as interactive dashboards, paginated reports, and KPI cards. Not a chatbot — a workspace.

## Stack

- **React 19** + **TypeScript** + **Vite**
- **Tailwind CSS 4** with OKLCH color system (warm-tinted neutrals, deep indigo accent)
- **Recharts** for SVG-based interactive charts
- **Zustand** for state management (agent phase machine)
- **Plus Jakarta Sans** typography

## Architecture

```
App.tsx
├── ActivityBar          Icon-only sidebar nav (datasets, memory, history)
├── Sidebar              Context-sensitive panel (dataset list, schema viewer)
├── MainWorkspace        The main content area, routes between 5 views:
│   ├── FirstOpen        Two-path welcome: Upload or Explore
│   ├── ExploreView      Rich dataset cards with role bars
│   ├── DatasetProfile   Full semantic layer visualization
│   ├── ReadyToQuery     Hero input + suggestion chips
│   └── ActiveWorkspace  Agent activity feed → render spec output
└── StatusBar            Connection status, active dataset, model name
```

## Key components

| Component | What it renders |
|-----------|----------------|
| `ActivityFeed` | Real-time SSE events as they stream from the agent |
| `ActivityEvent` | Polymorphic renderer for 22 event types (tool cards, thinking, HITL) |
| `RenderRouter` | Dispatches render_spec by mode → Simple / Moderate / Complex view |
| `ChartRenderer` | Recharts bar/line/scatter/pie from any agent visual format |
| `AskUserCard` | Inline HITL with option buttons + free-text input |
| `PlanApprovalCard` | Plan review with approve/reject/amend actions |
| `RoleBar` | Column role distribution bar (metrics/dimensions/temporal) |
| `DatasetProfile` | Full column table with stats, descriptions, quality bars |

## SSE event flow

```
POST /agent/query → SSE stream
  → agent-store.pushEvent() dispatches by event.type
  → AgentPhase transitions: idle → discovering → thinking → executing → done
  → ActivityFeed renders each event as it arrives
  → On "done": normalizeSpec() transforms raw agent JSON → typed RenderSpec
  → RenderRouter picks SimpleView / ModerateView / ComplexView
```

## Development

```bash
npm install
npm run dev          # Dev server at localhost:5173 (proxies API to :8000)
npm run build        # Production build to dist/
npm run typecheck    # TypeScript validation
```
