import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Maximize2, Minimize2, Minus, Plus, X } from "lucide-react";
import type { DatasetSummary } from "@/types/api";
import { useAllSchemas } from "@/hooks/use-all-schemas";
import {
  buildNodes,
  deriveEdges,
  layoutUML,
  nodeHeight,
  portPath,
  portPoint,
  visibleColumns,
  NODE_WIDTH,
  type GraphEdge,
  type NodeRect,
} from "@/lib/semantic-graph";
import { TableNode } from "@/components/datasets/TableNode";
import { cn } from "@/lib/utils";

/**
 * The semantic-layer graph — UML-style entity tables connected by
 * column-to-column FK lines with traveling pulses. Pan with right-mouse
 * drag (or space + left-drag), zoom with the wheel. Click a node to
 * open its contract. In focus mode, the focused entity is centered
 * and its 1-hop neighbors stack left/right by FK direction.
 */

const CANVAS_H_DEFAULT = 620;
const CANVAS_H_FOCUS = 560;

interface Transform {
  x: number;
  y: number;
  scale: number;
}

const MIN_SCALE = 0.35;
const MAX_SCALE = 2.2;

export function SemanticGraph({
  datasets,
  onSelect,
  search = "",
  focusId = null,
  height,
}: {
  datasets: DatasetSummary[];
  onSelect: (datasetId: string) => void;
  search?: string;
  focusId?: string | null;
  height?: number;
}) {
  const baseCanvasH = height ?? (focusId ? CANVAS_H_FOCUS : CANVAS_H_DEFAULT);
  const [fullscreen, setFullscreen] = useState(false);
  const canvasH = fullscreen ? Math.max(480, window.innerHeight - 40) : baseCanvasH;
  const ids = useMemo(() => datasets.map((d) => d.dataset_id), [datasets]);
  const { schemas } = useAllSchemas(ids);
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 900, h: canvasH });
  const [hovered, setHovered] = useState<string | null>(null);

  // Viewport transform (pan + zoom) applied to the world-group.
  const [view, setView] = useState<Transform>({ x: 0, y: 0, scale: 1 });
  const [panning, setPanning] = useState(false);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      const rect = el.getBoundingClientRect();
      setSize({ w: Math.max(360, rect.width), h: rect.height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [canvasH, fullscreen]);

  // Close fullscreen on Escape.
  useEffect(() => {
    if (!fullscreen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setFullscreen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [fullscreen]);

  // Build full graph, then narrow to focused subgraph when focusId is set.
  const fullNodes = useMemo(
    () => buildNodes(datasets, schemas),
    [datasets, schemas],
  );
  const fullEdges = useMemo(() => deriveEdges(fullNodes), [fullNodes]);

  const { nodes, edges } = useMemo(() => {
    if (!focusId) return { nodes: fullNodes, edges: fullEdges };
    const neighbors = new Set<string>([focusId]);
    for (const e of fullEdges) {
      if (e.fromId === focusId) neighbors.add(e.toId);
      if (e.toId === focusId) neighbors.add(e.fromId);
    }
    const keptNodes = fullNodes.filter((n) => neighbors.has(n.id));
    const keptEdges = fullEdges.filter(
      (e) => neighbors.has(e.fromId) && neighbors.has(e.toId),
    );
    return { nodes: keptNodes, edges: keptEdges };
  }, [fullNodes, fullEdges, focusId]);

  // Visible column set per node (decides node height + port indices).
  const nodeColumns = useMemo(() => {
    const m = new Map<string, ReturnType<typeof visibleColumns>>();
    for (const n of nodes) m.set(n.id, visibleColumns(n, nodes));
    return m;
  }, [nodes]);

  // Node sizes (used by layout + rendering).
  const nodeSizes = useMemo(() => {
    const m = new Map<string, { w: number; h: number }>();
    for (const n of nodes) {
      const c = nodeColumns.get(n.id);
      const visibleCount = c?.visible.length ?? 0;
      const hasOverflow = (c?.hiddenCount ?? 0) > 0;
      m.set(n.id, {
        w: NODE_WIDTH,
        h: nodeHeight(visibleCount, hasOverflow),
      });
    }
    return m;
  }, [nodes, nodeColumns]);

  // UML layout (world coords — node rectangles).
  const rects = useMemo(
    () => layoutUML(nodes, edges, focusId, nodeSizes),
    [nodes, edges, focusId, nodeSizes],
  );

  // Auto-fit on layout change: center the graph in the viewport with a
  // sensible initial scale. Only runs when the node-id set changes so
  // user pan/zoom isn't stomped while interacting.
  const layoutKey = useMemo(() => nodes.map((n) => n.id).join("|"), [nodes]);
  useEffect(() => {
    if (nodes.length === 0 || size.w === 0) return;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const n of nodes) {
      const r = rects.get(n.id);
      if (!r) continue;
      minX = Math.min(minX, r.x);
      minY = Math.min(minY, r.y);
      maxX = Math.max(maxX, r.x + r.w);
      maxY = Math.max(maxY, r.y + r.h);
    }
    if (!Number.isFinite(minX)) return;
    const worldW = maxX - minX;
    const worldH = maxY - minY;
    const PAD = 60;
    const scale = Math.min(
      (size.w - PAD * 2) / worldW,
      (size.h - PAD * 2) / worldH,
      1,
    );
    const s = Math.max(MIN_SCALE, Math.min(MAX_SCALE, scale));
    // Center the content: viewport coord = (world coord - minWorld) * scale + offset
    const x = (size.w - worldW * s) / 2 - minX * s;
    const y = (size.h - worldH * s) / 2 - minY * s;
    setView({ x, y, scale: s });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layoutKey, size.w, size.h]);

  const resetView = useCallback(() => {
    // Re-run auto-fit manually.
    setView((prev) => ({ ...prev, scale: 1, x: 0, y: 0 }));
    // A tick later, trigger the auto-fit effect again by toggling.
    setTimeout(() => {
      if (nodes.length === 0 || size.w === 0) return;
      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      for (const n of nodes) {
        const r = rects.get(n.id);
        if (!r) continue;
        minX = Math.min(minX, r.x);
        minY = Math.min(minY, r.y);
        maxX = Math.max(maxX, r.x + r.w);
        maxY = Math.max(maxY, r.y + r.h);
      }
      if (!Number.isFinite(minX)) return;
      const worldW = maxX - minX;
      const worldH = maxY - minY;
      const PAD = 60;
      const s = Math.max(MIN_SCALE, Math.min(MAX_SCALE,
        Math.min((size.w - PAD * 2) / worldW, (size.h - PAD * 2) / worldH, 1)
      ));
      setView({
        x: (size.w - worldW * s) / 2 - minX * s,
        y: (size.h - worldH * s) / 2 - minY * s,
        scale: s,
      });
    }, 0);
  }, [nodes, rects, size.w, size.h]);

  // ── Pan: attach window-level mousemove/up during a drag so children
  //     that stop propagation or override cursor can't break us.
  //     Right-button (2) or middle-button (1) initiates.
  const onMouseDownCanvas = (e: React.MouseEvent) => {
    if (e.button !== 2 && e.button !== 1) return;
    e.preventDefault();
    const startX = e.clientX;
    const startY = e.clientY;
    const startTx = view.x;
    const startTy = view.y;
    setPanning(true);
    const move = (ev: MouseEvent) => {
      setView((v) => ({
        ...v,
        x: startTx + (ev.clientX - startX),
        y: startTy + (ev.clientY - startY),
      }));
    };
    const up = () => {
      setPanning(false);
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  };

  // ── Zoom: React's synthetic onWheel is passive so preventDefault
  //     no-ops and the page scrolls underneath. Attach a native
  //     non-passive listener on the canvas element instead.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      const cx = e.clientX - rect.left;
      const cy = e.clientY - rect.top;
      const delta = -e.deltaY * 0.0015;
      setView((v) => {
        const nextScale = Math.max(
          MIN_SCALE,
          Math.min(MAX_SCALE, v.scale * (1 + delta)),
        );
        const k = nextScale / v.scale;
        return {
          scale: nextScale,
          x: cx - (cx - v.x) * k,
          y: cy - (cy - v.y) * k,
        };
      });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  const zoomBy = (mult: number) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const cx = rect.width / 2;
    const cy = rect.height / 2;
    setView((v) => {
      const nextScale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, v.scale * mult));
      const k = nextScale / v.scale;
      return {
        scale: nextScale,
        x: cx - (cx - v.x) * k,
        y: cy - (cy - v.y) * k,
      };
    });
  };

  // Adjacency for hover dimming.
  const neighbors = useMemo(() => {
    const m = new Map<string, Set<string>>();
    for (const e of edges) {
      if (!m.has(e.fromId)) m.set(e.fromId, new Set());
      if (!m.has(e.toId)) m.set(e.toId, new Set());
      m.get(e.fromId)!.add(e.toId);
      m.get(e.toId)!.add(e.fromId);
    }
    return m;
  }, [edges]);

  const matchQuery = search.trim().toLowerCase();
  const nodeMatches = (id: string) => {
    if (!matchQuery) return true;
    const n = nodes.find((x) => x.id === id);
    if (!n) return false;
    return (
      n.name.toLowerCase().includes(matchQuery) ||
      n.slug.toLowerCase().includes(matchQuery)
    );
  };

  const isDimmed = (id: string) => {
    if (matchQuery && !nodeMatches(id)) return true;
    if (!hovered) return false;
    if (hovered === id) return false;
    return !neighbors.get(hovered)?.has(id);
  };

  const edgeActive = (e: GraphEdge) =>
    hovered === e.fromId ||
    hovered === e.toId ||
    (focusId != null && (e.fromId === focusId || e.toId === focusId));

  // ── Compute port-to-port paths for every edge. ────────────────────────
  interface RenderedEdge {
    id: string;
    edge: GraphEdge;
    path: string;
  }
  const renderedEdges: RenderedEdge[] = useMemo(() => {
    const out: RenderedEdge[] = [];
    for (const e of edges) {
      const srcRect = rects.get(e.fromId);
      const dstRect = rects.get(e.toId);
      if (!srcRect || !dstRect) continue;

      const srcCols = nodeColumns.get(e.fromId)?.visible ?? [];
      const dstCols = nodeColumns.get(e.toId)?.visible ?? [];

      const srcColIdx = srcCols.findIndex((c) => c.name === e.via);
      const srcIdx = srcColIdx >= 0 ? srcColIdx : 0;

      // Target column — prefer an identifier, else first column.
      let dstIdx = dstCols.findIndex((c) => c.role === "identifier");
      if (dstIdx < 0) dstIdx = 0;

      // Decide sides based on geometry.
      const srcCenterX = srcRect.x + srcRect.w / 2;
      const dstCenterX = dstRect.x + dstRect.w / 2;
      const srcSide: "left" | "right" = dstCenterX >= srcCenterX ? "right" : "left";
      const dstSide: "left" | "right" = dstCenterX >= srcCenterX ? "left" : "right";

      const src = portPoint(srcRect, srcIdx, srcSide);
      const dst = portPoint(dstRect, dstIdx, dstSide);
      out.push({
        id: e.id,
        edge: e,
        path: portPath(src.x, src.y, dst.x, dst.y),
      });
    }
    return out;
  }, [edges, rects, nodeColumns]);

  // ── Render ────────────────────────────────────────────────────────────
  const canvasBody = (
    <div
      ref={containerRef}
      onMouseDown={onMouseDownCanvas}
      onContextMenu={(e) => e.preventDefault()}
      className={cn(
        "relative w-full rounded-3xl overflow-hidden border border-border",
        panning ? "cursor-grabbing" : "cursor-grab",
      )}
      style={{
        height: canvasH,
        background:
          "radial-gradient(ellipse at top, oklch(22% 0.035 260) 0%, oklch(13% 0.025 265) 60%, oklch(9% 0.02 265) 100%)",
        touchAction: "none",
        overscrollBehavior: "contain",
      }}
    >
      <StarField />

      {/* World — SVG edges + HTML nodes live in the same transformed space */}
      <div
        className="absolute top-0 left-0 origin-top-left"
        style={{
          transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})`,
        }}
      >
        <svg
          overflow="visible"
          style={{ width: 1, height: 1, position: "absolute", top: 0, left: 0 }}
        >
          <defs>
            <linearGradient id="edge-grad" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="oklch(72% 0.15 260)" stopOpacity="0.75" />
              <stop offset="100%" stopColor="oklch(78% 0.16 170)" stopOpacity="0.75" />
            </linearGradient>
            <linearGradient id="edge-grad-hot" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="oklch(86% 0.2 260)" stopOpacity="1" />
              <stop offset="100%" stopColor="oklch(88% 0.22 170)" stopOpacity="1" />
            </linearGradient>
            <filter id="pulse-glow" x="-80%" y="-80%" width="260%" height="260%">
              <feGaussianBlur stdDeviation="2" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          {renderedEdges.map((r) => {
            const active = edgeActive(r.edge);
            const dimmed = hovered != null && !active;
            return (
              <g key={r.id} opacity={dimmed ? 0.15 : 1}>
                <path
                  id={`path-${r.id}`}
                  d={r.path}
                  fill="none"
                  stroke={active ? "url(#edge-grad-hot)" : "url(#edge-grad)"}
                  strokeWidth={active ? 1.8 : 1.1}
                  strokeLinecap="round"
                />
                <circle
                  r={active ? 3.2 : 2.2}
                  fill="white"
                  filter="url(#pulse-glow)"
                  opacity={active ? 1 : 0.7}
                >
                  <animateMotion
                    dur={active ? "1.4s" : "2.8s"}
                    repeatCount="indefinite"
                    rotate="auto"
                  >
                    <mpath href={`#path-${r.id}`} />
                  </animateMotion>
                </circle>
                {active && (
                  <>
                    <circle r={2.6} fill="oklch(88% 0.22 170)" filter="url(#pulse-glow)">
                      <animateMotion dur="1.4s" begin="0.46s" repeatCount="indefinite">
                        <mpath href={`#path-${r.id}`} />
                      </animateMotion>
                    </circle>
                    <circle r={2.6} fill="oklch(85% 0.2 260)" filter="url(#pulse-glow)">
                      <animateMotion dur="1.4s" begin="0.93s" repeatCount="indefinite">
                        <mpath href={`#path-${r.id}`} />
                      </animateMotion>
                    </circle>
                  </>
                )}
              </g>
            );
          })}
        </svg>

        {/* Nodes rendered as HTML for rich content */}
        {nodes.map((n) => {
          const rect = rects.get(n.id);
          if (!rect) return null;
          const colInfo = nodeColumns.get(n.id);
          return (
            <div
              key={n.id}
              className="absolute"
              style={{ left: rect.x, top: rect.y, width: rect.w, height: rect.h }}
            >
              <TableNode
                node={n}
                columns={colInfo?.visible ?? []}
                hiddenCount={colInfo?.hiddenCount ?? 0}
                height={rect.h}
                isFocused={n.id === focusId}
                isHot={hovered === n.id}
                isDimmed={isDimmed(n.id)}
                onHover={setHovered}
                onClick={() => onSelect(n.id)}
              />
            </div>
          );
        })}
      </div>

      {/* Controls — zoom, reset, fullscreen */}
      <div className="absolute top-3 right-3 flex items-center gap-1 bg-white/5 backdrop-blur-md border border-white/15 rounded-full p-0.5 z-10">
        <button
          onClick={() => zoomBy(1 / 1.25)}
          className="p-1.5 text-white/70 hover:text-white rounded-full hover:bg-white/10 transition"
          title="Zoom out"
        >
          <Minus size={13} />
        </button>
        <span className="text-[10px] text-white/50 tabular-nums font-mono min-w-[32px] text-center">
          {Math.round(view.scale * 100)}%
        </span>
        <button
          onClick={() => zoomBy(1.25)}
          className="p-1.5 text-white/70 hover:text-white rounded-full hover:bg-white/10 transition"
          title="Zoom in"
        >
          <Plus size={13} />
        </button>
        <span className="w-px h-4 bg-white/15 mx-0.5" />
        <button
          onClick={resetView}
          className="px-2 py-1 text-[10px] text-white/70 hover:text-white rounded-full hover:bg-white/10 transition font-body"
          title="Fit view"
        >
          Fit
        </button>
        <button
          onClick={() => setFullscreen((v) => !v)}
          className="p-1.5 text-white/70 hover:text-white rounded-full hover:bg-white/10 transition"
          title={fullscreen ? "Exit fullscreen" : "Expand fullscreen"}
        >
          {fullscreen ? <Minimize2 size={12} /> : <Maximize2 size={12} />}
        </button>
        {fullscreen && (
          <button
            onClick={() => setFullscreen(false)}
            className="p-1.5 text-white/70 hover:text-white rounded-full hover:bg-white/10 transition"
            title="Close"
          >
            <X size={12} />
          </button>
        )}
      </div>

      {nodes.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center">
          <p className="text-white/60 font-body text-sm">
            No entities yet — drop a dataset to seed the graph.
          </p>
        </div>
      )}

      {/* Legend / status strip at the bottom */}
      <div className="absolute bottom-3 left-3 right-3 flex items-center justify-between text-[10px] font-body text-white/55 pointer-events-none">
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-white/80" />
            {nodes.length} {focusId ? "in scope" : "entities"}
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-0.5 bg-white/70" />
            {edges.length} {focusId ? "connections" : "relationships"}
          </span>
        </div>
        <span className="flex items-center gap-2">
          <kbd className="px-1 py-0.5 rounded bg-white/10 text-[9px] font-mono">right-drag</kbd>
          <span>pan</span>
          <kbd className="px-1 py-0.5 rounded bg-white/10 text-[9px] font-mono">scroll</kbd>
          <span>zoom</span>
          <span className="opacity-60">·</span>
          <span>click a table to open</span>
        </span>
      </div>
    </div>
  );

  if (fullscreen) {
    return (
      <div
        className="fixed inset-0 z-[60] bg-black/60 backdrop-blur-sm p-5 animate-fade-in"
        onClick={(e) => {
          if (e.target === e.currentTarget) setFullscreen(false);
        }}
      >
        {canvasBody}
      </div>
    );
  }
  return canvasBody;
}

/** Starfield overlay — renders low-opacity twinkling dots. */
function StarField() {
  const stars = useMemo(
    () =>
      Array.from({ length: 70 }, (_, i) => ({
        x: (Math.sin(i * 934.31) * 0.5 + 0.5) * 100,
        y: (Math.cos(i * 451.27) * 0.5 + 0.5) * 100,
        r: 0.5 + ((i * 7) % 13) / 20,
        o: 0.15 + ((i * 3) % 9) / 30,
        d: 2 + (i % 5),
      })),
    [],
  );
  return (
    <svg
      className="absolute inset-0 pointer-events-none"
      width="100%"
      height="100%"
      preserveAspectRatio="none"
    >
      {stars.map((s, i) => (
        <circle key={i} cx={`${s.x}%`} cy={`${s.y}%`} r={s.r} fill="white" opacity={s.o}>
          <animate
            attributeName="opacity"
            values={`${s.o};${s.o * 0.4};${s.o}`}
            dur={`${s.d}s`}
            repeatCount="indefinite"
          />
        </circle>
      ))}
    </svg>
  );
}
