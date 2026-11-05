import { LogOut, UserRound } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../../hooks/useAuth'

export function TopBar() {
  const { logout } = useAuth()
  const navigate = useNavigate()
  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 sm:px-6">
        <Link to="/dashboard" className="text-lg font-bold text-indigo-800">
          TableSense
        </Link>
        <div className="flex items-center gap-1">
          <Link
            to="/profile"
            aria-label="Profile"
            className="flex h-11 w-11 items-center justify-center rounded-full text-slate-700 hover:bg-slate-100"
          >
            <UserRound size={20} aria-hidden="true" />
          </Link>
          <button
            type="button"
            aria-label="Log out"
            onClick={() => void logout().then(() => navigate('/login'))}
            className="flex h-11 w-11 items-center justify-center rounded-full text-slate-700 hover:bg-slate-100"
          >
            <LogOut size={20} aria-hidden="true" />
          </button>
        </div>
      </div>
    </header>
  )
}
