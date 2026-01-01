import React from 'react';
import { BrowserRouter as Router, Route, Routes, Link } from 'react-router-dom';
import Alerts from './Alerts';
import Metrics from './Metrics';
import './App.css';

function App() {
  return (
    <Router future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <div className="App">
        <header className="App-header">
          <h1>Explainable Early-Warning System for API Degradation</h1>
          <nav>
            <Link to="/alerts">Alerts</Link> | <Link to="/metrics">Metrics</Link>
          </nav>
        </header>
        <main>
          <Routes>
            <Route path="/alerts" element={<Alerts />} />
            <Route path="/metrics" element={<Metrics />} />
            <Route path="/" element={<Alerts />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}

export default App;