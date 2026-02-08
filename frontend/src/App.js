import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Route, Routes, Link } from 'react-router-dom';
import Login from './components/Login';
import Alerts from './Alerts';
import AlertDetails from './AlertDetails';
import EndpointHealth from './EndpointHealth';
import Metrics from './Metrics';
import './App.css';

function App() {
  const [token, setToken] = useState(localStorage.getItem('token'));

  const handleLogin = (newToken) => {
    setToken(newToken);
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    setToken(null);
  };

  if (!token) {
    return <Login onLogin={handleLogin} />;
  }

  return (
    <Router future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <div className="App">
        <header className="App-header">
          <h1>API Degradation Detection System</h1>
          <nav>
            <Link to="/alerts">Alerts</Link> | <Link to="/endpoints">Endpoint Health</Link> | <Link to="/metrics">Metrics</Link>
            <button onClick={handleLogout} style={{ marginLeft: '20px' }}>Logout</button>
          </nav>
        </header>
        <main>
          <Routes>
            <Route path="/alerts" element={<Alerts />} />
            <Route path="/alerts/:id" element={<AlertDetails />} />
            <Route path="/metrics" element={<Metrics />} />
            <Route path="/endpoints" element={<EndpointHealth />} />
            <Route path="/" element={<Alerts />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}

export default App;