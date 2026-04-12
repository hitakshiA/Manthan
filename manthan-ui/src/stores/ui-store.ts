import { create } from "zustand";

type SidebarView = "datasets" | "memory" | "history";

interface UIState {
  sidebarView: SidebarView;
  sidebarOpen: boolean;
  rightPanelOpen: boolean;
  setSidebarView: (view: SidebarView) => void;
  toggleSidebar: () => void;
  toggleRightPanel: () => void;
}

export const useUIStore = create<UIState>((set) => ({
  sidebarView: "datasets",
  sidebarOpen: true,
  rightPanelOpen: false,
  setSidebarView: (view) => set({ sidebarView: view, sidebarOpen: true }),
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  toggleRightPanel: () => set((s) => ({ rightPanelOpen: !s.rightPanelOpen })),
}));
