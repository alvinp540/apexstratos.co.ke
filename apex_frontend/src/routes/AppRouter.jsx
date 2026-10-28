import { BrowserRouter, Routes, Route } from 'react-router-dom'
import PrivateRoute from './PrivateRoute'
import AdminRoute from './AdminRoute'
import VendorRoute from './VendorRoute'

import LandingPage from '../pages/LandingPage'
import LoginPage from '../pages/LoginPage'
import RegisterPage from '../pages/RegisterPage'
import DashboardPage from '../pages/DashboardPage'
import CohortsPage from '../pages/CohortsPage'
import RankingsPage from '../pages/RankingsPage'
import VendorPortalPage from '../pages/VendorPortalPage'
import OpportunityCenterPage from '../pages/OpportunityCenterPage'
import NotificationsPage from '../pages/NotificationsPage'
import ProfileSettingsPage from '../pages/ProfileSettingsPage'
import AdminDashboardPage from '../pages/AdminDashboardPage'
import MentorshipPage from '../pages/MentorshipPage'
import TeamsPage from '../pages/TeamsPage'
import CommunitiesPage from '../pages/CommunitiesPage'
import RewardsPage from '../pages/RewardsPage'
import { introWatched } from '../components/common/HowItWorksTabs'
import { Navigate, useLocation } from 'react-router-dom'

function IntroGate({ children }) {
  const location = useLocation()
  if (!introWatched()) return <Navigate to={`/?watch=1&next=${encodeURIComponent(location.pathname)}`} replace />
  return children
}

export default function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/how-it-works" element={<Navigate to="/?watch=1" replace />} />
        <Route path="/login" element={<IntroGate><LoginPage /></IntroGate>} />
        <Route path="/register" element={<IntroGate><RegisterPage /></IntroGate>} />

        <Route element={<PrivateRoute />}>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/mentors" element={<MentorshipPage />} />
          <Route path="/teams" element={<TeamsPage />} />
          <Route path="/communities" element={<CommunitiesPage />} />
          <Route path="/cohorts" element={<CohortsPage />} />
          <Route path="/rankings" element={<RankingsPage />} />
          <Route path="/opportunities" element={<OpportunityCenterPage />} />
          <Route path="/rewards" element={<RewardsPage />} />
          <Route path="/notifications" element={<NotificationsPage />} />
          <Route path="/profile" element={<ProfileSettingsPage />} />
        </Route>

        <Route element={<VendorRoute />}>
          <Route path="/vendor" element={<VendorPortalPage />} />
        </Route>

        <Route element={<AdminRoute />}>
          <Route path="/admin" element={<AdminDashboardPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
