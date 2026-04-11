# Manthan Python sandbox image — SPEC §4.3
#
# Runs user/agent-generated Python code against mounted Parquet datasets
# with no network access and bounded resources. Built on python:3.13-slim
# for a small footprint.

FROM python:3.13-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /sandbox

COPY requirements.txt /sandbox/requirements.txt
RUN pip install --no-cache-dir -r /sandbox/requirements.txt

COPY prelude.py /sandbox/prelude.py

# /data is mounted read-only at run time; /output is writable.
RUN mkdir -p /data /output

# The sandbox is invoked by docker exec via `python -i /sandbox/prelude.py`
# or `python -c "<user_code>"`; there is no default CMD so the host
# controls the lifetime.
