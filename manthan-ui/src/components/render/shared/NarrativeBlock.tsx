import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function NarrativeBlock({ text }: { text: string }) {
  return (
    <div className="prose prose-sm max-w-none text-text-secondary leading-relaxed
      prose-headings:text-text-primary prose-headings:font-semibold
      prose-strong:text-text-primary prose-strong:font-semibold
      prose-code:text-accent prose-code:bg-accent-soft prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-xs prose-code:font-mono
      prose-table:text-sm prose-th:text-left prose-th:text-text-secondary prose-th:font-medium prose-th:border-b prose-th:border-border prose-th:pb-2
      prose-td:border-b prose-td:border-border prose-td:py-2
      prose-a:text-accent prose-a:no-underline hover:prose-a:underline">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
    </div>
  );
}
