// API Configuration
// This will be replaced during build/deployment
const API_CONFIG = {
    // For local development
    LOCAL: "http://127.0.0.1:8000",
    
    // For production - replace this with your Render backend URL after deployment
    PRODUCTION: "https://your-backend-name.onrender.com",
};

// Automatically detect environment
const isDevelopment = window.location.hostname === 'localhost' || 
                      window.location.hostname === '127.0.0.1' ||
                      window.location.hostname === '';

// Export the backend URL
const BACKEND_URL = isDevelopment ? API_CONFIG.LOCAL : API_CONFIG.PRODUCTION;

console.log('API Config loaded:', {
    isDevelopment,
    backendUrl: BACKEND_URL,
    hostname: window.location.hostname
});
