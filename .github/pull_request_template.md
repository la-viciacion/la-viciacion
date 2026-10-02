## What and why

<!-- One or two sentences. The PR title is the squash commit: `feat(front): ...` -->

## Checklist

- [ ] Tests added or updated for the logic I touched
- [ ] Docs (`docs/`) updated if behaviour or operations changed
- [ ] Schema change? Follows [docs/migrations.md](../docs/migrations.md) (single head, idempotent, never applied to real data by me)
- [ ] New endpoint? Authorization in the API and `test_endpoint_security.py` still green
- [ ] New env var? Added to `.env.template` and `config.py`
