import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import AppLayout from './components/Layout/AppLayout';
import DashboardPage from './pages/DashboardPage';
import LoginPage from './pages/LoginPage';
import useAuthStore from './stores/useAuthStore';
import useAppStore from './stores/useAppStore';

export default function App() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const apmId = useAuthStore((s) => s.apmId);
  const setApmId = useAppStore((s) => s.setApmId);
  const connectWebSocket = useAppStore((s) => s.connectWebSocket);
  const disconnectWebSocket = useAppStore((s) => s.disconnectWebSocket);

  // Sync auth apmId into app store so dashboard/chat use the real identity
  useEffect(() => {
    if (apmId) setApmId(apmId);
  }, [apmId, setApmId]);

  // Connect WebSocket when authenticated
  useEffect(() => {
    if (isAuthenticated) {
      connectWebSocket();
      return () => disconnectWebSocket();
    }
  }, [isAuthenticated, connectWebSocket, disconnectWebSocket]);

  if (!isAuthenticated) {
    return <LoginPage />;
  }

  return (
    <BrowserRouter>
      <AppLayout>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AppLayout>
    </BrowserRouter>
  );
}
