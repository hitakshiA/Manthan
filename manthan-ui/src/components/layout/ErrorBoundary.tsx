import { Component, type ReactNode, type ErrorInfo } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    this.setState({ errorInfo });
    // Log the FULL error with component stack to console
    console.error("[ErrorBoundary] Caught error:", error.message);
    console.error("[ErrorBoundary] Component stack:", errorInfo.componentStack);
  }

  render() {
    if (this.state.hasError) {
      const stack = this.state.errorInfo?.componentStack ?? "";
      // Extract the component name from the stack
      const componentMatch = stack.match(/at (\w+)/);
      const componentName = componentMatch?.[1] ?? "Unknown";

      return (
        <div className="flex-1 flex flex-col items-center justify-center gap-4 p-8">
          <div className="w-10 h-10 rounded-lg bg-error-soft flex items-center justify-center">
            <AlertTriangle size={20} className="text-error" />
          </div>
          <div className="text-center max-w-lg">
            <h2 className="text-base font-semibold text-text-primary">
              Something went wrong
            </h2>
            <p className="text-sm text-text-secondary mt-1.5 leading-relaxed">
              {this.state.error?.message ?? "An unexpected error occurred"}
            </p>
            <p className="text-xs text-text-faint mt-1">
              in {componentName}
            </p>
            {/* Show full component stack in development for debugging */}
            {stack && (
              <details className="mt-3 text-left">
                <summary className="text-xs text-text-faint cursor-pointer">Component stack</summary>
                <pre className="mt-1 text-[10px] text-text-faint bg-surface-sunken p-2 rounded overflow-x-auto whitespace-pre-wrap max-h-40 overflow-y-auto">
                  {stack}
                </pre>
              </details>
            )}
          </div>
          <button
            onClick={() => this.setState({ hasError: false, error: null, errorInfo: null })}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium bg-accent text-accent-text hover:bg-accent-hover transition-colors"
          >
            <RotateCcw size={14} />
            Try again
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
