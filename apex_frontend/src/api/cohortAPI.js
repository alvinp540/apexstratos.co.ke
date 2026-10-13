import api from './axiosInstance'

export const getCohorts = () => api.get('/cohorts/')
export const getDailyCohorts = () => api.get('/cohorts/today/')
export const getCohort = (id) => api.get(`/cohorts/${id}/`)
export const enrollCohort = (id) => api.post(`/cohorts/${id}/enroll/`)
export const getAssessments = (cohortId) => api.get(`/cohorts/${cohortId}/assessments/`)
export const startAssessment = (assessmentId) => api.post(`/cohorts/assessments/${assessmentId}/start/`)
export const submitAssessment = (assessmentId, answers, videoData) =>
  api.post(`/cohorts/assessments/${assessmentId}/submit/`, { answers, ...videoData })
export const getCohortLeaderboard = (cohortId) => api.get(`/cohorts/${cohortId}/leaderboard/`)
export const sendHeartbeat = (attemptId, data) =>
  api.post(`/cohorts/attempts/${attemptId}/heartbeat/`, data)
export const allocateCohortRewards = (cohortId) =>
  api.post(`/cohorts/admin/${cohortId}/allocate-rewards/`)
export const runMentorshipFollowUp = (cohortId) =>
  api.post(`/cohorts/admin/${cohortId}/mentorship-follow-up/`)
export const listWhatsAppInvites = () => api.get('/cohorts/mentorship/whatsapp-invites/')
export const requestWhatsAppInvite = (payload) => api.post('/cohorts/mentorship/whatsapp-invites/', payload)

export const getMainContestPayments = () => api.get('/cohorts/payments/main-contest/')
export const submitMainContestPayment = (payload) => api.post('/cohorts/payments/main-contest/', payload)
export const getMainContestAssessments = () => api.get('/cohorts/contests/')
export const startMainContestAssessment = (assessmentId) =>
  api.post(`/cohorts/contests/${assessmentId}/start/`)
export const submitMainContestAttempt = (attemptId, answers) =>
  api.post(`/cohorts/contests/attempts/${attemptId}/submit/`, { answers })
export const getMainContestPaymentReviews = () =>
  api.get('/cohorts/admin/payments/main-contest/')
export const decideMainContestPayment = (paymentId, payload) =>
  api.post(`/cohorts/admin/payments/main-contest/${paymentId}/decision/`, payload)
