import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
});

// Add token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle 401 responses
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token');
      localStorage.removeItem('user');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// Auth
export const authAPI = {
  login: () => api.get('/auth/login'),
  emergencyLogin: (data) => api.post('/auth/login/emergency', data),
  logout: () => api.post('/auth/logout'),
  me: () => api.get('/auth/me'),
};

// Requests
export const requestsAPI = {
  list: (params) => api.get('/requests', { params }),
  get: (id) => api.get(`/requests/${id}`),
  create: (data) => api.post('/requests', data),
  cancel: (id) => api.post(`/requests/${id}/cancel`),
};

// Approvals
export const approvalsAPI = {
  pending: () => api.get('/approvals/pending'),
  action: (stepId, data) => api.post(`/approvals/${stepId}/action`, data),
  history: (requestId) => api.get(`/approvals/history/${requestId}`),
};

// Admin
export const adminAPI = {
  dashboard: () => api.get('/admin/dashboard'),
  users: (params) => api.get('/admin/users', { params }),
  updateUser: (id, data) => api.put(`/admin/users/${id}`, data),
  config: (category) => api.get('/admin/config', { params: { category } }),
  updateConfig: (key, value) => api.put(`/admin/config/${key}`, null, { params: { value } }),
  sshKeys: () => api.get('/admin/ssh-keys'),
  scripts: () => api.get('/admin/scripts'),
  workflow: () => api.get('/admin/workflow'),
  auditLogs: (params) => api.get('/admin/audit-logs', { params }),
};

// Reports
export const reportsAPI = {
  userAccess: (format) => api.get('/reports/user-access', { params: { format } }),
  sudoAccess: (format) => api.get('/reports/sudo-access', { params: { format } }),
  monthlyTrends: () => api.get('/reports/monthly-trends'),
};

// Search
export const searchAPI = {
  search: (q, field) => api.get('/search', { params: { q, field } }),
};

export default api;
