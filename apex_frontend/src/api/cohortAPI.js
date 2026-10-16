import api from './axiosInstance'

export const getCohorts = () => api.get('/cohorts/')
export const getDailyCohorts = () => api.get('/cohorts/today/')
export const getCohort = (id) => api.get(`/cohorts/${id}/`)
export const enrollCohort = (id) => api.post(`/cohorts/${id}/enroll/`)
export const getAssessments = (cohortId) => api.get(`/cohorts/${cohortId}/assessments/`)
export const startAssessment = (assessmentId) => api.post(`/cohorts/assessments/${assessmentId}/start/`)
export const submitAssessment = (assessmentId, answers) =>
  api.post(`/cohorts/assessments/${assessmentId}/submit/`, { answers })
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
export const getMainContestLibrary = (params = {}) => api.get('/cohorts/contests/library/', { params })
export const getMyContestCycleLeaderboard = () => api.get('/cohorts/contests/leaderboard/me/')
export const startMainContestAssessment = (assessmentId) =>
  api.post(`/cohorts/contests/${assessmentId}/start/`)
export const saveMainContestAttemptAnswers = (attemptId, answers, reasoning = {}) =>
  api.post(`/cohorts/contests/attempts/${attemptId}/answers/`, { answers, reasoning })
export const submitMainContestAttempt = (attemptId, answers, reasoning = {}) =>
  api.post(`/cohorts/contests/attempts/${attemptId}/submit/`, { answers, reasoning })
export const getMainContestPaymentReviews = () =>
  api.get('/cohorts/admin/payments/main-contest/')
export const decideMainContestPayment = (paymentId, payload) =>
  api.post(`/cohorts/admin/payments/main-contest/${paymentId}/decision/`, payload)
export const getSupportPrograms = () => api.get('/cohorts/support/programs/')
export const getSupportApplications = () => api.get('/cohorts/support/applications/')
export const submitSupportApplicationInformation = (applicationId, payload) =>
  api.patch(`/cohorts/support/applications/${applicationId}/information/`, payload)
export const applyForSupportProgram = (programId, payload) =>
  api.post(`/cohorts/support/programs/${programId}/applications/`, payload)
export const getAdminSupportApplications = () => api.get('/cohorts/admin/support/applications/')
export const decideSupportApplication = (applicationId, payload) =>
  api.post(`/cohorts/admin/support/applications/${applicationId}/decision/`, payload)
