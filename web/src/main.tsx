import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './app.css';
import App from './App.tsx';
import { RootBoundary } from './components/ErrorBoundary';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RootBoundary>
      <App />
    </RootBoundary>
  </StrictMode>,
);
