import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { ProtectedRoute } from './components/layout/ProtectedRoute'
import { RequireManager } from './components/layout/RequireManager'
import { RestaurantLayout } from './components/layout/RestaurantLayout'
import { AuthProvider } from './context/AuthContext'
import { AlertsPage } from './pages/AlertsPage'
import { AnalyticsPage } from './pages/AnalyticsPage'
import { LoginPage, RegisterPage } from './pages/AuthPages'
import { ChangePasswordPage } from './pages/ChangePasswordPage'
import { DashboardPage } from './pages/DashboardPage'
import { FloorPage } from './pages/FloorPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { ProfilePage } from './pages/ProfilePage'
import { SettingsPage } from './pages/SettingsPage'
import { SetupPage } from './pages/SetupPage'
import { StaffPage } from './pages/StaffPage'

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: true, staleTime: 2000 } },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/change-password" element={<ProtectedRoute><ChangePasswordPage /></ProtectedRoute>} />
            <Route path="/dashboard" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />
            <Route path="/profile" element={<ProtectedRoute><ProfilePage /></ProtectedRoute>} />
            <Route path="/r/:id" element={<ProtectedRoute><RestaurantLayout /></ProtectedRoute>}>
              <Route index element={<Navigate to="floor" replace />} />
              <Route path="floor" element={<FloorPage />} />
              <Route path="alerts" element={<AlertsPage />} />
              <Route path="analytics" element={<RequireManager><AnalyticsPage /></RequireManager>} />
              <Route path="setup" element={<RequireManager><SetupPage /></RequireManager>} />
              <Route path="staff" element={<RequireManager><StaffPage /></RequireManager>} />
              <Route path="settings" element={<RequireManager><SettingsPage /></RequireManager>} />
            </Route>
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  )
}
