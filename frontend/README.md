# API Degradation Detection - Frontend

A React-based dashboard for monitoring API degradation alerts and metrics.

## Features

- **Alerts Dashboard**: View all active alerts with severity levels, explanations, and affected metrics
- **Expandable Details**: Click "Expand" to see full alert explanations with recommendations
- **Metrics Visualization**: Chart showing latency trends over time
- **Real-time Updates**: Refresh button to fetch latest data

## Development

The frontend includes mock data for development when the backend API is not available.

### Running Locally

```bash
cd frontend
npm install
npm start
```

The app will run on `http://localhost:3000` and proxy API requests to `http://localhost:8001`.

### Backend Integration

When the backend API is running, the frontend will fetch real data. Otherwise, it falls back to mock data for development.

## Components

- **Alerts.js**: Displays alert table with expandable explanations
- **Metrics.js**: Shows latency charts for endpoint monitoring
- **App.js**: Main routing and navigation