# Manual scripts

Ad-hoc scripts used while developing (smoke-testing a running stack, poking the Pesapal sandbox, etc.).
They are **not** part of the automated test suite and may need their paths adjusted before they run.

The real tests live in each service (`python manage.py test`) and in `api-gateway/` (`npm test`),
and run on every push through `.github/workflows/ci.yml`.
