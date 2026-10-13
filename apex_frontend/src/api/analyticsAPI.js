import api from './axiosInstance'

export const getPublicPlatformStats = () => api.get('/analytics/public/')
export const getProfessionalAnalytics = () => api.get('/analytics/professional/me/')
