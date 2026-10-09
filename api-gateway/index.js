const express = require('express');
const { createProxyMiddleware } = require('http-proxy-middleware');
const morgan = require('morgan');
const cors = require('cors');
const helmet = require('helmet');
const { rateLimit } = require('express-rate-limit');
require('dotenv').config();

const PORT = process.env.PORT || 8000;

/**
 * Builds the gateway app. Settings are read from the environment when this is called,
 * which keeps the gateway testable (see index.test.js).
 */
function createApp() {
  const app = express();

  const envList = (name, fallback) =>
      (process.env[name] ? process.env[name].split(',') : fallback)
          .map((v) => v.trim())
          .filter(Boolean);

  // The gateway sits behind Railway's proxy; trust one hop so rate limiting
  // sees the real client IP instead of the proxy's.
  app.set('trust proxy', 1);

  // Security headers. CSP is skipped: this is a JSON API (and an optional Swagger page).
  app.use(helmet({
      contentSecurityPolicy: false,
      crossOriginResourcePolicy: { policy: 'cross-origin' },
  }));

  // CORS: only the known frontends may call the API from a browser.
  // Requests without an Origin header (server-to-server, webhooks, curl) are unaffected.
  const allowedOrigins = envList('CORS_ALLOWED_ORIGINS', [
      'https://www.ubuntunow.rw',
      'https://ubuntunow.rw',
      'https://dev.ubuntunow.rw',
      'https://admin.ubuntunow.rw',
      'https://ubuntu-nexus-front.vercel.app',
      'http://localhost:3000',
      'http://localhost:8080',
  ]);
  app.use(cors({
      origin: (origin, callback) => callback(null, !origin || allowedOrigins.includes(origin)),
      maxAge: 600,
  }));

  if (process.env.NODE_ENV !== 'test') {
      app.use(morgan(process.env.NODE_ENV === 'production' ? 'combined' : 'dev'));
    }

  // Reject oversized uploads before they are streamed to a service.
  const maxBodyBytes = Number(process.env.MAX_BODY_MB || 25) * 1024 * 1024;
  app.use((req, res, next) => {
      if (Number(req.headers['content-length'] || 0) > maxBodyBytes) {
          return res.status(413).json({ detail: 'Request body too large.' });
      }
      next();
  });

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

  app.get('/health', (req, res) => {
      res.json({ status: 'API Gateway is running' });
  });

  // Internal service-to-service endpoints must never be reachable from the public
  // internet. Services call each other directly via their *_SERVICE_URL, not through
  // this gateway. (They are also protected by the X-Internal-Token check.)
  app.use((req, res, next) => {
      if (/(^|\/)internal(\/|$)/.test(req.path)) {
          return res.status(404).json({ detail: 'Not found.' });
      }
      next();
  });

  // Rate limiting. Limits are per client IP and deliberately generous: many mobile
  // users share one carrier IP. Payment-provider webhooks are never limited.
  const limiterOptions = {
      standardHeaders: 'draft-7',
      legacyHeaders: false,
      message: { detail: 'Too many requests. Please try again later.' },
  };
  const isWebhook = (req) => req.path.startsWith('/api/v1/payments/payment/webhook/');

  // Credential / OTP endpoints: login, admin login, register, OTP send/verify/resend.
  const authLimiter = rateLimit({
      ...limiterOptions,
      windowMs: 15 * 60 * 1000,
      limit: Number(process.env.RATE_LIMIT_AUTH || 30),
      skip: (req) => req.method === 'OPTIONS' || isWebhook(req),
  });
  app.use([
      '/api/v1/users/login',
      '/api/v1/users/register',
      '/api/v1/users/admin/login',
      '/api/v1/users/admin/setup',
      '/api/v1/auth',
  ], authLimiter);

  // Everything else.
  app.use(rateLimit({
      ...limiterOptions,
      windowMs: 15 * 60 * 1000,
      limit: Number(process.env.RATE_LIMIT_GENERAL || 1000),
      skip: (req) => req.method === 'OPTIONS' || isWebhook(req),
  }));

  // Routing — order matters: more-specific paths first
  app.use(proxy('/api/v1/auth', services.auth));
  app.use(proxy('/api/v1/users/store', services.store));
  app.use(proxy('/api/v1/store', services.store));
  app.use(proxy('/api/v1/users', services.auth));
  app.use(proxy('/api/v1/products', services.product));
  app.use(proxy('/api/v1/orders', services.order));
  app.use(proxy('/api/v1/payments', services.payment));
  app.use(proxy('/api/v1/notifications', services.notification));

  // API docs are only exposed when explicitly enabled (EXPOSE_DOCS=true).
  if (process.env.EXPOSE_DOCS === 'true') {
      app.use(proxy('/api/docs', services.auth));
      app.use(proxy('/api/schema', services.auth));
      app.use(proxy('/api/redoc', services.auth));
  }

  return app;
}

module.exports = { createApp };

if (require.main === module) {
  createApp().listen(PORT, '0.0.0.0', () => {
    console.log(`API Gateway is running on port ${PORT}`);
  });
}
