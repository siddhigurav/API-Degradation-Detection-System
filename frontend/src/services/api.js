import axios from 'axios';

const api = axios.create({
  baseURL: '/api/v1',
});

// Add token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export const getHealth = () => api.get('/health');
export const getMetrics = (serviceName, endpoint) => api.get(`/metrics/${serviceName}/${endpoint}`);
export const getAlerts = () => api.get('/alerts');
export const ingestLog = (log) => api.post('/logs', log);

export default api;