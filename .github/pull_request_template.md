## What and why

<!-- One or two sentences. PR title in Conventional Commits: `feat(front): ...` -->

## Checklist

- [ ] Tests added or updated for the logic I touched
- [ ] Docs (`docs/`) updated if behaviour or operations changed
- [ ] Schema change? Follows [docs/desarrollo/migrations.md](../docs/desarrollo/migrations.md) (single head, idempotent, never applied to real data by me)
- [ ] New endpoint? Authorization in the API and `test_endpoint_security.py` still green
- [ ] New env var? Added to `.env.template` and `config.py`
