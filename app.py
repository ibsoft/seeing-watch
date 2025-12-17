import os
import re
from collections import OrderedDict
from datetime import datetime, time as dt_time, date
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker


class Config:
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "changeme123")
    DATABASE_URL = os.environ.get("SEEING_DATABASE_URL", "sqlite:///seeing.db")
    USER_AGENT = "astronomy-seeing-app/1.0"

    DEFAULT_LOCATION = "peristeri"
    LOCATIONS = {
        "peristeri": {
            "name": "Peristeri, Greece",
            "url": "https://www.meteoblue.com/en/weather/outdoorsports/seeing/peristeri_greece_255524",
            "timezone": "Europe/Athens",
        },
        "piraeus": {
            "name": "Piraeus, Greece",
            "url": "https://www.meteoblue.com/en/weather/outdoorsports/seeing/piraeus_greece_255274",
            "timezone": "Europe/Athens",
        },
        "glyfada": {
            "name": "Glyfada, Greece",
            "url": "https://www.meteoblue.com/en/weather/outdoorsports/seeing/glyfada_greece_262036",
            "timezone": "Europe/Athens",
        },
        "ekkara": {
            "name": "Ekkara, Greece",
            "url": "https://www.meteoblue.com/en/weather/outdoorsports/seeing/ekkara_greece_262828",
            "timezone": "Europe/Athens",
        },
    }


app = Flask(__name__)
app.config.from_object(Config)

Base = declarative_base()

connect_args = {}
if Config.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(Config.DATABASE_URL, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, future=True)


class SeeingMeasurement(Base):
    __tablename__ = "seeing_measurements"

    id = Column(Integer, primary_key=True)
    location_slug = Column(String(32), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    day_index = Column(Integer, nullable=False)
    hour = Column(Integer, nullable=False)
    cloud_low = Column(Integer)
    cloud_mid = Column(Integer)
    cloud_high = Column(Integer)
    arc_seconds = Column(Float)
    seeing_index_one = Column(Integer)
    seeing_index_two = Column(Integer)
    jet_stream = Column(Float)
    bad_layer_bottom = Column(Float)
    bad_layer_top = Column(Float)
    bad_layer_gradient = Column(Float)
    temperature = Column(Float)
    humidity = Column(Integer)
    celestial = Column(Text)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(ZoneInfo("UTC")))


class DaySummary(Base):
    __tablename__ = "day_summaries"

    id = Column(Integer, primary_key=True)
    day_index = Column(Integer, nullable=False, index=True)
    day_date = Column(Date, nullable=False)
    weekday = Column(String(16))
    meta = Column(Text)
    location_slug = Column(String(32), nullable=False, index=True)


Base.metadata.create_all(engine)


def resolve_location(slug: str | None) -> tuple[str, dict]:
    if slug is None:
        slug = Config.DEFAULT_LOCATION
    location = Config.LOCATIONS.get(slug)
    if not location:
        slug = Config.DEFAULT_LOCATION
        location = Config.LOCATIONS[slug]
    return slug, location


def build_zoneinfo(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo("UTC")


def parse_int(text: str) -> int | None:
    if not text:
        return None
    match = re.search(r"-?\d+", text.replace("\xa0", ""))
    if not match:
        return None
    return int(match.group(0))


def parse_float(text: str) -> float | None:
    if not text:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text.replace("\xa0", ""))
    if not match:
        return None
    return float(match.group(0))


def extract_text(cell) -> str:
    return cell.get_text(" ", strip=True)


def determine_quality(arc_seconds: float | None) -> tuple[str, str]:
    if arc_seconds is None:
        return "Unknown", "quality-unknown"
    if arc_seconds <= 1.1:
        return "Excellent", "quality-excellent"
    if arc_seconds <= 1.7:
        return "Good", "quality-good"
    if arc_seconds <= 2.5:
        return "Fair", "quality-fair"
    return "Poor", "quality-poor"


def parse_seeing_table(html: str, tz: ZoneInfo) -> tuple[list[dict], dict[int, dict[str, str]]]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.table-seeing")
    if not table:
        raise ValueError("Seeing table not found in the source HTML")

    tbody = table.find("tbody")
    if not tbody:
        raise ValueError("Table body missing from the seeing table")

    day_dates: dict[int, str] = {}
    next_day_index = 0
    readings: list[dict] = []
    day_meta: dict[int, dict[str, str]] = {}

    for tr in tbody.find_all("tr", recursive=False):
        new_day_cell = tr.select_one("td.new-day")
        if new_day_cell:
            text = new_day_cell.get_text(" ", strip=True)
            match = re.search(r"(\d{4}-\d{2}-\d{2})", text)
            weekday = new_day_cell.select_one("span.date-day")
            weekday_text = weekday.get_text(strip=True) if weekday else ""
            meta_text = ""
            pre = new_day_cell.find("pre")
            if pre:
                meta_text = pre.get_text(" ", strip=True)
            if match:
                day_dates[next_day_index] = match.group(1)
                day_meta[next_day_index] = {
                    "date": match.group(1),
                    "weekday": weekday_text,
                    "meta": meta_text,
                }
                next_day_index += 1
            continue
        classes = tr.get("class") or []
        if "hour-row" not in classes:
            continue

        time_cell = tr.find("td", class_="time")
        if not time_cell:
            continue

        hour = parse_int(time_cell.get_text())
        if hour is None:
            continue

        day_index_attr = tr.get("data-day")
        if day_index_attr is None:
            continue

        day_index = int(day_index_attr)
        day_date = day_dates.get(day_index)
        if not day_date:
            continue

        local_date = datetime.strptime(day_date, "%Y-%m-%d").date()
        local_dt = datetime.combine(local_date, dt_time(hour=int(hour)), tzinfo=tz)
        aware_ts = local_dt.astimezone(ZoneInfo("UTC"))

        cells = [cell for cell in tr.find_all("td", recursive=False)]
        if len(cells) < 14:
            continue

        low_cloud = parse_int(extract_text(cells[1]))
        mid_cloud = parse_int(extract_text(cells[2]))
        high_cloud = parse_int(extract_text(cells[3]))
        arc_seconds = parse_float(extract_text(cells[4]))
        seeing_one = parse_int(extract_text(cells[5]))
        seeing_two = parse_int(extract_text(cells[6]))
        jet_stream = parse_float(extract_text(cells[7]))
        layer_bottom = parse_float(extract_text(cells[8]))
        layer_top = parse_float(extract_text(cells[9]))
        layer_gradient = parse_float(extract_text(cells[10]))
        temperature = parse_float(extract_text(cells[11]))
        humidity = parse_int(extract_text(cells[12]))

        celestial_pre = cells[13].find("pre")
        celestial = extract_text(celestial_pre) if celestial_pre else extract_text(cells[13])

        readings.append(
            {
                "timestamp": aware_ts,
                "day_index": day_index,
                "hour": hour,
                "cloud_low": low_cloud,
                "cloud_mid": mid_cloud,
                "cloud_high": high_cloud,
                "arc_seconds": arc_seconds,
                "seeing_index_one": seeing_one,
                "seeing_index_two": seeing_two,
                "jet_stream": jet_stream,
                "bad_layer_bottom": layer_bottom,
                "bad_layer_top": layer_top,
                "bad_layer_gradient": layer_gradient,
                "temperature": temperature,
                "humidity": humidity,
                "celestial": celestial,
            }
        )

    if not readings:
        raise ValueError("No hourly rows were parsed from the page")

    return readings, day_meta


def fetch_remote_data(slug: str | None = None) -> tuple[bool, str | tuple[list[dict], dict[int, dict[str, str]]]]:
    _, location = resolve_location(slug)
    tz = build_zoneinfo(location["timezone"])
    try:
        resp = requests.get(location["url"], timeout=20, headers={"User-Agent": Config.USER_AGENT})
        resp.raise_for_status()
    except requests.RequestException as exc:
        return False, f"Unable to reach meteoblue: {exc}"

    try:
        data = parse_seeing_table(resp.text, tz)
    except ValueError as exc:
        return False, f"Parsing error: {exc}"

    return True, data


def refresh_seeing_data(slug: str | None = None) -> tuple[bool, str]:
    location_slug, _ = resolve_location(slug)
    success, payload = fetch_remote_data(location_slug)
    if not success:
        return False, payload  # type: ignore[arg-type]

    readings, day_meta = payload  # type: ignore[arg-type]
    for row in readings:
        row["location_slug"] = location_slug

    for meta in day_meta.values():
        meta["location_slug"] = location_slug

    with SessionLocal() as session:
        session.query(SeeingMeasurement).filter(SeeingMeasurement.location_slug == location_slug).delete()
        session.query(DaySummary).filter(DaySummary.location_slug == location_slug).delete()
        session.commit()

        for row in readings:
            measurement = SeeingMeasurement(**row)
            session.add(measurement)

        for day_index, info in day_meta.items():
            day_date = datetime.strptime(info["date"], "%Y-%m-%d").date()
            summary = DaySummary(
                day_index=day_index,
                day_date=day_date,
                weekday=info.get("weekday"),
                meta=info.get("meta"),
                location_slug=location_slug,
            )
            session.add(summary)
        session.commit()

    return True, f"Stored {len(readings)} hourly observations"


@app.route("/")
def home():
    slug, location = resolve_location(None)
    return render_template(
        "home.html",
        location=location["name"],
        locations=Config.LOCATIONS,
        default_location=slug,
    )


@app.route("/refresh", methods=("POST",))
def refresh_data():
    location_slug = request.form.get("location")
    resolved_slug, _ = resolve_location(location_slug)
    success, message = refresh_seeing_data(resolved_slug)
    flash(message, "success" if success else "danger")
    return redirect(url_for("seeing", location=resolved_slug))


@app.route("/seeing")
def seeing():
    location_slug, location = resolve_location(request.args.get("location"))
    tz = build_zoneinfo(location["timezone"])

    with SessionLocal() as session:
        measurements = (
            session.query(SeeingMeasurement)
            .filter(SeeingMeasurement.location_slug == location_slug)
            .order_by(SeeingMeasurement.timestamp)
            .all()
        )
        day_summaries = (
            session.query(DaySummary)
            .filter(DaySummary.location_slug == location_slug)
            .order_by(DaySummary.day_index)
            .all()
        )

    day_groups: OrderedDict[date, list[dict]] = OrderedDict()
    for meas in measurements:
        local_ts = meas.timestamp.astimezone(tz)
        day = local_ts.date()
        quality_label, quality_class = determine_quality(meas.arc_seconds)
        entry = {
            "hour": local_ts.strftime("%H"),
            "datetime": local_ts.isoformat(),
            "cloud_low": meas.cloud_low,
            "cloud_mid": meas.cloud_mid,
            "cloud_high": meas.cloud_high,
            "arc_seconds": meas.arc_seconds,
            "seeing_index_one": meas.seeing_index_one,
            "seeing_index_two": meas.seeing_index_two,
            "jet_stream": meas.jet_stream,
            "bad_layer_bottom": meas.bad_layer_bottom,
            "bad_layer_top": meas.bad_layer_top,
            "bad_layer_gradient": meas.bad_layer_gradient,
            "temperature": meas.temperature,
            "humidity": meas.humidity,
            "celestial": meas.celestial,
            "quality_label": quality_label,
            "quality_class": quality_class,
            "super_good": (
                meas.seeing_index_one == 5
                and meas.seeing_index_two == 5
                and (meas.jet_stream is not None and meas.jet_stream < 20)
            ),
        }
        day_groups.setdefault(day, []).append(entry)

    summary_map = {summary.day_date: summary for summary in day_summaries}
    day_cards = []
    for day_key, rows in day_groups.items():
        summary = summary_map.get(day_key)
        if summary and summary.weekday:
            label_text = f"{summary.weekday} {day_key.strftime('%Y-%m-%d')}"
        else:
            label_text = day_key.strftime("%a, %b %d")
        meta_text = summary.meta if summary else None
        day_cards.append(
            {
                "date": day_key,
                "label": label_text,
                "meta": meta_text,
                "rows": rows,
            }
        )

    super_good_slots = []
    for card in day_cards:
        for row in card["rows"]:
            if row.get("super_good"):
                super_good_slots.append(f"{card['label']} {row['hour']}:00")

    last_updated = None
    if measurements:
        last_updated = measurements[-1].timestamp.astimezone(tz)

    legend = [
        ("Excellent (≤1.1)", "quality-excellent"),
        ("Good (≤1.7)", "quality-good"),
        ("Fair (≤2.5)", "quality-fair"),
        ("Poor (>2.5)", "quality-poor"),
    ]

    return render_template(
        "seeing.html",
        days=day_cards,
        location=location["name"],
        current_slug=location_slug,
        super_good_slots=super_good_slots,
        legend=legend,
        last_updated=last_updated,
        source_url=location["url"],
    )


@app.errorhandler(404)
def not_found(error):
    return render_template("error.html", title="Page not found", message="We couldn't find that page."), 404


@app.errorhandler(500)
def server_error(error):
    return (
        render_template(
            "error.html",
            title="Something broke",
            message="An internal error occurred. Try refreshing or come back later.",
        ),
        500,
    )


# Example APScheduler setup for a daily refresh (uncomment in production):
# from apscheduler.schedulers.background import BackgroundScheduler
# scheduler = BackgroundScheduler()
# scheduler.add_job(refresh_seeing_data, trigger="cron", hour=2, timezone='Europe/Athens')
# scheduler.start()


if __name__ == "__main__":
    app.run(debug=True)
