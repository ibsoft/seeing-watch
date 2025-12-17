#!/usr/bin/env bash
set -euo pipefail

# Create or reissue the combined certificate for both hostnames and reload nginx afterwards.
DOMAINS=(seeing.pyworld.org hashwhisper.pyworld.org)
EMAIL="admin@pyworld.org" # replace with a real contact address

exec /usr/bin/certbot --nginx "${DOMAINS[@]/#/-d }" --non-interactive --agree-tos \
    --email "$EMAIL" --deploy-hook "systemctl reload nginx"
