import { create } from "zustand";

type SidebarView = "datasets" | "memory" | "history";

export interface ExpandedVisual {
  visual_id: string;
  visual_type: string;
  html: string;
  /** Hint from the agent — not binding; the real height comes from
   *  postMessage once the iframe is live. */
  height: number;
}

interface UIState {
  sidebarView: SidebarView;
  sidebarOpen: boolean;
  rightPanelOpen: boolean;
  /** Is the artifact side panel currently open? (user can close/reopen) */
  artifactOpen: boolean;
  /** Is the artifact shown in fullscreen overlay mode? */
  artifactFullscreen: boolean;
  /** Inline visual the user expanded into the side panel (mirrors the
   *  artifact-to-panel flow so any chart can live in the right column). */
  expandedVisual: ExpandedVisual | null;
  expandedVisualFullscreen: boolean;
  /** User has clicked "Start analyzing" — show ReadyToQuery instead of schema profile */
  analyzeMode: boolean;
  /** Which view the FirstOpen (no active dataset) page renders.
   *  ``home`` is the hero landing; ``explore`` is the full dataset
   *  lister. Lifted into the store so the sidebar's Datasets rail
   *  button can route here from anywhere. */
  landingView: "home" | "explore";
  /** Source picker modal (Files / Cloud / Database / SaaS). One
   *  instance mounted at the app root, opened from several places
   *  (landing page "Connect warehouse" button, sidebar "Upload" rail
   *  button, empty state upload target). Lifted into the store so
   *  multiple components can request it without racing each other. */
  sourcePickerOpen: boolean;
  setSidebarView: (view: SidebarView) => void;
  toggleSidebar: () => void;
  toggleRightPanel: () => void;
  setArtifactOpen: (open: boolean) => void;
  setArtifactFullscreen: (fs: boolean) => void;
  setExpandedVisual: (v: ExpandedVisual | null) => void;
  setExpandedVisualFullscreen: (fs: boolean) => void;
  setAnalyzeMode: (v: boolean) => void;
  setSourcePickerOpen: (open: boolean) => void;
  setLandingView: (v: "home" | "explore") => void;
}

export const useUIStore = create<UIState>((set) => ({
  sidebarView: "datasets",
  sidebarOpen: true,
  rightPanelOpen: false,
  artifactOpen: true,
  artifactFullscreen: false,
  expandedVisual: null,
  expandedVisualFullscreen: false,
  analyzeMode: false,
  sourcePickerOpen: false,
  landingView: "home",
  setSidebarView: (view) => set({ sidebarView: view, sidebarOpen: true }),
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  toggleRightPanel: () => set((s) => ({ rightPanelOpen: !s.rightPanelOpen })),
  setArtifactOpen: (open) => set({ artifactOpen: open, artifactFullscreen: false }),
  setArtifactFullscreen: (fs) => set({ artifactFullscreen: fs, artifactOpen: true }),
  // Opening an inline visual in the side panel closes the artifact so
  // they don't fight for the same slot.
  setExpandedVisual: (v) => set({ expandedVisual: v, expandedVisualFullscreen: false, ...(v ? { artifactOpen: false } : {}) }),
  setExpandedVisualFullscreen: (fs) => set({ expandedVisualFullscreen: fs }),
  setAnalyzeMode: (v) => set({ analyzeMode: v }),
  setSourcePickerOpen: (open) => set({ sourcePickerOpen: open }),
  setLandingView: (v) => set({ landingView: v }),
}));
