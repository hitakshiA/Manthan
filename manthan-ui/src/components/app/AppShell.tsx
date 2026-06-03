/**
 * AppShell - sidebar + top bar + outlet for every /app route.
 *
 * Editorial direction: print sidebar. Nav rows are 11px letterspaced
 * labels with tabular numerals on the right, no icons, no rounded
 * pill backgrounds. The active row marks itself with a 1px left rule.
 */

import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useSearchParams } from "react-router-dom";
import {
  ChevronsUpDown,
  LogOut,
  Menu,
  Moon,
  Sun,
  X,
} from "lucide-react";
import type { ReactNode } from "react";
import { useClerk, useUser } from "@clerk/react";

import {
  getDashboardMetrics,
  getMe,
  type DashboardMetrics,
  type MeResponse,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { DemoTriggerMenu } from "@/components/app/DemoTriggerMenu";
import { Logo } from "@/components/Logo";
import { useTheme } from "@/lib/theme";
import { DemoV2Wizard } from "@/components/demo-v2/DemoV2Wizard";
import { DemoV3SlackWizard } from "@/components/demo-v2/DemoV3SlackWizard";
import { loadState as loadDemoV2State } from "@/lib/demo-v2";
import { loadState as loadDemoV3State } from "@/lib/demo-v3";

export function AppShell() {
  const metrics = useDashboardMetrics();
  const me = useMe();
  const demo = useDemoActive(me);
  const location = useLocation();

  // Mobile drawer open/close. Closed on every route change so tapping
  // a nav row navigates AND collapses the drawer in one motion.
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  useEffect(() => {
    setMobileNavOpen(false);
  }, [location.pathname]);

  // Shared nav-row markup so desktop sidebar + mobile drawer stay in
  // sync. Single source of truth for what's in the menu.
  const navRows = (
    <>
      <NavRow iconSlug="inbox" to="/app" label="Inbox" count={metrics?.inbox_count} alert={!!metrics && metrics.awaiting_count > 0} />
      <NavRow iconSlug="done" to="/app/done" label="Done" count={metrics?.done_count} />
      <NavRow iconSlug="policies" to="/app/policy" label="Policies" />
      <NavRow iconSlug="sources" to="/app/sources" label="Sources" count={metrics?.sources_count} />
      <NavRow iconSlug="audit" to="/app/audit" label="Audit" />
      <NavRow iconSlug="settings" to="/app/settings" label="Settings" />
    </>
  );

  return (
    <div
      // Fixed to viewport height so the sidebar (and its UserWidget
      // pinned at the bottom) never get pushed off-screen by a long
      // main column. The main area handles its own scroll inside.
      className="h-screen flex flex-col lg:flex-row overflow-hidden"
      style={{
        background: "var(--color-bg)",
        color: "var(--color-ink)",
      }}
    >
      {/* MOBILE TOP BAR - below lg only. Hamburger + workspace name.
            Desktop has the sidebar visible at all times so it doesn't
            need this. The bar shrinks to 44px tall so it doesn't eat
            into the editorial title block of each page. */}
      <div
        className="lg:hidden flex items-center gap-3 px-4 h-11 shrink-0 border-b"
        style={{
          background: "var(--color-bg)",
          borderColor: "var(--color-rule-soft)",
        }}
      >
        <button
          onClick={() => setMobileNavOpen(true)}
          aria-label="Open navigation"
          className="p-1.5 -ml-1.5"
          style={{ color: "var(--color-ink-muted)" }}
        >
          <Menu className="h-5 w-5" />
        </button>
        <div
          className="text-[12px] tracking-[0.16em] uppercase truncate"
          style={{
            color: "var(--color-ink-faint)",
            fontFamily: "Geist Mono, ui-monospace, monospace",
          }}
        >
          Manthan · {me?.org.name ?? "workspace"}
        </div>
      </div>

      {/* SIDEBAR - focused six-item nav.
            We deliberately cut the long sectioned list (15 rows across
            five groups) down to the surfaces a Director actually opens
            during a triage session: Inbox, Done, Policies, Sources,
            Audit, Settings. Everything else (Active/Escalated/Chat/
            Memory/Metrics/Help/etc) is either reachable via filters in
            the Inbox or covered by the case workspace itself - keeping
            it in the chrome was clutter, not utility. */}
      <aside
        className="hidden lg:flex w-[224px] shrink-0 flex-col border-r"
        style={{
          background: "var(--color-bg)",
          borderColor: "var(--color-rule-soft)",
        }}
      >
        <WorkspaceSwitch me={me} />

        <nav className="flex-1 overflow-y-auto px-2.5 pb-3 pt-3 flex flex-col gap-px">
          {navRows}
        </nav>

        <UserWidget me={me} />
      </aside>

      {/* MOBILE NAV DRAWER - slides from left below lg.
            Same nav rows + workspace switch + user widget as desktop,
            just inside a portal-ish overlay. The drawer is below the
            demo wizard (z-9000) so the wizard always wins. */}
      {mobileNavOpen && (
        <div
          className="lg:hidden fixed inset-0 z-50 flex"
          aria-modal="true"
          role="dialog"
        >
          <div
            className="absolute inset-0"
            style={{ background: "rgba(0,0,0,0.55)" }}
            onClick={() => setMobileNavOpen(false)}
          />
          <aside
            className="relative w-[260px] max-w-[80vw] h-full flex flex-col border-r animate-[manthan-drawer-in_180ms_ease]"
            style={{
              background: "var(--color-bg)",
              borderColor: "var(--color-rule-soft)",
            }}
          >
            <div className="flex items-center justify-between px-3 h-11 shrink-0 border-b"
              style={{ borderColor: "var(--color-rule-soft)" }}>
              <div
                className="text-[11px] tracking-[0.18em] uppercase"
                style={{
                  color: "var(--color-ink-faint)",
                  fontFamily: "Geist Mono, ui-monospace, monospace",
                }}
              >
                Menu
              </div>
              <button
                onClick={() => setMobileNavOpen(false)}
                aria-label="Close navigation"
                className="p-1.5 -mr-1.5"
                style={{ color: "var(--color-ink-muted)" }}
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <WorkspaceSwitch me={me} />
            <nav className="flex-1 overflow-y-auto px-2.5 pb-3 pt-2 flex flex-col gap-px">
              {navRows}
            </nav>
            <UserWidget me={me} />
          </aside>
          <style>{`
            @keyframes manthan-drawer-in {
              from { transform: translateX(-100%); }
              to   { transform: translateX(0); }
            }
          `}</style>
        </div>
      )}

      {/* MAIN */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* No TopBar - every editorial-memo surface owns its own header.
            The breadcrumb / recovered-$$ chip / demo selector used to
            live here; they're gone on purpose now so each page's
            Spectral title + eyebrow can carry the whole top weight. */}
        <main className="flex-1 overflow-y-auto">
          <RouteFader>
            <Outlet />
          </RouteFader>
        </main>
      </div>

      {demo.kind === "v2" && me?.member.email && (
        <DemoV2Wizard
          loggedInEmail={me.member.email}
          onClose={demo.dismiss}
        />
      )}
      {demo.kind === "v3" && me?.member.email && (
        <DemoV3SlackWizard
          loggedInEmail={me.member.email}
          onClose={demo.dismiss}
        />
      )}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// RouteFader - fade-in animation when the sidebar page group changes.
//
// Earlier version tried to hold the old children for a fade-OUT before
// the swap. That doesn't work cleanly here because `children` is a
// single <Outlet /> reference - React Router renders the new page
// component inside the same Outlet, so we can't snapshot the old
// rendered tree without going around react-router's internals.
//
// New approach: re-mount the wrapper on group change via React `key`,
// which triggers a CSS keyframe animation. The new page tweens in
// from opacity:0 + a tiny y-offset, which masks the hard swap visually
// even without an outgoing fade. Same group (e.g. /app -> /app/case/x)
// keeps the same key, so deep-navs don't re-animate.
// ──────────────────────────────────────────────────────────────────────

function RouteFader({ children }: { children: ReactNode }) {
  const location = useLocation();
  const groupKey = pageGroupKey(location.pathname);
  return (
    <div
      key={groupKey}
      style={{
        animation: "manthan-route-fade 280ms cubic-bezier(0.22, 1, 0.36, 1)",
        height: "100%",
        width: "100%",
        willChange: "opacity, transform",
      }}
    >
      <style>{`
        @keyframes manthan-route-fade {
          from { opacity: 0; transform: translateY(4px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>
      {children}
    </div>
  );
}

function pageGroupKey(pathname: string): string {
  // /app           -> "inbox"
  // /app/done      -> "done"
  // /app/policy/x  -> "policy"
  // /app/case/abc  -> "case"
  // anything else  -> the first segment after /app
  if (pathname === "/app" || pathname === "/app/") return "inbox";
  const m = pathname.match(/^\/app\/([^/]+)/);
  return m ? m[1] : pathname;
}

// ──────────────────────────────────────────────────────────────────────
// Unified demo mount controller. Returns which wizard (if any) should
// be mounted, derived from:
//   - URL `?demo=v2` or `?demo=v3` (explicit launch from a card click)
//   - non-stale saved localStorage state for v2 or v3 (resume after a
//     refresh / tab close mid-flow)
// dismiss() clears both signals (the URL param + any saved state for
// the active wizard).
// ──────────────────────────────────────────────────────────────────────

type DemoKind = "v2" | "v3" | null;

function useDemoActive(me: MeResponse | null): {
  kind: DemoKind;
  dismiss: () => void;
} {
  const [params, setParams] = useSearchParams();
  // Derive saved-state inline on every render. Used to be cached in
  // useState and only refreshed on pathname change, which meant when
  // the Inbox cleared localStorage to open a story BEFORE the wizard
  // mounted, AppShell didn't see the change until the next route
  // navigation - the wizard rendered ON TOP of the story slide. Inline
  // reads are cheap (single localStorage key) and always fresh.
  const v2Saved = loadDemoV2State() !== null;
  const v3Saved = loadDemoV3State() !== null;

  const urlFlag = params.get("demo");
  let kind: DemoKind = null;
  if (me?.member.email) {
    if (urlFlag === "v3" || (!urlFlag && v3Saved)) kind = "v3";
    else if (urlFlag === "v2" || (!urlFlag && v2Saved)) kind = "v2";
  }

  const dismiss = () => {
    if (urlFlag) {
      const next = new URLSearchParams(params);
      next.delete("demo");
      setParams(next, { replace: true });
    }
    // clearState() on the wizard side wipes localStorage; nothing for
    // us to do here on the React side because v2Saved/v3Saved derive
    // inline on the next render.
  };

  return { kind, dismiss };
}

// ──────────────────────────────────────────────────────────────────────
// Workspace switcher - title + slug, no chrome.
// ──────────────────────────────────────────────────────────────────────

function WorkspaceSwitch({ me }: { me: MeResponse | null }) {
  return (
    <div
      className="px-4 py-4 border-b"
      style={{ borderColor: "var(--color-rule-soft)" }}
    >
      <button
        className="w-full flex items-center gap-2.5 group text-left hover:opacity-90 transition-opacity"
      >
        <Logo size={20} showWordmark={false} />
        <div className="flex-1 min-w-0">
          <div
            className="text-[13.5px] truncate"
            style={{ color: "var(--color-ink-strong)" }}
          >
            {me?.org.name ?? "Workspace"}
          </div>
          <div
            className="text-[10.5px] tracking-[0.06em] mt-0.5 truncate"
            style={{ color: "var(--color-ink-faint)" }}
          >
            {me ? `${me.org.slug} · ${me.org.plan.replace(/_/g, " ")}` : "-"}
          </div>
        </div>
        <ChevronsUpDown
          className="h-3.5 w-3.5"
          style={{ color: "var(--color-ink-ghost)" }}
        />
      </button>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Nav group + row.
// ──────────────────────────────────────────────────────────────────────

function NavGroup({ label, children }: { label?: string; children: ReactNode }) {
  return (
    <div className="mt-5 first:mt-2">
      {label && (
        <div
          className="px-2.5 mb-1.5 text-[10.5px] uppercase tracking-[0.16em] font-medium"
          style={{ color: "var(--color-ink-ghost)" }}
        >
          {label}
        </div>
      )}
      <div className="flex flex-col gap-px">{children}</div>
    </div>
  );
}

function NavRow({
  iconSlug,
  to,
  label,
  count,
  meta,
  alert,
}: {
  /** Slug in /icons/nav/{slug}.gif + .png (e.g. "inbox", "policies"). */
  iconSlug: string;
  to: string;
  label: string;
  count?: number | string;
  meta?: string;
  alert?: boolean;
}) {
  return (
    <NavLink
      to={to}
      end={to === "/app"}
      className={({ isActive }) =>
        cn(
          // flex-1 makes each row claim an equal share of the sidebar's
          // remaining vertical space. Type + icon scale up to match so
          // each row reads as a primary section, not a list item.
          "nav-row group relative flex flex-1 items-center gap-3.5 px-3 text-[17px] tracking-[0.003em] transition-colors min-h-[48px]",
          isActive && "nav-row-active",
        )
      }
      style={({ isActive }) => ({
        color: isActive ? "var(--color-ink-strong)" : "var(--color-ink)",
        fontWeight: isActive ? 500 : 400,
        borderRadius: 6,
        background: isActive ? "var(--color-surface-2)" : "transparent",
      })}
    >
      {({ isActive }) => (
        <>
          <NavAnimatedIcon slug={iconSlug} active={isActive} />
          <span className="flex-1 truncate">{label}</span>
          {meta && (
            <span
              className="text-[10px] tracking-[0.08em] uppercase tabular-nums"
              style={{ color: "var(--color-ink-ghost)" }}
            >
              {meta}
            </span>
          )}
          {count !== undefined && count !== null && (
            <span
              className="tabular-nums text-[15px]"
              style={{
                color: alert
                  ? "var(--color-amber)"
                  : isActive
                    ? "var(--color-ink-strong)"
                    : "var(--color-ink-faint)",
              }}
            >
              {typeof count === "number" ? count.toLocaleString() : count}
            </span>
          )}
        </>
      )}
    </NavLink>
  );
}

/**
 * NavAnimatedIcon - the per-nav-row icon. Renders a static first-frame
 * PNG by default, and on row hover swaps to the animated GIF (which
 * restarts the loop). The GIFs ship black on transparent, so we apply
 * `filter: invert(var(--icon-invert))` - a token set to 1 in dark
 * theme and 0 in light - to keep them legible across both themes.
 *
 * The hover swap relies on the parent NavLink's :hover state via the
 * `.nav-row` class. Implemented with two stacked <img>s for zero
 * layout shift on swap, and `display: none` toggled via the class.
 */
function NavAnimatedIcon({
  slug,
  active,
}: {
  slug: string;
  active: boolean;
}) {
  const size = 28;
  return (
    <span
      // Use a data attribute (not inline CSS custom prop) for the
      // active-state selector - React's inline-style serialization is
      // sensitive to whitespace and CSS attribute selectors are brittle
      // against it. data-active="1" is reliable across browsers.
      data-active={active ? "1" : "0"}
      className="nav-icon relative inline-block shrink-0"
      style={{ width: size, height: size }}
      aria-hidden
    >
      <img
        src={`/icons/nav/${slug}.png`}
        alt=""
        width={size}
        height={size}
        className="nav-icon-still absolute inset-0 w-full h-full"
      />
      <img
        src={`/icons/nav/${slug}.gif`}
        alt=""
        width={size}
        height={size}
        className="nav-icon-anim absolute inset-0 w-full h-full"
      />
    </span>
  );
}

// ──────────────────────────────────────────────────────────────────────
// User widget - initials + name, hairline border above.
// ──────────────────────────────────────────────────────────────────────

function UserWidget({ me }: { me: MeResponse | null }) {
  const initials = me?.member.initials ?? "-";
  const name = me?.member.display_name ?? "-";
  const role = me?.member.role ?? "";
  const [theme, setTheme] = useTheme();
  // `useClerk()` returns the singleton Clerk instance - calling
  // `.signOut()` clears the session and respects the
  // `afterSignOutUrl="/"` config from main.tsx, so the user lands
  // back on the marketing page.
  const clerk = useClerk();
  return (
    <div
      className="px-2.5 py-2.5 border-t flex items-center gap-2 shrink-0"
      style={{
        borderColor: "var(--color-rule-soft)",
        background: "var(--color-bg)",
        // Min height guarantees the widget never collapses to invisible
        // even on shorter viewports where the nav could otherwise
        // squeeze it.
        minHeight: 52,
      }}
    >
      <button className="flex-1 min-w-0 flex items-center gap-2.5 px-1.5 py-1 group hover:opacity-90 transition-opacity">
        <div
          className="h-7 w-7 inline-flex items-center justify-center text-[10.5px] tracking-[0.03em] font-medium tabular-nums shrink-0"
          style={{
            background: "var(--color-accent-soft)",
            color: "var(--color-accent)",
            borderRadius: "var(--radius-sm)",
          }}
        >
          {initials}
        </div>
        <div className="flex-1 min-w-0 text-left">
          <div
            className="text-[13px] truncate"
            style={{ color: "var(--color-ink-strong)" }}
          >
            {name}
          </div>
          {role && (
            <div
              className="text-[10.5px] tracking-[0.06em] capitalize truncate"
              style={{ color: "var(--color-ink-faint)" }}
            >
              {role}
            </div>
          )}
        </div>
      </button>
      <button
        onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
        className="h-7 w-7 inline-flex items-center justify-center rounded hover:bg-[var(--color-surface)] transition-colors shrink-0"
        style={{ color: "var(--color-ink-muted)" }}
        title={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
        aria-label="Toggle theme"
      >
        {theme === "dark" ? (
          <Sun className="h-4 w-4" />
        ) : (
          <Moon className="h-4 w-4" />
        )}
      </button>
      <button
        onClick={() => {
          // Fire-and-forget - Clerk handles its own state cleanup +
          // the afterSignOutUrl redirect from main.tsx.
          void clerk?.signOut();
        }}
        className="h-7 w-7 inline-flex items-center justify-center rounded hover:bg-[var(--color-surface)] transition-colors shrink-0"
        style={{ color: "var(--color-ink-muted)" }}
        title="Sign out"
        aria-label="Sign out"
      >
        <LogOut className="h-4 w-4" />
      </button>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// TopBar - print-style breadcrumb on a hairline, recovered $$ chip + demo.
// No glow, no backdrop-blur theatre.
// ──────────────────────────────────────────────────────────────────────

function TopBar({
  pathname,
  metrics,
}: {
  pathname: string;
  metrics: DashboardMetrics | null;
}) {
  // The page header inside each route owns the primary heading
  // ("Inbox", "Policies", etc) - we don't duplicate it here. Only
  // show a breadcrumb for the deep paths where it actually helps
  // (e.g. /app/case/abc - show "Inbox / Case").
  const crumbs = pathname.split("/").filter(Boolean);
  const isShallow =
    crumbs.length === 0 ||
    (crumbs.length === 1 && crumbs[0] === "app") ||
    crumbs.length === 2;
  return (
    <header
      className="sticky top-0 z-30 border-b shrink-0"
      style={{
        background: "var(--color-bg)",
        borderColor: "var(--color-rule-soft)",
      }}
    >
      <div className="h-11 px-6 md:px-8 flex items-center justify-between gap-6">
        {/* Left: breadcrumb only on deep paths. Shallow pages let their
             own page header carry the title. */}
        <nav className="flex items-baseline gap-2 text-[12px] min-w-0">
          {!isShallow &&
            crumbs.slice(1).map((c, i, arr) => {
              const isLast = i === arr.length - 1;
              return (
                <span key={i} className="inline-flex items-baseline gap-2">
                  {i > 0 && (
                    <span style={{ color: "var(--color-ink-ghost)" }}>/</span>
                  )}
                  <span
                    className="capitalize tracking-[0.02em]"
                    style={{
                      color: isLast
                        ? "var(--color-ink-strong)"
                        : "var(--color-ink-faint)",
                    }}
                  >
                    {c}
                  </span>
                </span>
              );
            })}
        </nav>

        <div className="flex items-center gap-5">
          <RecoveredChip minor={metrics?.recovered_this_month_minor ?? null} />
          <DemoTriggerMenu />
        </div>
      </div>
    </header>
  );
}

// TopBar is no longer rendered (the editorial-memo pages own their own
// chrome) but we keep the component around in case we want to re-enable
// it for a specific surface later. Suppress the unused-symbol warning.
void TopBar;

function RecoveredChip({ minor }: { minor: number | null }) {
  if (minor === null) {
    return (
      <span
        className="text-[11.5px] tabular-nums"
        style={{ color: "var(--color-ink-ghost)" }}
      >
        -
      </span>
    );
  }
  return (
    <div className="inline-flex items-baseline gap-1.5">
      <span
        className="text-[10px] uppercase tracking-[0.14em]"
        style={{ color: "var(--color-ink-ghost)" }}
      >
        Recovered
      </span>
      <span
        className="font-display text-[15px] tabular-nums leading-none"
        style={{ color: "var(--color-ink-strong)" }}
      >
        {formatMoneyShort(minor)}
      </span>
      <span
        className="text-[10px] uppercase tracking-[0.12em]"
        style={{ color: "var(--color-ink-ghost)" }}
      >
        / month
      </span>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Hooks + helpers.
// ──────────────────────────────────────────────────────────────────────

function useDashboardMetrics(): DashboardMetrics | null {
  const [m, setM] = useState<DashboardMetrics | null>(null);
  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    const tick = async () => {
      try {
        const r = await getDashboardMetrics();
        if (!cancelled) setM(r);
      } catch {
        // ignore - retry next tick
      } finally {
        if (!cancelled) timer = window.setTimeout(tick, 8000);
      }
    };
    tick();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, []);
  return m;
}

function useMe(): MeResponse | null {
  const [me, setMe] = useState<MeResponse | null>(null);
  // Re-fetch /api/me whenever the Clerk session changes - so the
  // sidebar identity reflects the actual signed-in user. Without this
  // dependency, the first /api/me fires BEFORE Clerk has resolved the
  // session, ClerkIdentitySync hasn't set the X-Manthan-Dev-Email
  // header yet, and we cache the seeded "Dev Admin" forever.
  const { isLoaded, isSignedIn, user } = useUser();
  const clerkEmail = user?.primaryEmailAddress?.emailAddress ?? null;
  useEffect(() => {
    let cancelled = false;
    // Don't fire until Clerk has either confirmed signed-in (so the
    // identity header is set) OR confirmed signed-out (so we fall
    // back to seed cleanly).
    if (!isLoaded) return;
    getMe()
      .then((r) => {
        if (!cancelled) setMe(r);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [isLoaded, isSignedIn, clerkEmail]);
  return me;
}

function formatMoneyShort(minor: number): string {
  if (minor >= 100_000_00) {
    return `$${(Math.round(minor / 100_000) / 10).toLocaleString()}M`.replace(
      /\.0M$/,
      "M",
    );
  }
  if (minor >= 1_000_00) {
    return `$${Math.round(minor / 1_000_00).toLocaleString()}K`;
  }
  return `$${(minor / 100).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}
