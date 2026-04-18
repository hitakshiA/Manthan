"""Manthan design system for HTML artifacts.

This CSS + JS block is injected into the agent's system prompt so that
every create_artifact call produces HTML matching the app's design.
"""

ARTIFACT_DESIGN_SYSTEM = """\
# Artifact Design System (MANDATORY for create_artifact)

Your HTML artifacts MUST use this exact design system to match the Manthan app.

## CSS Variables (copy into every artifact's <style>)
```css
:root {
  --bg: #f6f6f5; --bg-card: #ffffff; --bg-sunken: #f2f2f1;
  --text-1: #262625; --text-2: #646463; --text-3: #919190; --text-4: #b6b6b5;
  --accent: #6e56cf; --accent-hover: #5d42b0; --accent-soft: #eae3fc;
  --success: #3b8263; --success-soft: #e7f6f0;
  --warning: #bd9e14; --warning-soft: #fcf5e0;
  --error: #c92f31; --error-soft: #feeced;
  --border: #e8e8e7; --border-strong: #d3d3d2;
  --shadow-sm: 0 1px 3px rgba(38,38,37,0.06);
  --shadow-md: 0 4px 12px rgba(38,38,37,0.06);
  --radius: 12px; --radius-lg: 16px; --radius-full: 9999px;
}
```

## Fonts
```html
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
```
- Display/headings: 'Instrument Serif', serif
- Body/data: 'Inter', sans-serif

## Base Styles
```css
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:'Inter',sans-serif; background:var(--bg); color:var(--text-1);
  line-height:1.6; -webkit-font-smoothing:antialiased; }
```

## Layout
- Container: max-width:1200px; margin:0 auto; padding:24px;
- CSS Grid: grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap:16px;

## Chart.js Setup (CRITICAL — follow exactly)
```javascript
const COLORS = ['#6e56cf','#3b8263','#bd9e14','#c92f31','#3b82f6','#8b5cf6','#14b8a6','#f59e0b'];
Chart.defaults.font.family = "'Inter', sans-serif";
Chart.defaults.font.size = 12;
Chart.defaults.color = '#919190';
Chart.defaults.plugins.legend.labels.usePointStyle = true;
Chart.defaults.elements.bar.borderRadius = 4;
```

## CHART CONTAINER RULES (NON-NEGOTIABLE)
Every chart canvas MUST be inside a fixed-height container:
```css
.chart-wrapper { position:relative; height:280px; width:100%; }
```
```html
<div class="chart-wrapper"><canvas id="myChart"></canvas></div>
```
Every Chart.js instance MUST set:
```javascript
options: { responsive: true, maintainAspectRatio: false }
```
NEVER let a chart grow unbounded. NEVER omit maintainAspectRatio:false.

## DATA PRE-AGGREGATION (NON-NEGOTIABLE)
NEVER pass raw rows (5000 order records) to Chart.js. ALWAYS pre-aggregate:
- Line charts: aggregate to monthly/weekly (max 36 data points)
- Bar charts: max 20 categories. If more, show top 20
- Pie/doughnut: max 8 slices. Group rest as "Other"
- Scatter: max 500 points. Sample if more
- Tables: paginate at 20 rows

Pre-aggregate IN SQL before embedding:
```sql
-- GOOD: monthly aggregation (12 rows)
SELECT DATE_TRUNC('month', order_time) AS month, SUM(total_price) AS revenue
FROM orders GROUP BY 1 ORDER BY 1

-- BAD: raw rows (5000 rows → chart explodes)
SELECT order_time, total_price FROM orders
```

## KPI Cards
```css
.kpi-card { background:var(--bg-card); border:1px solid var(--border);
  border-radius:var(--radius); padding:20px 24px; }
.kpi-label { font-size:11px; font-weight:600; color:var(--text-3);
  text-transform:uppercase; letter-spacing:0.5px; }
.kpi-value { font-family:'Instrument Serif',serif; font-size:32px;
  color:var(--text-1); margin:4px 0; }
.kpi-delta { font-size:12px; font-weight:600; }
.kpi-delta.positive { color:var(--success); }
.kpi-delta.negative { color:var(--error); }
```

## Chart + Table Cards
```css
.chart-card { background:var(--bg-card); border:1px solid var(--border);
  border-radius:var(--radius); padding:20px 24px; overflow:hidden; }
.chart-title { font-size:14px; font-weight:600; color:var(--text-1); margin-bottom:4px; }
.chart-subtitle { font-size:11px; color:var(--text-3); margin-bottom:16px; }
.chart-wrapper { position:relative; height:280px; width:100%; }
.table-card { background:var(--bg-card); border:1px solid var(--border);
  border-radius:var(--radius); padding:20px 24px; overflow-x:auto; max-height:500px;
  overflow-y:auto; }
table { width:100%; border-collapse:collapse; font-size:13px; }
th { text-align:left; padding:10px 12px; border-bottom:2px solid var(--border);
  font-size:11px; font-weight:600; color:var(--text-3);
  text-transform:uppercase; letter-spacing:0.5px; cursor:pointer; user-select:none; }
th:hover { color:var(--accent); }
td { padding:10px 12px; border-bottom:1px solid var(--bg-sunken); }
tr:hover td { background:var(--bg-sunken); }
.num { text-align:right; font-variant-numeric:tabular-nums; }
.tag { font-size:11px; font-weight:600; padding:3px 10px;
  border-radius:var(--radius-full); display:inline-block; }
```

## CRITICAL: Dashboard Architecture Pattern

Every dashboard MUST use a single Dashboard class that owns ALL state:

```javascript
class Dashboard {
  constructor(rawData) {
    this.raw = rawData;          // never mutated
    this.filtered = rawData;     // current filtered view
    this.charts = {};            // Chart.js instances by id
    this.activeFilters = {};     // { filterName: value }
    this.drillState = null;      // current drill-down context
    this.init();
  }

  init() {
    this.populateFilters();
    this.render();               // renders EVERYTHING
  }

  // Called by EVERY filter/control change
  applyFilters() {
    this.filtered = this.raw.filter(row => {
      for (const [key, val] of Object.entries(this.activeFilters)) {
        if (val && val !== 'all' && row[key] != val) return false;
      }
      return true;
    });
    this.render();               // re-renders EVERYTHING
  }

  // SINGLE render method updates ALL tiles
  render() {
    this.renderKPIs();           // ALL KPI cards
    this.renderCharts();         // ALL charts
    this.renderTable();          // ALL tables
    this.renderActiveFilters();  // show active filter pills
  }
}
```

## FILTER RULES (NON-NEGOTIABLE)
1. applyFilters() MUST update EVERY KPI, EVERY chart, and EVERY table
2. Filters are global — changing one filter re-renders the entire dashboard
3. Show active filter pills below the filter bar so the user knows what's applied
4. Include a "Reset All" button that clears all filters
5. Date range filters: use two <input type="date"> elements
6. Dimension filters: <select> dropdowns populated from the data
7. Filters should show count: "Status (7 values)" in the label

## DRILL-DOWN PATTERNS
Every chart should support click-to-drill:

```javascript
// On every chart's onClick:
options: {
  onClick: (event, elements) => {
    if (elements.length > 0) {
      const idx = elements[0].index;
      const label = chart.data.labels[idx];
      dashboard.drillDown(dimensionName, label);
    }
  }
}

// In Dashboard class:
drillDown(dimension, value) {
  this.activeFilters[dimension] = value;
  this.applyFilters();
  this.showDrillBreadcrumb(dimension, value);
}

showDrillBreadcrumb(dimension, value) {
  // Show: "All → Status: Delivered" with back button
  const bc = document.getElementById('breadcrumb');
  bc.innerHTML = `<span class="breadcrumb-item" onclick="dashboard.clearDrill()">All</span>
    <span>→</span>
    <span class="breadcrumb-active">${dimension}: ${value}</span>`;
  bc.style.display = 'flex';
}

clearDrill() {
  this.drillState = null;
  this.activeFilters = {};
  this.populateFilters();  // reset dropdowns
  this.applyFilters();
  document.getElementById('breadcrumb').style.display = 'none';
}
```

## ACTIVE FILTER PILLS
```css
.filter-pills { display:flex; gap:6px; flex-wrap:wrap; margin:8px 0; }
.filter-pill { font-size:11px; font-weight:600; padding:4px 10px;
  border-radius:var(--radius-full); background:var(--accent-soft);
  color:var(--accent); display:flex; align-items:center; gap:4px; }
.filter-pill .remove { cursor:pointer; font-size:14px; line-height:1; }
.filter-pill .remove:hover { color:var(--error); }
```

When a filter is active, show a pill: `Status: Delivered ✕`
Clicking ✕ removes that filter and re-renders.

## TABLE FEATURES
- Sortable columns (click header toggles asc/desc, show ▲▼ arrow)
- Clickable rows: clicking a row drills into that entity
- Pagination for >20 rows: "Showing 1-20 of 150" with prev/next buttons
- Conditional formatting: color cells based on value (green for high, red for low)
```css
.cell-good { color:var(--success); font-weight:600; }
.cell-bad { color:var(--error); font-weight:600; }
.cell-warn { color:var(--warning); font-weight:600; }
```

## CHART TOOLTIPS
Every chart must have rich tooltips:
```javascript
tooltip: {
  callbacks: {
    title: (items) => items[0].label,
    label: (item) => {
      // Show: "Revenue: $1.2M" or "Orders: 1,234" with proper formatting
      return `${item.dataset.label}: ${formatValue(item.parsed.y, format)}`;
    },
    afterBody: (items) => {
      // Show percentage of total, or comparison to average
      const total = items[0].dataset.data.reduce((a,b) => a+b, 0);
      const pct = ((items[0].parsed.y / total) * 100).toFixed(1);
      return `${pct}% of total`;
    }
  }
}
```

## DETAIL PANEL (for drill-down results)
When a user clicks a chart bar or table row, show a detail panel:
```css
.detail-panel { background:var(--bg-card); border:1px solid var(--border);
  border-radius:var(--radius-lg); padding:24px; margin-top:16px;
  box-shadow:var(--shadow-md); }
.detail-panel h3 { font-size:16px; font-weight:600; margin-bottom:12px; }
.detail-panel .close-btn { float:right; cursor:pointer; color:var(--text-3);
  font-size:18px; }
.detail-panel .close-btn:hover { color:var(--error); }
```

## NUMBER FORMATTING (always use these helpers)
```javascript
function fmt(v, type) {
  if (v == null) return '—';
  switch(type) {
    case '$': return v >= 1e6 ? `$${(v/1e6).toFixed(1)}M` : v >= 1e3 ? `$${(v/1e3).toFixed(1)}K` : `$${v.toFixed(0)}`;
    case '%': return `${v.toFixed(1)}%`;
    case '#': return v >= 1e6 ? `${(v/1e6).toFixed(1)}M` : v >= 1e3 ? `${(v/1e3).toFixed(1)}K` : v.toLocaleString();
    default: return String(v);
  }
}
```

## IMPORTANT RULES
- Background is ALWAYS var(--bg) (#f6f6f5) — NEVER dark/black
- Cards are ALWAYS white with 1px border
- ALL headings use Instrument Serif, ALL body uses Inter
- Filters MUST update EVERY tile — KPIs, charts, AND tables
- Every chart is clickable — click drills into that dimension value
- Tables are sortable AND clickable (row click = drill)
- Show breadcrumb trail when drilled: "All → Region: North → Status: Delivered"
- Include "Reset All Filters" button
- Show active filter pills
- Format all numbers with fmt() helper
- Pre-aggregate data (max 1000 points per chart)
- Tables paginate at 20 rows

## JAVASCRIPT SAFETY RULES
- Use regular strings with + concatenation instead of template literals
  with backticks. Template literals often break due to unmatched braces.
  BAD:  `${value}%`
  GOOD: value + '%'
- Always call the main render/init function at the END of the script
  so the dashboard loads with data on page open (not just on interaction)
- DO NOT wrap the entire script in try/catch. If you open ``try {`` you
  MUST close it with ``} catch (e) { console.error(e); }`` — a missing
  catch clause is a SyntaxError and renders the whole dashboard blank.
  Safer default: write correct code and skip the try/catch entirely.
- Test every function: if a chart or KPI doesn't render, the user sees blank cards
"""
