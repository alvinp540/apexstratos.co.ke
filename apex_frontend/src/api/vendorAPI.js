import api from './axiosInstance'

export const getVendorJobs = () => api.get('/vendor/jobs/')
export const createJob = (data) => api.post('/vendor/jobs/', data)
export const getJob = (id) => api.get(`/vendor/jobs/${id}/`)
export const updateJob = (id, data) => api.patch(`/vendor/jobs/${id}/`, data)
export const deleteJob = (id) => api.delete(`/vendor/jobs/${id}/`)
export const publishJob = (id) => api.post(`/vendor/jobs/${id}/publish/`)
export const rateJob = (id, data) => api.post(`/vendor/jobs/${id}/rate/`, data)
export const getJobMatches = (id) => api.get(`/vendor/jobs/${id}/matches/`)
export const getVendorDashboard = () => api.get('/vendor/dashboard/')
export const getProfessionalOpportunities = (params) => api.get('/vendor/opportunities/', { params })
