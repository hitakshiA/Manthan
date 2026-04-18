/** Heuristics that turn a raw SQL query or Python snippet into an
 *  exec-voice status line, plus a progression ladder the UI cycles
 *  through while the tool is still running.
 *
 *  The thinking indicator only shows a single generic "Running the
 *  analysis" today. That's fine for a 2-second SQL lookup but wrong
 *  for a 60-second SARIMAX fit — the exec stares at a frozen label
 *  and thinks the app hung. We infer the *kind* of work from the
 *  code preview, then rotate through specific sub-steps so the
 *  perceived progress matches the actual work.
 */

export interface WorkInference {
  /** Single-line status headline (shown immediately) */
  label: string;
  /** Extra lines the UI can cycle through if the tool is slow.
   *  Ordered earliest → latest. First entry is shown after ~3s,
   *  the rest every ~4s until the tool finishes. */
  ladder: string[];
}

/** Infer a Python playbook from its code preview. */
export function inferPythonWork(code: string): WorkInference {
  const c = (code || "").toLowerCase();

  if (/sarimax|exponentialsmoothing|seasonal_decompose|\bforecast\b/.test(c)) {
    return {
      label: "Fitting a forecast…",
      ladder: [
        "Loading the history…",
        "Picking the right model…",
        "Running the fit — this can take a moment…",
        "Computing confidence bands…",
        "Still fitting — large series, bear with me…",
      ],
    };
  }
  if (/isolationforest|zscore|anomal/.test(c)) {
    return {
      label: "Hunting for anomalies…",
      ladder: [
        "Scoring each point…",
        "Ranking the outliers…",
        "Cross-checking the flagged windows…",
      ],
    };
  }
  if (/kmeans|silhouette|\brfm\b|segment/.test(c)) {
    return {
      label: "Segmenting customers…",
      ladder: [
        "Computing the behavioral features…",
        "Finding natural groupings…",
        "Labeling each segment in business language…",
      ],
    };
  }
  if (/ttest_ind|mannwhitneyu|chi2_contingency|\bwelch\b/.test(c)) {
    return {
      label: "Testing if the gap is real…",
      ladder: [
        "Splitting the two groups…",
        "Running the significance test…",
        "Translating the p-value into plain English…",
      ],
    };
  }
  if (/pearsonr|spearmanr|\bols\(|regress/.test(c)) {
    return {
      label: "Running a correlation…",
      ladder: [
        "Pulling the paired series…",
        "Fitting the relationship…",
        "Checking for confounds…",
      ],
    };
  }
  if (/pivot_table|pivot\(/.test(c) && /cohort|retention|monthly.*month/.test(c)) {
    return {
      label: "Building the cohort table…",
      ladder: [
        "Stamping each customer's signup month…",
        "Computing month-over-month retention…",
        "Shaping the heatmap…",
      ],
    };
  }
  if (/plotly|px\.|go\.figure|go\.bar|go\.scatter|go\.line|matplotlib|plt\./.test(c)) {
    return {
      label: "Drafting the chart…",
      ladder: [
        "Shaping the data…",
        "Laying out the visual…",
        "Polishing the axes…",
      ],
    };
  }
  if (/\bgroupby\(|agg\(|pivot_table/.test(c)) {
    return {
      label: "Aggregating the cuts…",
      ladder: [
        "Slicing by the dimensions…",
        "Rolling up the totals…",
      ],
    };
  }
  if (/read_parquet|read_csv|pd\.read/.test(c)) {
    return { label: "Loading the data…", ladder: ["Parsing the rows…"] };
  }
  if (/whatif|simulate|sensitivity|elasticity/.test(c)) {
    return {
      label: "Running a what-if…",
      ladder: [
        "Setting up the scenario grid…",
        "Sweeping the parameters…",
        "Ranking by sensitivity…",
      ],
    };
  }

  return {
    label: "Running the analysis…",
    ladder: [
      "Crunching the numbers…",
      "Still working on it…",
    ],
  };
}

/** Infer what a SQL query is doing from its text. */
export function inferSqlWork(sql: string): WorkInference {
  const s = (sql || "").toLowerCase();

  if (/\bshow tables\b|information_schema/.test(s)) {
    return { label: "Scanning the dataset structure…", ladder: [] };
  }
  if (/\border by\b.*\blimit\b/.test(s)) {
    return { label: "Ranking…", ladder: ["Sorting the cut…", "Picking the top slice…"] };
  }
  if (/date_trunc|\bmonth\(|\byear\(|\bquarter\(|\bweek\(|\bday\(|\bdate_part\b/.test(s)) {
    return {
      label: "Pulling the time series…",
      ladder: ["Bucketing by period…", "Aligning the window…"],
    };
  }
  if (/count\(\*\)|\bsum\(|\bavg\(|\bmedian\(|\bstddev\(|percentile/.test(s) && /group by/.test(s)) {
    return {
      label: "Crunching the numbers by segment…",
      ladder: ["Rolling up each group…", "Formatting the totals…"],
    };
  }
  if (/count\(\*\)|\bsum\(|\bavg\(|\bmedian\(|\bstddev\(|percentile/.test(s)) {
    return { label: "Crunching the numbers…", ladder: [] };
  }
  if (/\bjoin\b/.test(s)) {
    return {
      label: "Stitching the tables…",
      ladder: ["Matching records…", "Keeping the valid joins…"],
    };
  }
  if (/group by/.test(s)) {
    return { label: "Slicing the data…", ladder: ["Bucketing…"] };
  }
  return { label: "Pulling the data…", ladder: [] };
}

/** Infer exec-voice work label from a tool name + its args_preview. */
export function inferWorkFromTool(tool: string, argsPreview: string): WorkInference {
  if (tool === "run_python") return inferPythonWork(argsPreview);
  if (tool === "run_sql") return inferSqlWork(argsPreview);
  if (tool === "create_artifact") {
    const title = argsPreview.replace(/^Creating:\s*/i, "");
    return {
      label: title ? `Writing up: ${title}` : "Writing up the brief…",
      ladder: ["Laying out the findings…", "Finalizing the recommendation…"],
    };
  }
  if (tool === "emit_visual") {
    return { label: "Preparing a quick view…", ladder: [] };
  }
  if (tool === "save_memory") return { label: "Noting this for later…", ladder: [] };
  if (tool === "recall_memory") return { label: "Remembering prior findings…", ladder: [] };
  if (tool === "get_schema") return { label: "Checking what's in the dataset…", ladder: [] };
  if (tool === "get_context") return { label: "Reading the context…", ladder: [] };
  if (tool === "ask_user") return { label: "Checking with you…", ladder: [] };
  if (tool === "create_plan") return { label: "Laying out the plan…", ladder: [] };
  return { label: tool, ladder: [] };
}
