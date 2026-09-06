import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import { Dashboard } from './pages/Dashboard';
import { Compare } from './pages/Compare';
import { QueryDetail } from './pages/QueryDetail';
import { Datasets } from './pages/Datasets';
import { Evaluate } from './pages/Evaluate';
import { Configs } from './pages/Configs';
import { Sweeps } from './pages/Sweeps';

const navItems = [
  { to: '/', label: 'Dashboard' },
  { to: '/evaluate', label: 'Evaluate' },
  { to: '/sweeps', label: 'Sweeps' },
  { to: '/compare', label: 'Compare' },
  { to: '/datasets', label: 'Datasets' },
  { to: '/configs', label: 'Configs' },
];

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-slate-50">
        {/* Navigation */}
        <nav className="bg-white border-b border-gray-200">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex items-center justify-between h-16">
              <div className="flex items-center gap-8">
                <span className="text-lg font-bold text-gray-900">RAG Eval</span>
                <div className="flex gap-1">
                  {navItems.map((item) => (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      end={item.to === '/'}
                      className={({ isActive }) =>
                        `px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                          isActive
                            ? 'bg-blue-50 text-blue-700'
                            : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                        }`
                      }
                    >
                      {item.label}
                    </NavLink>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </nav>

        {/* Main Content */}
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/evaluate" element={<Evaluate />} />
            <Route path="/sweeps" element={<Sweeps />} />
            <Route path="/compare" element={<Compare />} />
            <Route path="/datasets" element={<Datasets />} />
            <Route path="/configs" element={<Configs />} />
            <Route path="/run/:runId" element={<QueryDetail />} />
            <Route path="/run/:runId/query/:resultId" element={<QueryDetail />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
