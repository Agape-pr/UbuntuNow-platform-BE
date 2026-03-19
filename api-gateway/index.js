const express = require('express');
const { createProxyMiddleware } = require('http-proxy-middleware');
const morgan = require('morgan');
const cors = require('cors');
require('dotenv').config();

const app = express();
const PORT = process.env.PORT || 8000;

// Middleware
app.use(cors());
app.use(morgan('dev'));

// Service URLs (could be passed via environment variables)
const services = {
    auth: process.env.AUTH_SERVICE_URL || 'http://localhost:8001',
    store: process.env.STORE_SERVICE_URL || 'http://localhost:8002',
    product: process.env.PRODUCT_SERVICE_URL || 'http://localhost:8003',
    order: process.env.ORDER_SERVICE_URL || 'http://localhost:8004',
    payment: process.env.PAYMENT_SERVICE_URL || 'http://localhost:8005',
    notification: process.env.NOTIFICATION_SERVICE_URL || 'http://localhost:8006',
};

// Proxy helper — uses pathFilter so the full original URL is forwarded to the backend.
// http-proxy-middleware v3 strips the Express mount-path by default;
// using app.use('/') + pathFilter avoids that behaviour entirely.
const proxy = (pathPrefix, target) =>
    createProxyMiddleware({
        target,
        changeOrigin: true,
        pathFilter: pathPrefix,
    });

// Routing — order matters: more-specific paths first
app.use(proxy('/api/v1/auth', services.auth));
app.use(proxy('/api/v1/users/store', services.store));
app.use(proxy('/api/v1/store', services.store));
app.use(proxy('/api/v1/users', services.auth));
app.use(proxy('/api/v1/products', services.product));
app.use(proxy('/api/v1/orders', services.order));
app.use(proxy('/api/v1/payments', services.payment));
app.use(proxy('/api/v1/notifications', services.notification));

// Admin, Docs, and fallback
app.use(proxy('/admin', services.auth));
app.use(proxy('/api/docs', services.auth));
app.use(proxy('/api/schema', services.auth));
app.use(proxy('/api/redoc', services.auth));

app.get('/health', (req, res) => {
    res.json({ status: 'API Gateway is running' });
});

app.listen(PORT, '0.0.0.0', () => {
    console.log(`API Gateway is running on port ${PORT}`);
});
