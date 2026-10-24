import { NavLink, Outlet } from 'react-router-dom';

export default function Layout() {
  return (
    <main className="shell">
      <header className="topbar">
        <NavLink className="brand" to="/" aria-label="Eagle Eye home">
          <span className="brand-mark">E</span>
          <span>EAGLE EYE</span>
        </NavLink>
        <nav className="nav">
          <NavLink to="/" end>Dashboard</NavLink>
          <NavLink to="/inspect">New inspection</NavLink>
        </nav>
      </header>
      <Outlet />
      <footer>
        <span>EAGLE EYE · HACKATHON PROTOTYPE</span>
        <span>AI-assisted · Evidence-led · Human-reviewed</span>
      </footer>
    </main>
  );
}
