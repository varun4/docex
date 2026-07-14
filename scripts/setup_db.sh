#!/bin/bash
set -e

sudo -u postgres psql -c "CREATE USER docsextract WITH PASSWORD 'docsextract';" 2>/dev/null || echo "User 'docsextract' already exists"
sudo -u postgres psql -c "CREATE DATABASE docex OWNER docsextract;" 2>/dev/null || echo "Database 'docex' already exists"

echo "PostgreSQL setup complete."
