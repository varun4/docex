#!/bin/bash
set -euo pipefail

REPO_URL="https://github.com/varun4/docex.git"
DOMAIN=""
EMAIL=""
SEED=false

usage() {
    echo "Usage: $0 [--domain DOMAIN] [--email EMAIL] [--seed]"
    echo ""
    echo "  --domain DOMAIN   Public domain for HTTPS (e.g. docex.example.com)"
    echo "  --email EMAIL     Let's Encrypt email for cert notifications"
    echo "  --seed            Import ~2,800 seed documents from Stardew Valley Wiki"
    exit 1
}

while [ $# -gt 0 ]; do
    case "$1" in
        --domain) DOMAIN="$2"; shift 2 ;;
        --email)  EMAIL="$2";  shift 2 ;;
        --seed)   SEED=true;   shift ;;
        *) usage ;;
    esac
done

# --- Detect platform ---
ARCH=$(uname -m)
RAM_MB=$(awk '/MemTotal/ {printf "%d", $2/1024}' /proc/meminfo 2>/dev/null || echo 1024)
echo "Architecture: $ARCH  |  RAM: ${RAM_MB}MB"

if [ "$RAM_MB" -lt 1500 ]; then
    echo "WARNING: <1.5GB RAM detected. Elasticsearch + Kafka may struggle."
    echo "  Oracle Free Tier ARM (Ampere A1, 24GB) is strongly recommended."
    echo "  Continuing anyway..."
fi

# --- Install Docker if missing ---
if ! command -v docker &>/dev/null; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker "$USER"
    echo "Docker installed. You may need to log out and back in for group changes."
fi

if ! docker compose version &>/dev/null; then
    echo "Docker Compose plugin not found. Installing via docker-compose-plugin..."
    sudo apt-get update -qq && sudo apt-get install -y -qq docker-compose-plugin
fi

# --- Clone / update repo ---
if [ -d docex ]; then
    echo "docex/ exists — pulling latest..."
    cd docex && git pull
else
    echo "Cloning docex..."
    git clone "$REPO_URL"
    cd docex
fi

# --- Configure .env ---
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env from .env.example"
fi

# Set/update PG_PASSWORD
if [ ! -f .env.generated ]; then
    PG_PASS=$(openssl rand -base64 18 | tr '+/' '-_')
    if grep -q "^PG_PASSWORD=" .env; then
        sed -i "s/^PG_PASSWORD=.*/PG_PASSWORD=$PG_PASS/" .env
    else
        echo "PG_PASSWORD=$PG_PASS" >> .env
    fi
    # Mark generated so we don't overwrite on re-run
    touch .env.generated
    echo "Generated random PG_PASSWORD"
fi

# Set DOMAIN / EMAIL / production Caddy ports
if [ -n "$DOMAIN" ]; then
    for var in "DOMAIN=$DOMAIN" "CADDY_HTTP_PORT=80" "CADDY_HTTPS_PORT=443"; do
        key="${var%%=*}"
        if grep -q "^${key}=" .env; then
            sed -i "s/^${key}=.*/${var}/" .env
        else
            echo "${var}" >> .env
        fi
    done
    # Append the {$DOMAIN} server block to Caddyfile for TLS
    if ! grep -q "{$DOMAIN}" Caddyfile; then
        cat >> Caddyfile << EOF

{$DOMAIN} {
    root * /usr/share/caddy

    @api {
        path /documents* /search* /health* /metrics* /openapi*
    }
    reverse_proxy @api app:8000

    file_server
}
EOF
    fi
fi
if [ -n "$EMAIL" ]; then
    if grep -q "^EMAIL=" .env; then
        sed -i "s/^EMAIL=.*/EMAIL=$EMAIL/" .env
    else
        echo "EMAIL=$EMAIL" >> .env
    fi
fi

# --- Start services ---
echo "Starting all services..."
docker compose up -d --build

# --- Wait for app to be healthy ---
echo "Waiting for the API to become healthy..."
for i in $(seq 1 60); do
    if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
        echo "API is healthy (attempt $i)"
        break
    fi
    if [ "$i" -eq 60 ]; then
        echo "ERROR: API did not become healthy after 60 attempts. Check 'docker compose logs app'."
        exit 1
    fi
    sleep 2
done

# --- Initialize DB schema ---
echo "Initializing database schema..."
docker compose run --rm app python scripts/init_db.py

# --- Initialize ES index ---
echo "Creating Elasticsearch index..."
docker compose run --rm app python scripts/init_es.py

# --- Optional: seed data ---
if [ "$SEED" = true ]; then
    echo "Fetching seed data from Stardew Valley Wiki..."
    docker compose run --rm app python scripts/seed.py --output data/seed.jsonl

    echo "Importing seed data (~2,800 documents)..."
    docker compose run --rm app python scripts/bulk_import.py data/seed.jsonl --api http://app:8000 --rate 40

    echo "Waiting for consumer to finish indexing..."
    sleep 10
    DOC_COUNT=$(curl -s -X GET "http://localhost:9200/documents/_count" \
        -H "Content-Type: application/json" \
        -d '{"query":{"term":{"tenant_id":"stardewvalley"}}}' | grep -o '"count":[0-9]*' | grep -o '[0-9]*')
    echo "Indexed $DOC_COUNT documents for tenant 'stardewvalley'"
fi

# --- Summary ---
echo ""
echo "============================================"
echo "  DocEx is running!"
echo ""

if [ -n "$DOMAIN" ]; then
    echo "  UI:      https://$DOMAIN"
    echo "  API:     https://$DOMAIN/health"
    echo ""
    echo "  HTTPS will be available once DNS propagates"
    echo "  and Let's Encrypt issues a certificate."
else
    IP=$(curl -sf http://checkip.amazonaws.com 2>/dev/null || echo "<SERVER_IP>")
    HTTP_PORT="${CADDY_HTTP_PORT:-8080}"
    echo "  UI:      http://$IP:$HTTP_PORT"
    echo "  API:     http://$IP:$HTTP_PORT/health"
    echo "  Direct:  http://$IP:8000"
fi

echo ""
echo "  Search:  curl -H 'X-Tenant-ID: stardewvalley' 'http://localhost:8080/search?q=stardrop'"
echo ""
echo "  docker compose logs --tail=20 -f"
echo "============================================"
