import { Component, type ReactNode } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex-1 flex flex-col items-center justify-center gap-4 p-8">
          <div className="w-10 h-10 rounded-lg bg-error-soft flex items-center justify-center">
            <AlertTriangle size={20} className="text-error" />
          </div>
          <div className="text-center max-w-sm">
            <h2 className="text-base font-semibold text-text-primary">
              Something went wrong
            </h2>
            <p className="text-sm text-text-secondary mt-1.5 leading-relaxed">
              {this.state.error?.message ?? "An unexpected error occurred"}
            </p>
          </div>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
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
