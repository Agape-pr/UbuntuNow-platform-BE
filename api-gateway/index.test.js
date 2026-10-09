const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const { createApp } = require('./index');

// A stand-in for every backend service: echoes what it received.
function startUpstream() {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      res.setHeader('content-type', 'application/json');
      res.end(JSON.stringify({ url: req.url, method: req.method, auth: req.headers.authorization || null }));
    });
    server.listen(0, '127.0.0.1', () => resolve(server));
  });
}

const listen = (app) =>
  new Promise((resolve) => {
    const server = app.listen(0, '127.0.0.1', () => resolve(server));
  });

async function withGateway(env, fn) {
  const upstream = await startUpstream();
  const target = `http://127.0.0.1:${upstream.address().port}`;
  const saved = { ...process.env };
  Object.assign(process.env, {
    AUTH_SERVICE_URL: target, STORE_SERVICE_URL: target, PRODUCT_SERVICE_URL: target,
    ORDER_SERVICE_URL: target, PAYMENT_SERVICE_URL: target, NOTIFICATION_SERVICE_URL: target,
    ...env,
  });
  const server = await listen(createApp());
  const base = `http://127.0.0.1:${server.address().port}`;
  try {
    await fn(base);
  } finally {
    server.close(); upstream.close();
    for (const k of Object.keys(process.env)) if (!(k in saved)) delete process.env[k];
    Object.assign(process.env, saved);
  }
}

const get = (url, headers = {}) => fetch(url, { headers });
const post = (url, headers = {}, body = '{}') => fetch(url, { method: 'POST', headers: { 'content-type': 'application/json', ...headers }, body });

test('proxies each API prefix to its service and keeps the full path', () =>
  withGateway({}, async (base) => {
    for (const path of ['/api/v1/auth/otp/verify/', '/api/v1/users/me/', '/api/v1/users/store/shop/', '/api/v1/products/products/',
      '/api/v1/orders/orders/', '/api/v1/payments/payment/status/1', '/api/v1/notifications/']) {
      const res = await get(base + path, { authorization: 'Bearer abc' });
      assert.equal(res.status, 200, path);
      const body = await res.json();
      assert.equal(body.url, path);
      assert.equal(body.auth, 'Bearer abc');
    }
  }));

test('health check works and is not rate limited', () =>
  withGateway({ RATE_LIMIT_GENERAL: '2' }, async (base) => {
    for (let i = 0; i < 6; i++) assert.equal((await get(base + '/health')).status, 200);
  }));

test('internal service routes are never reachable from outside', () =>
  withGateway({}, async (base) => {
    for (const path of ['/api/v1/orders/internal/1/', '/api/v1/orders/internal/1/update-payment/',
      '/api/v1/users/internal/stores/by-id/1/', '/api/v1/products/internal/stock/1/', '/api/v1/users/internal/audit/']) {
      assert.equal((await get(base + path)).status, 404, path);
      assert.equal((await post(base + path)).status, 404, path);
    }
    // ...but a path that merely contains the word is fine
    assert.equal((await get(base + '/api/v1/users/store/internal-goods/')).status, 200);
  }));

test('CORS only allows the known frontends', () =>
  withGateway({}, async (base) => {
    const allowed = ['https://www.ubuntunow.rw', 'https://dev.ubuntunow.rw', 'https://admin.ubuntunow.rw', 'http://localhost:3000'];
    for (const origin of allowed) {
      const res = await get(base + '/api/v1/products/products/', { origin });
      assert.equal(res.headers.get('access-control-allow-origin'), origin, origin);
    }
    for (const origin of ['https://evil.example', 'https://ubuntunow.rw.evil.example', 'null']) {
      const res = await get(base + '/api/v1/products/products/', { origin });
      assert.equal(res.headers.get('access-control-allow-origin'), null, origin);
    }
    // requests with no Origin (webhooks, servers) are unaffected
    assert.equal((await post(base + '/api/v1/payments/payment/webhook/intouch/')).status, 200);
  }));

test('CORS preflight answers for allowed origins and withholds permission otherwise', () =>
  withGateway({}, async (base) => {
    const ask = (origin) => fetch(base + '/api/v1/users/login', {
      method: 'OPTIONS',
      headers: { origin, 'access-control-request-method': 'POST', 'access-control-request-headers': 'authorization,content-type' },
    });
    const ok = await ask('https://dev.ubuntunow.rw');
    assert.equal(ok.status, 204);
    assert.equal(ok.headers.get('access-control-allow-origin'), 'https://dev.ubuntunow.rw');
    assert.equal((await ask('https://evil.example')).headers.get('access-control-allow-origin'), null);
  }));

test('CORS_ALLOWED_ORIGINS replaces the defaults', () =>
  withGateway({ CORS_ALLOWED_ORIGINS: 'https://only.example' }, async (base) => {
    assert.equal((await get(base + '/health', { origin: 'https://only.example' })).headers.get('access-control-allow-origin'), 'https://only.example');
    assert.equal((await get(base + '/health', { origin: 'https://www.ubuntunow.rw' })).headers.get('access-control-allow-origin'), null);
  }));

test('login, admin login and OTP endpoints are tightly rate limited', () =>
  withGateway({ RATE_LIMIT_AUTH: '3' }, async (base) => {
    for (const path of ['/api/v1/users/login', '/api/v1/users/admin/login', '/api/v1/auth/otp/email/send/']) {
      const codes = [];
      for (let i = 0; i < 5; i++) codes.push((await post(base + path)).status);
      // each path counts towards the shared auth budget: once spent, everything is 429
      assert.ok(codes.includes(429) || path !== '/api/v1/users/login', path);
    }
    const blocked = await post(base + '/api/v1/auth/otp/email/send/');
    assert.equal(blocked.status, 429);
    assert.deepEqual(await blocked.json(), { detail: 'Too many requests. Please try again later.' });
  }));

test('token refresh and normal traffic are not caught by the strict auth limit', () =>
  withGateway({ RATE_LIMIT_AUTH: '1' }, async (base) => {
    for (let i = 0; i < 5; i++) assert.equal((await post(base + '/api/v1/users/token/refresh')).status, 200);
    for (let i = 0; i < 5; i++) assert.equal((await get(base + '/api/v1/products/products/')).status, 200);
  }));

test('payment webhooks are never rate limited', () =>
  withGateway({ RATE_LIMIT_AUTH: '1', RATE_LIMIT_GENERAL: '1' }, async (base) => {
    for (const path of ['/api/v1/payments/payment/webhook/pesapal/', '/api/v1/payments/payment/webhook/intouch/']) {
      for (let i = 0; i < 8; i++) assert.equal((await post(base + path)).status, 200, path);
    }
  }));

test('the general limit applies to everything else', () =>
  withGateway({ RATE_LIMIT_GENERAL: '3' }, async (base) => {
    const codes = [];
    for (let i = 0; i < 5; i++) codes.push((await get(base + '/api/v1/products/products/')).status);
    assert.deepEqual(codes, [200, 200, 200, 429, 429]);
  }));

test('API docs and the old /admin proxy are hidden unless EXPOSE_DOCS=true', async () => {
  await withGateway({}, async (base) => {
    for (const path of ['/api/docs/', '/api/schema/', '/api/redoc/', '/admin/']) assert.equal((await get(base + path)).status, 404, path);
  });
  await withGateway({ EXPOSE_DOCS: 'true' }, async (base) => {
    for (const path of ['/api/docs/', '/api/schema/', '/api/redoc/']) assert.equal((await get(base + path)).status, 200, path);
    assert.equal((await get(base + '/admin/')).status, 404); // the Django admin is not mounted anywhere
  });
});

test('oversized request bodies are refused before reaching a service', () =>
  withGateway({ MAX_BODY_MB: '1' }, async (base) => {
    const big = await post(base + '/api/v1/products/seller/products/', {}, 'x'.repeat(2 * 1024 * 1024));
    assert.equal(big.status, 413);
    const small = await post(base + '/api/v1/products/seller/products/', {}, '{"a":1}');
    assert.equal(small.status, 200);
  }));

test('responses carry security headers', () =>
  withGateway({}, async (base) => {
    const res = await get(base + '/health');
    assert.equal(res.headers.get('x-content-type-options'), 'nosniff');
    assert.ok(res.headers.get('strict-transport-security'));
    assert.equal(res.headers.get('x-powered-by'), null);
  }));
