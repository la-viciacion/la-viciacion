#!/bin/sh
alembic upgrade head
uvicorn src.main:app --log-level warning --proxy-headers --host 0.0.0.0 --port 5000
