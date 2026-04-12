import { useState } from "react";
import type { ComplexRenderSpec } from "@/types/render-spec";
import { ExecSummary } from "./complex/ExecSummary";
import { PageNav } from "./complex/PageNav";
import { ReportPage } from "./complex/ReportPage";
import { AppendixPage } from "./complex/AppendixPage";

export function ComplexView({ spec }: { spec: ComplexRenderSpec }) {
  const [activePage, setActivePage] = useState("__exec_summary");

  const currentPage = spec.pages.find((p) => p.id === activePage);

  return (
    <div className="max-w-6xl mx-auto">
      <div className="mb-5">
        <h1 className="text-xl font-bold text-text-primary text-balance">
          {spec.report_title}
        </h1>
        {spec.report_subtitle && (
          <p className="text-sm text-text-secondary mt-1">{spec.report_subtitle}</p>
        )}
      </div>

      <div className="flex border border-border rounded-lg bg-surface-1 min-h-[500px]">
        <PageNav
          pages={spec.pages}
          activePage={activePage}
          onNavigate={setActivePage}
        />
        <div className="flex-1 p-6 overflow-y-auto">
          {activePage === "__exec_summary" && (
            <ExecSummary summary={spec.executive_summary} />
          )}
          {activePage === "__appendix" && (
            <AppendixPage appendix={spec.appendix} />
          )}
          {currentPage && (
            <ReportPage page={currentPage} />
          )}
        </div>
      </div>

      {spec.plan_ids && spec.plan_ids.length > 0 && (
        <p className="text-xs text-text-tertiary mt-3">
          Plans: {spec.plan_ids.map((id) => (
            <code key={id} className="font-mono text-accent mr-2">{id}</code>
          ))}
        </p>
      )}
    </div>
  );
}
