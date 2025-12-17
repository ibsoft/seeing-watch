#!/usr/bin/env bash
set -euo pipefail

# Renew all certificates and reload nginx if anything changed.
/usr/bin/certbot renew --quiet --deploy-hook "systemctl reload nginx"
