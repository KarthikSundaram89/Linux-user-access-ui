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

// Handle 401 responses - try refresh before redirect
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      try {
        const refreshRes = await api.post('/auth/refresh');
        const newToken = refreshRes.data.access_token;
        if (newToken) {
          localStorage.setItem('access_token', newToken);
          originalRequest.headers.Authorization = `Bearer ${newToken}`;
          return api(originalRequest);
        }
      } catch (refreshErr) {
        // Refresh failed - redirect to login
      }
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
  refresh: () => api.post('/auth/refresh'),
  me: () => api.get('/auth/me'),
};

// Requests
export const requestsAPI = {
  list: (params) => api.get('/requests', { params }),
  get: (id) => api.get(`/requests/${id}`),
  create: (data) => api.post('/requests', data),
  cancel: (id) => api.post(`/requests/${id}/cancel`),
  retry: (id) => api.post(`/requests/${id}/retry`),
  clone: (id) => api.post(`/requests/${id}/clone`),
  saveDraft: (data) => api.post('/requests/draft', data),
  submitDraft: (id) => api.post(`/requests/${id}/submit`),
  uploadCSV: (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/requests/upload-csv', formData, { headers: { 'Content-Type': 'multipart/form-data' } });
  },
};

// Approvals
export const approvalsAPI = {
  pending: () => api.get('/approvals/pending'),
  action: (stepId, data) => api.post(`/approvals/${stepId}/action`, data),
  history: (requestId) => api.get(`/approvals/history/${requestId}`),
  comments: (requestId) => api.get(`/approvals/comments/${requestId}`),
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
  emailTemplates: () => api.get('/admin/email-templates'),
  createEmailTemplate: (data) => api.post('/admin/email-templates', null, { params: data }),
  updateEmailTemplate: (id, data) => api.put(`/admin/email-templates/${id}`, null, { params: data }),
  deleteEmailTemplate: (id) => api.delete(`/admin/email-templates/${id}`),
  rotationStatus: () => api.get('/admin/rotation-status'),
  chartMonthly: () => api.get('/admin/charts/monthly-requests'),
  chartTopServers: () => api.get('/admin/charts/top-servers'),
  chartApprovalSLA: () => api.get('/admin/charts/approval-sla'),
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

// Servers (EC2 Inventory Lookup)
export const serversAPI = {
  lookup: (servers) => api.post('/servers/lookup', { servers }),
  lookupSingle: (identifier) => api.get(`/servers/lookup/${identifier}`),
  inventoryStats: () => api.get('/servers/inventory/stats'),
};

export default api;
