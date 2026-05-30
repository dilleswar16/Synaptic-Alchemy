import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Component, type ReactNode } from 'react'
import { ThemeProvider } from './context/ThemeContext'
import DashboardPage from './pages/DashboardPage'
import InvestigationsPage from './pages/InvestigationsPage'
import InvestigationDetailPage from './pages/InvestigationDetailPage'
import FixStrategyPage from './pages/FixStrategyPage'
import CorvinCommandPage from './pages/CorvinCommandPage'
import PredictiveAnalyticsPage from './pages/PredictiveAnalyticsPage'
import ApplicationsPage from './pages/ApplicationsPage'
import SloMonitoringPage from './pages/SloMonitoringPage'
import ValidationsPage from './pages/ValidationsPage'
import NotFoundPage from './pages/NotFoundPage'

// ── Global error boundary ─────────────────────────────────────────────────────

class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  constructor(props: { children: ReactNode }) {
    super(props)
    this.state = { error: null }
  }
  static getDerivedStateFromError(error: Error) {
    return { error }
  }
  render() {
    if (this.state.error) {
      return (
        <div style={{
          minHeight: '100vh', display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center', gap: 16,
          background: 'var(--c-bg)', color: 'var(--c-text)',
          fontFamily: 'var(--font-display)',
        }}>
          <div style={{ fontSize: '2rem', color: 'var(--c-signal)' }}>⚠</div>
          <div style={{ fontWeight: 800, fontSize: '1.1rem' }}>Something went wrong</div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: 'var(--c-text-muted)', maxWidth: 480, textAlign: 'center' }}>
            {this.state.error.message}
          </div>
          <button
            className="btn-primary"
            onClick={() => { this.setState({ error: null }); window.location.href = '/' }}
          >
            Return to Dashboard
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

export default function App() {
  return (
    <ThemeProvider>
      <ErrorBoundary>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/predictive-analytics" element={<PredictiveAnalyticsPage />} />
            <Route path="/investigations" element={<InvestigationsPage />} />
            <Route path="/investigations/:id" element={<InvestigationDetailPage />} />
            <Route path="/investigations/:id/fix-strategy" element={<FixStrategyPage />} />
            <Route path="/corvin" element={<CorvinCommandPage />} />
            <Route path="/applications" element={<ApplicationsPage />} />
            <Route path="/applications/:id" element={<ApplicationsPage />} />
            <Route path="/slo" element={<SloMonitoringPage />} />
            <Route path="/validations" element={<ValidationsPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </BrowserRouter>
      </ErrorBoundary>
    </ThemeProvider>
  )
}
