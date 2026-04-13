# api/ — FastAPI HTTP Endpoints

13 routers exposing the full Manthan API surface. All mounted in `src/main.py`.

## Routers

| Router | Prefix | Key endpoints |
|--------|--------|---------------|
| `health` | `/health` | Liveness probe |
| `datasets` | `/datasets` | Upload, list, delete, schema, context, output artifacts |
| `tools` | `/tools` | SQL execution, Python sandbox, tool manifest |
| `clarification` | `/clarification` | Interactive column classification questions |
| `status` | `/datasets/{id}` | Ingestion progress (REST + WebSocket) |
| `memory` | `/memory` | Cross-session key-value store (CRUD + search) |
| `agent_tasks` | `/tasks` | Per-session agent work tracking |
| `ask_user` | `/ask_user` | Human-in-the-loop questions (post + wait + answer) |
| `plans` | `/plans` | Plan lifecycle (create → submit → approve/reject/amend) |
| `subagents` | `/subagents` | Isolated parallel analysis workspaces |
| `tool_discovery` | `/tools/list` | Full tool manifest for agent self-discovery |
| `agent` | `/agent` | Query endpoints: SSE stream + synchronous |

## Key patterns

- **State injection**: All handlers use `StateDep = Annotated[AppState, Depends(get_state)]`
- **Rate limiting**: Applied via `@limiter.limit()` (slowapi)
- **Long-polling**: `/ask_user/{id}/wait` and `/plans/{id}/wait` block until user responds
- **SSE streaming**: `/agent/query` returns `text/event-stream` with 22 event types
- **SPA serving**: `/` serves the React frontend from `manthan-ui/dist/` if it exists
