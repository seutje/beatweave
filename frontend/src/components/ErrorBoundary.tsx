import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = {};

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Uncaught Beatweave UI error", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <main className="fatal-error">
          <div className="fatal-error__panel">
            <span className="brand-mark">⌁</span>
            <h1>Beatweave hit an unexpected error</h1>
            <p>{this.state.error.message}</p>
            <button onClick={() => window.location.reload()}>
              Reload application
            </button>
          </div>
        </main>
      );
    }
    return this.props.children;
  }
}
