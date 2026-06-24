#!/usr/bin/env bash
set -o errexit

python -m pip install --upgrade pip
pip install -r requirements_fastapi.txt
python init_db.py
