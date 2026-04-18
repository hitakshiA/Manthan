import {
  siPostgresql,
  siMysql,
  siSqlite,
  siGooglecloud,
  siStripe,
  siHubspot,
  siShopify,
  siNotion,
  siAirtable,
  siGoogleads,
  siMeta,
  siGithub,
} from "simple-icons";

/**
 * Brand marks for every ingestion source we talk to. Uses CC0 SVG
 * paths from ``simple-icons`` where the brand is still in the
 * registry; falls back to a colored monogram tile for brands that
 * have been removed from simple-icons due to trademark takedowns
 * (Amazon, Azure, Microsoft, Salesforce, Slack).
 *
 * Monochrome mode: pass ``mono`` to force the current text color —
 * useful when we want the icon to match the DB-pill's on-state
 * accent color rather than the brand's native hue.
 */

interface SimpleIconEntry {
  hex: string;
  path: string;
  title: string;
}

// Every slug the picker knows about maps to either a simple-icons
// entry OR a monogram fallback. Keeping them in one table makes it
// cheap to fix a branding nit (hex swap, letter change) in one
// place.
type Slug =
  | "postgres"
  | "mysql"
  | "sqlite"
  | "s3"
  | "gcs"
  | "azure"
  | "https"
  | "stripe"
  | "hubspot"
  | "salesforce"
  | "shopify"
  | "notion"
  | "airtable"
  | "googleads"
  | "meta"
  | "github"
  | "slack";

interface MonogramFallback {
  label: string;
  hex: string;
  foreground?: string;
}

const REGISTRY: Record<
  Slug,
  { icon: SimpleIconEntry; mono?: never } | { icon?: never; mono: MonogramFallback }
> = {
  postgres: { icon: siPostgresql },
  mysql: { icon: siMysql },
  sqlite: { icon: siSqlite },
  gcs: { icon: siGooglecloud },
  stripe: { icon: siStripe },
  hubspot: { icon: siHubspot },
  shopify: { icon: siShopify },
  notion: { icon: siNotion },
  airtable: { icon: siAirtable },
  googleads: { icon: siGoogleads },
  meta: { icon: siMeta },
  github: { icon: siGithub },
  // Fallbacks — brands removed from simple-icons.
  s3: { mono: { label: "S3", hex: "FF9900" } },
  azure: { mono: { label: "Az", hex: "0078D4" } },
  salesforce: { mono: { label: "SF", hex: "00A1E0" } },
  slack: { mono: { label: "Sk", hex: "4A154B" } },
  https: { mono: { label: "https", hex: "6B7280" } },
};

export function ConnectorIcon({
  slug,
  size = 16,
  className = "",
  mono = false,
  showBackground = false,
}: {
  slug: Slug;
  size?: number;
  className?: string;
  /** Force ``currentColor`` instead of the brand hex. */
  mono?: boolean;
  /** Render inside a soft brand-colored rounded tile. Off by default
   *  because inline labels look better with bare marks; on when we
   *  want the icon to feel like a chip (e.g. the SaaS grid). */
  showBackground?: boolean;
}) {
  const entry = REGISTRY[slug];
  if (!entry) return null;

  if (entry.icon) {
    const color = mono ? "currentColor" : `#${entry.icon.hex}`;
    const svg = (
      <svg
        role="img"
        viewBox="0 0 24 24"
        width={size}
        height={size}
        fill={color}
        xmlns="http://www.w3.org/2000/svg"
        aria-label={entry.icon.title}
        className={className}
      >
        <title>{entry.icon.title}</title>
        <path d={entry.icon.path} />
      </svg>
    );
    if (!showBackground) return svg;
    return (
      <span
        className={`inline-flex items-center justify-center rounded-md ${className}`}
        style={{
          width: size + 8,
          height: size + 8,
          backgroundColor: `#${entry.icon.hex}15`,
        }}
      >
        {svg}
      </span>
    );
  }

  // Monogram fallback — letter (or short code) in brand color on a
  // soft background tile. Sized to match simple-icons glyphs when
  // placed alongside them.
  const m = entry.mono;
  const hex = mono ? "currentColor" : `#${m.hex}`;
  const bg = mono ? "transparent" : `#${m.hex}${showBackground ? "18" : "00"}`;
  return (
    <span
      className={`inline-flex items-center justify-center rounded-md font-semibold ${className}`}
      style={{
        width: size + (showBackground ? 8 : 0),
        height: size + (showBackground ? 8 : 0),
        backgroundColor: bg,
        color: hex,
        fontSize: Math.max(9, Math.round(size * 0.55)),
        lineHeight: 1,
        letterSpacing: "-0.02em",
      }}
      aria-label={m.label}
    >
      {m.label}
    </span>
  );
}
