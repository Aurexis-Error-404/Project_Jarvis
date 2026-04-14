// src/index.jsx — React entry point
// Mounts the App component into the #root div in index.html

import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './styles/index.css';

// Mount React app
const container = document.getElementById('root');
const root = createRoot(container);
root.render(<App />);

console.log('[JARVIS] React app mounted');
