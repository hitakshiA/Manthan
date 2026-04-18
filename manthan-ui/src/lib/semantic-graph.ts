import type { ColumnSchema, DatasetSummary, SchemaSummary } from "@/types/api";

// ── UML node geometry — exported for renderer + port math ──────────────
export const NODE_WIDTH = 260;
export const HEADER_HEIGHT = 58;
export const COL_ROW_HEIGHT = 24;
export const FOOTER_HEIGHT = 28;
export const MAX_COLUMNS_SHOWN = 14;

export function nodeHeight(visibleColCount: number, hasOverflow: boolean): number {
  return (
    HEADER_HEIGHT +
    visibleColCount * COL_ROW_HEIGHT +
    (hasOverflow ? COL_ROW_HEIGHT : 0) +
    FOOTER_HEIGHT
  );
}

/**
 * Derive the semantic-layer graph client-side from the schema catalog.
 *
 * Nodes are entities (one per dataset). Edges are inferred FK links:
 * for each identifier column in A whose base name matches an entity
 * slug in B, we draw A → B. This is the same heuristic
 * ``src/ingestion/relationships.py`` uses server-side for bundle
 * ingestion, reimplemented here against the already-loaded schemas so
 * the UI doesn't need a second backend round-trip.
 */

export interface GraphNode {
  id: string;                // dataset_id
  slug: string;              // entity slug (or dataset name fallback)
  name: string;              // business name
  sourceType: string;
  rowCount: number;
  metricCount: number;
  rollupCount: number;
  piiCount: number;
  schema: SchemaSummary | null;
  createdAt: string;
}

export interface GraphEdge {
  id: string;                // `${fromId}->${toId}:${via}`
  fromId: string;
  toId: string;
  via: string;               // the column on `from` that points at `to`
}

export interface GraphLayoutPos {
  x: number;
  y: number;
}

export function buildNodes(
  datasets: DatasetSummary[],
  schemas: Map<string, SchemaSummary>,
): GraphNode[] {
  // Dedupe by name, most-recent wins — same policy the lister uses.
  const seen = new Set<string>();
  const sorted = [...datasets].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );
  const unique = sorted.filter((d) => {
    if (seen.has(d.name)) return false;
    seen.add(d.name);
    return true;
  });

  return unique.map((ds) => {
    const schema = schemas.get(ds.dataset_id) ?? null;
    const entity = schema?.entity ?? null;
    return {
      id: ds.dataset_id,
      slug: entity?.slug ?? ds.name.toLowerCase().replace(/[^a-z0-9_]/g, "_"),
      name: entity?.name ?? ds.name,
      sourceType: ds.source_type,
      rowCount: ds.row_count,
      metricCount: entity?.metrics.length ?? 0,
      rollupCount: entity?.rollups.length ?? 0,
      piiCount: schema?.columns.filter((c) => c.pii).length ?? 0,
      schema,
      createdAt: ds.created_at,
    };
  });
}

/** Strip common suffixes / normalize case for FK matching. */
function normalizeName(n: string): string {
  return n
    .toLowerCase()
    .replace(/_/g, "")
    .replace(/id$|key$|number$|sku$|code$/, "")
    .trim();
}

function normalizeEntityName(n: string): string {
  return n
    .toLowerCase()
    .replace(/[^a-z0-9]/g, "")
    .replace(/s$/, ""); // naive singularize
}

const FK_SUFFIX = /(_id|_code|_key|_number|_sku|id|code|key|number|sku)$/i;

export function deriveEdges(nodes: GraphNode[]): GraphEdge[] {
  const edges: GraphEdge[] = [];
  const seen = new Set<string>();

  // Pre-compute normalized entity names for match lookups.
  const byNormName = new Map<string, GraphNode>();
  for (const n of nodes) {
    byNormName.set(normalizeEntityName(n.slug), n);
    byNormName.set(normalizeEntityName(n.name), n);
  }

  for (const from of nodes) {
    if (!from.schema) continue;
    // FK candidates = any column whose name ends with an identifier
    // suffix (``_id``/``_code``/``_key``/``_number``/``_sku``).
    // We look across roles (identifier OR dimension) because the
    // classifier often routes low-cardinality FK columns to
    // ``dimension`` — we don't want to miss the edge.
    const fkCandidates = from.schema.columns.filter((c) => {
      if (c.role === "metric" || c.role === "temporal" || c.role === "auxiliary")
        return false;
      return FK_SUFFIX.test(c.name);
    });
    for (const col of fkCandidates) {
      const base = normalizeName(col.name);
      if (!base || base.length < 3) continue;
      const target = byNormName.get(base);
      if (!target || target.id === from.id) continue;
      const key = `${from.id}->${target.id}:${col.name}`;
      if (seen.has(key)) continue;
      seen.add(key);
      edges.push({
        id: key,
        fromId: from.id,
        toId: target.id,
        via: col.name,
      });
    }
  }
  return edges;
}

/**
 * Radial layout: the hub (most connections) sits at the center, the
 * rest fan out in a ring. Deterministic given the input order, so the
 * graph doesn't jitter between renders.
 */
export function layoutNodes(
  nodes: GraphNode[],
  edges: GraphEdge[],
  width: number,
  height: number,
): Map<string, GraphLayoutPos> {
  const pos = new Map<string, GraphLayoutPos>();
  if (nodes.length === 0) return pos;

  const degree = new Map<string, number>();
  for (const n of nodes) degree.set(n.id, 0);
  for (const e of edges) {
    degree.set(e.fromId, (degree.get(e.fromId) ?? 0) + 1);
    degree.set(e.toId, (degree.get(e.toId) ?? 0) + 1);
  }

  // Hub = the single most-connected node; break ties by rowCount so
  // the biggest table dominates when there are no edges.
  const sorted = [...nodes].sort((a, b) => {
    const d = (degree.get(b.id) ?? 0) - (degree.get(a.id) ?? 0);
    if (d !== 0) return d;
    return b.rowCount - a.rowCount;
  });

  const cx = width / 2;
  const cy = height / 2;

  // Single node: center it.
  if (sorted.length === 1) {
    pos.set(sorted[0].id, { x: cx, y: cy });
    return pos;
  }

  // Two or three nodes: space them along a line / triangle.
  if (sorted.length <= 3) {
    const r = Math.min(width, height) * 0.28;
    sorted.forEach((n, i) => {
      const angle = (i / sorted.length) * Math.PI * 2 - Math.PI / 2;
      pos.set(n.id, { x: cx + Math.cos(angle) * r, y: cy + Math.sin(angle) * r });
    });
    return pos;
  }

  // Hub-and-spoke. Hub centered; rest on a ring.
  const [hub, ...rest] = sorted;
  pos.set(hub.id, { x: cx, y: cy });
  const radius = Math.min(width, height) * 0.36;
  rest.forEach((n, i) => {
    const angle = (i / rest.length) * Math.PI * 2 - Math.PI / 2;
    pos.set(n.id, {
      x: cx + Math.cos(angle) * radius,
      y: cy + Math.sin(angle) * radius,
    });
  });

  return pos;
}

/** Curved bezier path between two points, perpendicular-offset for clarity. */
export function edgePath(
  p1: GraphLayoutPos,
  p2: GraphLayoutPos,
  curvature = 0.2,
): string {
  const mx = (p1.x + p2.x) / 2;
  const my = (p1.y + p2.y) / 2;
  const dx = p2.x - p1.x;
  const dy = p2.y - p1.y;
  const len = Math.hypot(dx, dy);
  if (len === 0) return `M${p1.x},${p1.y} L${p2.x},${p2.y}`;
  const offset = len * curvature;
  const controlX = mx + (-dy / len) * offset;
  const controlY = my + (dx / len) * offset;
  return `M${p1.x},${p1.y} Q${controlX},${controlY} ${p2.x},${p2.y}`;
}

/** Horizontal S-bezier between two ports — classic UML connector. */
export function portPath(sx: number, sy: number, tx: number, ty: number): string {
  const dx = Math.max(Math.abs(tx - sx) * 0.5, 60);
  const c1x = sx + (tx >= sx ? dx : -dx);
  const c2x = tx + (tx >= sx ? -dx : dx);
  return `M${sx},${sy} C${c1x},${sy} ${c2x},${ty} ${tx},${ty}`;
}

// ── Column selection + FK tagging ─────────────────────────────────────────
//
// Columns are prioritized: identifier > metric > temporal > dimension >
// auxiliary. FK columns (those whose normalized base name matches another
// entity) are ALWAYS kept so edges always have a target port.

const FK_NAME_SUFFIX = /(_id|_code|_key|_number|_sku|id|code|key|number|sku)$/i;

export interface ColumnWithPort extends ColumnSchema {
  /** Index inside the visible columns array (for port Y calc). */
  portIndex: number;
  /** True if this column points at another entity. */
  isFK: boolean;
  /** For FK columns, the id of the entity it points to. */
  fkTargetId: string | null;
}

function rolePriority(role: string): number {
  switch (role) {
    case "identifier": return 0;
    case "metric": return 1;
    case "temporal": return 2;
    case "dimension": return 3;
    case "auxiliary": return 4;
    default: return 5;
  }
}

/**
 * Decide which columns to render inside a table node and tag FK columns
 * with their target node id.
 */
export function visibleColumns(
  node: GraphNode,
  allNodes: GraphNode[],
): { visible: ColumnWithPort[]; hiddenCount: number } {
  if (!node.schema) return { visible: [], hiddenCount: 0 };

  const cols = node.schema.columns;

  // Precompute entity lookup for FK tagging.
  const byNormName = new Map<string, GraphNode>();
  for (const n of allNodes) {
    byNormName.set(normalizeEntityName(n.slug), n);
    byNormName.set(normalizeEntityName(n.name), n);
  }

  const tagged: ColumnWithPort[] = cols.map((c) => {
    let isFK = false;
    let fkTargetId: string | null = null;
    if (
      c.role !== "metric" &&
      c.role !== "temporal" &&
      c.role !== "auxiliary" &&
      FK_NAME_SUFFIX.test(c.name)
    ) {
      const base = normalizeName(c.name);
      if (base && base.length >= 3) {
        const target = byNormName.get(base);
        if (target && target.id !== node.id) {
          isFK = true;
          fkTargetId = target.id;
        }
      }
    }
    return { ...c, portIndex: 0, isFK, fkTargetId };
  });

  // If the schema is short enough, keep all columns.
  if (tagged.length <= MAX_COLUMNS_SHOWN) {
    return {
      visible: tagged.map((c, i) => ({ ...c, portIndex: i })),
      hiddenCount: 0,
    };
  }

  // Otherwise: keep all FKs + all identifiers + fill with metrics/temporal/dim
  // up to the cap, preserving original order within each group.
  const fks = tagged.filter((c) => c.isFK);
  const rest = tagged.filter((c) => !c.isFK);
  rest.sort((a, b) => rolePriority(a.role) - rolePriority(b.role));

  const room = Math.max(0, MAX_COLUMNS_SHOWN - fks.length);
  const picked = [...fks, ...rest.slice(0, room)];

  // Restore original order so the UML card reads top-to-bottom like the
  // schema — otherwise FKs all bunch at the top.
  const keepSet = new Set(picked.map((c) => c.name));
  const ordered = tagged.filter((c) => keepSet.has(c.name));

  return {
    visible: ordered.map((c, i) => ({ ...c, portIndex: i })),
    hiddenCount: tagged.length - ordered.length,
  };
}

// ── Grid / focused layout for rectangular UML nodes ──────────────────────

export interface NodeRect extends GraphLayoutPos {
  w: number;
  h: number;
}

/**
 * Horizontal flow layout: focus node at center column, left column for
 * entities the focus references, right column for entities that reference
 * the focus. Leftover/disconnected nodes go further out.
 *
 * Returns node rectangles (top-left corner + width/height) in world coords.
 */
export function layoutUML(
  nodes: GraphNode[],
  edges: GraphEdge[],
  focusId: string | null,
  nodeSizes: Map<string, { w: number; h: number }>,
): Map<string, NodeRect> {
  const rects = new Map<string, NodeRect>();
  const sizeOf = (id: string) =>
    nodeSizes.get(id) ?? { w: NODE_WIDTH, h: HEADER_HEIGHT + FOOTER_HEIGHT };

  const COL_GAP = 120;     // horizontal gap between columns of nodes
  const ROW_GAP = 60;      // vertical gap between nodes in same column

  function stackColumn(ids: string[], xLeft: number): { yTop: number; yBottom: number } {
    let totalH = 0;
    for (const id of ids) totalH += sizeOf(id).h;
    totalH += Math.max(0, ids.length - 1) * ROW_GAP;
    let y = -totalH / 2;
    const yTop = y;
    for (const id of ids) {
      const s = sizeOf(id);
      rects.set(id, { x: xLeft, y, w: s.w, h: s.h });
      y += s.h + ROW_GAP;
    }
    return { yTop, yBottom: yTop + totalH };
  }

  if (focusId && nodes.some((n) => n.id === focusId)) {
    // Split neighbors by direction relative to focus.
    const referencedIds: string[] = []; // focus points at these (focus.col -> other)
    const referencesIds: string[] = []; // these point at focus (other.col -> focus)
    for (const e of edges) {
      if (e.fromId === focusId) referencedIds.push(e.toId);
      else if (e.toId === focusId) referencesIds.push(e.fromId);
    }
    const referenced = Array.from(new Set(referencedIds));
    const references = Array.from(new Set(referencesIds));
    const connected = new Set([focusId, ...referenced, ...references]);
    const orphans = nodes.filter((n) => !connected.has(n.id)).map((n) => n.id);

    const focusSize = sizeOf(focusId);

    // X coordinates for columns.
    const centerX = 0;
    const leftX = centerX - focusSize.w - COL_GAP;
    const rightX = centerX + focusSize.w + COL_GAP;
    // Double-left column for orphans (stuff with no edge to focus).
    const orphanX = leftX - NODE_WIDTH - COL_GAP;

    // Stack each column.
    stackColumn(references, leftX);
    rects.set(focusId, {
      x: centerX,
      y: -focusSize.h / 2,
      w: focusSize.w,
      h: focusSize.h,
    });
    stackColumn(referenced, rightX);
    if (orphans.length > 0) stackColumn(orphans, orphanX);
    return rects;
  }

  // Non-focused mode: simple grid, 2–3 columns based on node count.
  const cols = nodes.length <= 2 ? nodes.length : nodes.length <= 6 ? 2 : 3;
  // Compute column X offsets (each column is NODE_WIDTH wide).
  const colXs: number[] = [];
  for (let i = 0; i < cols; i++) {
    const x = i * (NODE_WIDTH + COL_GAP) - ((cols - 1) * (NODE_WIDTH + COL_GAP)) / 2;
    colXs.push(x);
  }
  // Distribute nodes round-robin; stack in columns.
  const bucketsX: string[][] = Array.from({ length: cols }, () => []);
  nodes.forEach((n, i) => bucketsX[i % cols].push(n.id));
  bucketsX.forEach((ids, ci) => stackColumn(ids, colXs[ci]));
  return rects;
}

/** Port location on a node rect for a given column index. */
export function portPoint(
  rect: NodeRect,
  colIndex: number,
  side: "left" | "right",
): { x: number; y: number } {
  const y = rect.y + HEADER_HEIGHT + colIndex * COL_ROW_HEIGHT + COL_ROW_HEIGHT / 2;
  const x = side === "right" ? rect.x + rect.w : rect.x;
  return { x, y };
}
