# Seeing Dashboard

A Flask-based mini-app that visualizes meteoblue's astronomical seeing forecast for Peristeri, Greece. Data is scraped from the official seeing page, normalized and stored in SQLite, and presented with a dark, mobile-friendly grid.

## Requirements

- Python 3.10+
- `pip install -r requirements.txt`

## Setup

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
2. **Initialize the database** (creates `seeing.db` by default):
   ```bash
   python -c "import app"
   ```
   This will run the SQLAlchemy metadata creation. You can also run the app once and it will auto-create the schema.
3. **Fetch the first dataset** (optional but recommended):
   Start the app and visit `http://localhost:5000/seeing`, then click the **Refresh data** button or send a POST request to `/refresh` to pull the latest observations.
4. **Run the dev server**
   ```bash
   flask --app app run
   ```

## Configuration

Change the following values via environment variables before starting Flask if needed:

- `SEEING_DATABASE_URL`: SQLAlchemy URL (defaults to `sqlite:///seeing.db`).
- `FLASK_SECRET_KEY`: Secret key used for flashes.

## Switching locations

Choose your preferred city right from the home page dropdown. Each selection jumps straight to the `/seeing` dashboard for that location, and the refresh button respects the current city when hitting `/refresh`. Available cities today: Peristeri, Piraeus, Glyfada, and Ekkara (all Greece), with the ability to add more entries to `Config.LOCATIONS`.

## Schema changes

The app now tracks a `location_slug` column, so you must recreate the database when upgrading from a previous version. Remove the old file and rerun the schema creation step before refreshing data:

```bash
rm seeing.db
python -c "import app"
```

## Daily refresh

The `refresh_seeing_data` helper can be invoked manually or scheduled. For example, to refresh once per day at 02:00 using APScheduler:

```python
from apscheduler.schedulers.background import BackgroundScheduler
scheduler = BackgroundScheduler()
scheduler.add_job(refresh_seeing_data, trigger='cron', hour=2, timezone='Europe/Athens')
scheduler.start()
```

Place this snippet near the bottom of `app.py` (uncommented) when running in production.

## PWA & offline behavior

The site now ships with a `manifest.json`, icons, and `static/sw.js`, which caches the home page, offline fallback page, CSS, JS, and icon when the service worker installs. To try it locally, use a secure context (HTTPS or `localhost`), open devtools > Application > Manifest to install, and reload while offline to see the fallback page. When you deploy, browsers will prompt visitors to “install” the dashboard for quick access.

## Systemd service on port 8701

A provided [+seeing.service+](seeing.service) unit boots the Flask app on port `8701` so you can expose it consistently after machine restarts.

1. Copy the template into `/etc/systemd/system/seeing.service` and adjust `WorkingDirectory` (set to `/opt/seeing` if that is where you install the app), `User`, and `Group` for your installation. Create a virtualenv (e.g., `/opt/seeing/.venv`) and install the requirements so `/opt/seeing/.venv/bin/python` can execute `-m flask`, or point `ExecStart`/`PATH` to whichever interpreter you require.
2. Run `sudo systemctl daemon-reload` to pick up the new unit.
3. Start and enable the service with `sudo systemctl enable --now seeing.service`.
4. Confirm it listens on port `8701` (e.g., `ss -tlnp | grep 8701`) and tails logs via `sudo journalctl -u seeing.service -f`.

## Nginx reverse proxy

`deploy/seeing.conf` contains a hardened nginx site definition that redirects HTTP to HTTPS, enforces modern TLS settings, and proxies traffic to port `8701`. After placing it under `/etc/nginx/sites-available/seeing.conf`:

1. Update `server_name` and the `ssl_certificate`/`ssl_certificate_key` paths to match your domain and certificate provider.
2. [Optional] Adjust `proxy_set_header` lines if you insert other middleware (load balancers, WebSocket tunnels, etc.).
3. Enable the site (`sudo ln -s /etc/nginx/sites-available/seeing.conf /etc/nginx/sites-enabled/seeing.conf`), test nginx (`sudo nginx -t`), and reload it (`sudo systemctl reload nginx`).
4. Verify the HTTPS endpoint stays up and terminates TLS correctly (`curl -I https://seeing.example.com` or use your monitoring tool).

### Certificate issuance

Use `scripts/request-certs.sh` to request a certificate that covers both `seeing.pyworld.org` and `hashwhisper.pyworld.org`. Update the `EMAIL` variable to the address that should receive expiration notices, then run `sudo /opt/seeing/scripts/request-certs.sh` after nginx is configured and reachable over HTTP. This script will call the combined `certbot --nginx -d ...` command you mentioned and reload nginx once the new cert is in place.

### Monthly certificate renewal

Use `scripts/renew-certs.sh` to run `certbot renew` and reload nginx whenever certificates change. To have this happen automatically once per month, add a cron job such as:

```
0 3 1 * * root /opt/seeing/scripts/renew-certs.sh >/var/log/seeing-cert-renew.log 2>&1
```

Drop that line into `/etc/cron.d/seeing-cert-renewal` (or your preferred crontab) so the script runs at 03:00 on the first day of every month. Make sure `/opt/seeing` is readable by the cron user and that `certbot`/`systemctl` are on its PATH.

If you want a single certificate to cover both `seeing.pyworld.org` and `hashwhisper.pyworld.org`, issue it with:

```
sudo certbot --nginx -d seeing.pyworld.org -d hashwhisper.pyworld.org
```

Then the renewal job above will keep both hostnames updated. If you prefer separate certificates, run the same command twice with the desired domain pairings and `certbot renew` will refresh every certificate it manages.
