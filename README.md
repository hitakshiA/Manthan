# Manthan

**Seamless Self-Service Intelligence — Talk to Data.**

Manthan is a data layer that ingests arbitrary datasets, profiles and annotates
them autonomously, and exposes them to downstream analysis agents through a
small set of well-defined tools. Built for the NatWest *Code for Purpose* India
Hackathon — Problem Statement: *Talk to Data*.

## Status

Early scaffolding. Project structure, dependencies, and the `/health` endpoint
are in place. The ingestion, profiling, semantic, materialization, tools, and
API modules are stubbed and being built out in subsequent iterations. See
[`SPEC.md`](SPEC.md) for the engineering specification and
[`AGENTS.md`](AGENTS.md) for contribution guidelines.

## Requirements

- Python 3.12 or newer
- Docker (required later for the Python sandbox used by the `run_python` tool)

## Install

```bash
git clone https://github.com/hitakshiA/Manthan.git
cd Manthan
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # then fill in real values
```

## Run

```bash
uvicorn src.main:app --reload
```

Once running, verify liveness:

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

## Tests

```bash
pytest tests/ -v
```

## Limitations

- Only the `/health` endpoint is wired up. Ingestion, profiling, semantic
  annotation, materialization, and agent tool endpoints are not yet
  implemented.
- No frontend yet.
- No hosted deployment yet.

## Future Improvements

See [`SPEC.md`](SPEC.md) §7.3 for the intentional non-goals and the growth
path (multi-dataset, multi-tenant, cloud deployment, etc.).

## License

Apache License 2.0. See [`LICENSE`](LICENSE).
