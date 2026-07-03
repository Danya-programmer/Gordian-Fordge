import { Outlet } from 'react-router-dom'
import { Header } from '@widgets/Header/Header'

export function Layout() {
  return (
    <div className="d-flex flex-column min-vh-100">
      <Header />
      <main className="flex-grow-1 container py-4">
        <Outlet />
      </main>
    </div>
  )
}