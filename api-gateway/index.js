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

// Routing
app.use('/api/v1/auth', createProxyMiddleware({ target: services.auth, changeOrigin: true }));
app.use('/api/v1/users/store', createProxyMiddleware({ target: services.store, changeOrigin: true }));
app.use('/api/v1/users', createProxyMiddleware({ target: services.auth, changeOrigin: true }));
app.use('/api/v1/products', createProxyMiddleware({ target: services.product, changeOrigin: true }));
app.use('/api/v1/orders', createProxyMiddleware({ target: services.order, changeOrigin: true }));
app.use('/api/v1/payments', createProxyMiddleware({ target: services.payment, changeOrigin: true }));
app.use('/api/v1/notifications', createProxyMiddleware({ target: services.notification, changeOrigin: true }));

// Admin, Docs, and fallback
app.use('/admin', createProxyMiddleware({ target: services.auth, changeOrigin: true }));
app.use('/api/docs', createProxyMiddleware({ target: services.auth, changeOrigin: true }));

app.get('/health', (req, res) => {
    res.json({ status: 'API Gateway is running' });
});

app.listen(PORT, () => {
    console.log(`API Gateway is running on port ${PORT}`);
});
