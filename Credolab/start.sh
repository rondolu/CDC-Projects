#!/bin/bash
gunicorn --timeout 0  --threads=8 --worker-class=gthread main:app
