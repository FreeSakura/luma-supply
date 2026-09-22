# Contributing

Keep changes focused on a reproducible problem or a concrete business flow.
Explain the trigger, expected behavior and relevant verification in your change.
Do not add broad defensive layers or tests that merely repeat trivial assignments.

## Local checks

Use Python 3.10+ and Node 22+. Follow `docs/DEPLOYMENT.md` to create the virtual
environment, install pinned dependencies and run the application.

```sh
python -m pytest -q
cd web
npm ci
npm run build
```

Changes to native mini-programs belong in `miniapps/shared`; regenerate both
projects with `python -m scripts.build_miniapps` and include generated changes.
Tests use a temporary database. Do not reset a contributor's runtime database
to run tests.

## Data and evidence

Never commit `.env`, tokens, uploaded images, business databases, student IDs,
customer contact details or original course documents. Keep reports and experiment
outputs in `local-only/` or `output/`. Use synthetic fixtures for regression tests.
Report dataset provenance and distinguish offline checks from real integration.
Do not claim synthetic retrieval accuracy as real-photo performance.

By submitting original contributions, you agree to their distribution under the
repository's MIT license. Keep upstream notices for any third-party code.
