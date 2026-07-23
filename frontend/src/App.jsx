import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { AuthProvider, useAuth } from './hooks/useAuth';
import { ThemeProvider } from './hooks/useTheme';
import Layout from './components/layout/Layout';
import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/DashboardPage';
import NewRequestPage from './pages/NewRequestPage';
import RequestsPage from './pages/RequestsPage';
import RequestDetailPage from './pages/RequestDetailPage';
import ApprovalsPage from './pages/ApprovalsPage';
import AdminDashboardPage from './pages/AdminDashboardPage';
import AdminUsersPage from './pages/AdminUsersPage';
import AdminConfigPage from './pages/AdminConfigPage';
import AdminAuditPage from './pages/AdminAuditPage';
import ReportsPage from './pages/ReportsPage';

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="flex items-center justify-center h-screen"><div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div></div>;
  if (!user) return <Navigate to="/login" />;
  return children;
}

function AdminRoute({ children }) {
  const { user } = useAuth();
  if (!user || !['administrator', 'super_administrator'].includes(user.role)) {
    return <Navigate to="/dashboard" />;
  }
  return children;
}

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <Toaster position="top-right" />
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<ProtectedRoute><Layout /></ProtectedRoute>}>
            <Route index element={<Navigate to="/dashboard" />} />
            <Route path="dashboard" element={<DashboardPage />} />
            <Route path="requests" element={<RequestsPage />} />
            <Route path="requests/new" element={<NewRequestPage />} />
            <Route path="requests/:requestId" element={<RequestDetailPage />} />
            <Route path="approvals" element={<ApprovalsPage />} />
            <Route path="admin" element={<AdminRoute><AdminDashboardPage /></AdminRoute>} />
            <Route path="admin/users" element={<AdminRoute><AdminUsersPage /></AdminRoute>} />
            <Route path="admin/config" element={<AdminRoute><AdminConfigPage /></AdminRoute>} />
            <Route path="admin/audit" element={<AdminRoute><AdminAuditPage /></AdminRoute>} />
            <Route path="reports" element={<AdminRoute><ReportsPage /></AdminRoute>} />
          </Route>
        </Routes>
      </AuthProvider>
    </ThemeProvider>
  );
}
