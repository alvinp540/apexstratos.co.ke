import { Navigate, Route, Routes } from 'react-router-dom'
import Shell from './components/Shell'
import { useAuth } from './context/AuthContext'
import { Loading } from './components/States'
import { Admin, Merit, Notifications, Profile } from './pages/AccountPages'
import ContestPage from './pages/ContestPage'
import { AreaTutorials, Mentorship, Opportunities, SponsoredView, StudyAreas, TutorialDetail, Tutorials } from './pages/LearningPages'
import { AuthPage, Dashboard, Landing } from './pages/PublicPages'

function Protected() {
  const { user, loading } = useAuth()
  if (loading) return <div className="full-page-loading"><Loading /></div>
  if (!user) return <Navigate to="/login" replace />
  return <Shell />
}

export default function App() {
  return <Routes>
    <Route path="/" element={<Landing />} />
    <Route path="/login" element={<AuthPage mode="login" />} />
    <Route path="/register" element={<AuthPage mode="register" />} />
    <Route element={<Protected />}>
      <Route path="/dashboard" element={<Dashboard />} />
      <Route path="/study" element={<StudyAreas />} />
      <Route path="/study/:area" element={<AreaTutorials />} />
      <Route path="/tutorials" element={<Tutorials />} />
      <Route path="/tutorials/:id" element={<TutorialDetail />} />
      <Route path="/mentorship" element={<Mentorship />} />
      <Route path="/sponsored-view" element={<SponsoredView />} />
      <Route path="/contests" element={<ContestPage />} />
      <Route path="/merit" element={<Merit />} />
      <Route path="/opportunities" element={<Opportunities />} />
      <Route path="/profile" element={<Profile />} />
      <Route path="/notifications" element={<Notifications />} />
      <Route path="/admin" element={<Admin />} />
    </Route>
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes>
}
