import { NavLink } from 'react-router-dom'

export function Header() {
  return (
    <nav className="navbar navbar-expand-lg navbar-dark bg-dark">
      <div className="container">
        <span className="navbar-brand mb-0 h1">Gordian Forge - AI-разведка знаний для Норникеля</span>
        <div className="navbar-nav flex-row gap-2">
          <NavLink
            to="/"
            className={({ isActive }) =>
              `btn btn-sm ${isActive ? 'btn-primary' : 'btn-outline-light'}`
            }
            end
          >
            💬 Чат
          </NavLink>
          <NavLink
            to="/upload"
            className={({ isActive }) =>
              `btn btn-sm ${isActive ? 'btn-primary' : 'btn-outline-light'}`
            }
          >
            📁 Загрузка файлов
          </NavLink>
        </div>
      </div>
    </nav>
  )
}