import streamlit as st
import base64
import os
from pathlib import Path
import requests
from datetime import datetime, timezone, timedelta
import streamlit.components.v1 as components
from dotenv import load_dotenv

# ==========================================
# 1. LOAD ENV, RESOLVE ASSETS & PAGE CONFIG
# ==========================================
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

def _resolve_static_image(filename: str) -> str | None:
    """Locate static images reliably regardless of the working directory."""
    candidates = [
        BASE_DIR / "static" / "images" / filename,
        BASE_DIR / "web" / "static" / "images" / filename,
        BASE_DIR.parent / "static" / "images" / filename,
        BASE_DIR.parent / "web" / "static" / "images" / filename,
        Path("web/static/images") / filename,
        Path("admin/packnship/web/static/images") / filename,
        Path("packnship/web/static/images") / filename,
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            return str(p)
    return None

def get_icon_b64(filename: str) -> str | None:
    resolved = _resolve_static_image(filename)
    if not resolved:
        return None
    try:
        with open(resolved, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return None

APP_ICON_PATH = _resolve_static_image("appiconfinal.png") or "📦"

st.set_page_config(
    page_title="Track Shipment · Pack-N-Ship",
    page_icon=APP_ICON_PATH,
    layout="wide",
    initial_sidebar_state="collapsed",
)

ICON_FILES = {
    "logo": "appiconfinal.png",
    "brand_logo": "packnship_logo.png",
}
ICONS = {k: get_icon_b64(v) for k, v in ICON_FILES.items()}
if not ICONS.get("logo") and ICONS.get("brand_logo"):
    ICONS["logo"] = ICONS["brand_logo"]

def icon_img(key: str, size: int = 44, fallback: str = "📦", radius: int = 0) -> str:
    b64 = ICONS.get(key)
    rad_style = f"border-radius:{radius}px;" if radius > 0 else ""
    if b64:
        return (
            f'<img src="data:image/png;base64,{b64}" '
            f'style="width:{size}px;height:{size}px;object-fit:contain;display:block;{rad_style}" alt="" />'
        )
    return f'<span style="font-size:{int(size*0.75)}px;line-height:1;">{fallback}</span>'

# ==========================================
# 2. SUPABASE CONFIG & HELPERS
# ==========================================
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# Prioritize Service Role Key on backend so RLS on locations/users does not block public tracking
API_KEY = SUPABASE_SERVICE_ROLE_KEY if SUPABASE_SERVICE_ROLE_KEY else SUPABASE_ANON_KEY

# Philippine Standard Time (UTC+8)
PHT_TZ = timezone(timedelta(hours=8))

APK_DOWNLOAD_LINK = "https://drive.google.com/drive/folders/1ywrPTfC0-lytwTvwrK-0g3Gky9JW2IQi?usp=drive_link"
HOME_SITE_LINK = "https://packnship.streamlit.app/"

def _sb_headers():
    return {
        "apikey": API_KEY,
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

def _sb_get(path: str, params: dict | None = None):
    if not SUPABASE_URL or not API_KEY:
        print("Missing Supabase credentials in .env")
        return None
    try:
        url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/{path.lstrip('/')}"
        r = requests.get(url, headers=_sb_headers(), params=params or {}, timeout=10)
        if r.status_code >= 400:
            print(f"Supabase Error {r.status_code}: {r.text}")
            return None
        return r.json()
    except Exception as e:
        print(f"Supabase fetch failed: {e}")
        return None

def _parse_tracking_id(raw: str) -> int | None:
    if not raw:
        return None
    s = str(raw).strip().upper()
    s = s.replace("PNS-", "").replace("PNS", "").replace("REQ-", "").strip()
    s = s.lstrip("#").lstrip("0") or "0"
    try:
        return int(s)
    except Exception:
        return None

def _fmt_dt(iso: str | None, short_date: bool = False) -> str:
    """
    Converts UTC / naive database timestamps into Philippine Standard Time (UTC+8)
    and formats them to match the mobile app (e.g., 'Oct 22, 2026 · 5:10 AM').
    """
    if not iso:
        return "—"
    try:
        raw = str(iso).strip()
        if "T" not in raw and " " in raw:
            raw = raw.replace(" ", "T", 1)
        has_tz = raw.endswith("Z") or ("+" in raw[10:]) or ("-" in raw[10:])
        if not has_tz:
            raw += "+00:00"
        else:
            raw = raw.replace("Z", "+00:00")

        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        dt_pht = dt.astimezone(PHT_TZ)

        hour_12 = dt_pht.hour % 12 or 12
        minute_str = f"{dt_pht.minute:02d}"
        ampm = "AM" if dt_pht.hour < 12 else "PM"

        if short_date:
            date_part = dt_pht.strftime("%b %d")
        else:
            date_part = f"{dt_pht.strftime('%b')} {dt_pht.day}, {dt_pht.year}"

        return f"{date_part} · {hour_12}:{minute_str} {ampm}"
    except Exception:
        return str(iso)

def _status_meta(status: str, completed: bool = False):
    s = (status or "").strip().lower()
    if completed or s in ("completed", "delivered"):
        return {"label": "Delivered", "color": "#059669", "bg": "#ECFDF5", "border": "#A7F3D0", "icon": "✓"}
    if s in ("cancelled", "canceled"):
        return {"label": "Cancelled", "color": "#DC2626", "bg": "#FEF2F2", "border": "#FECACA", "icon": "✕"}
    if s == "in transit":
        return {"label": "In Transit", "color": "#EA580C", "bg": "#FFF7ED", "border": "#FED7AA", "icon": "🚚"}
    if s == "matched":
        return {"label": "Courier Matched", "color": "#2563EB", "bg": "#EFF6FF", "border": "#BFDBFE", "icon": "🤝"}
    if s in ("accepted", "in progress"):
        return {"label": "In Progress", "color": "#EA580C", "bg": "#FFF7ED", "border": "#FED7AA", "icon": "🚗"}
    if s == "pending":
        return {"label": "Finding Courier", "color": "#D97706", "bg": "#FFFBEB", "border": "#FDE68A", "icon": "⏳"}
    return {"label": (status or "Active").title(), "color": "#4B5563", "bg": "#F3F4F6", "border": "#E5E7EB", "icon": "•"}

def _extract_joined_row(val) -> dict:
    if isinstance(val, dict):
        return val
    if isinstance(val, list) and len(val) > 0 and isinstance(val[0], dict):
        return val[0]
    return {}

def _get_plus_code(lat, lng) -> str:
    if lat is None or lng is None:
        return ""
    try:
        lat_val = float(lat)
        lng_val = float(lng)
        return f"8W{int(lat_val*100):02d}+{int(lng_val*100):03d}"
    except Exception:
        return ""

def _format_location_display(loc: dict) -> tuple[str, str]:
    if not loc:
        return ("Location unavailable", "Coordinates unavailable")

    lat = loc.get("latitude")
    lng = loc.get("longitude")
    plus_code = _get_plus_code(lat, lng)

    coords_str = "Coordinates unavailable"
    if lat is not None and lng is not None:
        try:
            coords_str = f"{float(lat):.5f}, {float(lng):.5f}"
        except Exception:
            pass

    parts = [
        str(loc.get("street_address") or "").strip(),
        str(loc.get("barangay") or "").strip(),
        str(loc.get("city") or "").strip(),
        str(loc.get("province") or "").strip(),
    ]
    clean_parts = []
    for pt in parts:
        if pt and pt.lower() not in ("none", "null", "n/a", "unknown", "-"):
            if pt not in clean_parts:
                clean_parts.append(pt)

    if clean_parts:
        primary = ", ".join(clean_parts)
        secondary = f"{plus_code} · {coords_str}" if plus_code else coords_str
        return (primary, secondary)

    if plus_code:
        return (plus_code, coords_str)

    return ("Location unavailable", coords_str)

def fetch_tracking_bundle(request_id: int) -> dict | None:
    req_rows = _sb_get(
        "delivery_requests",
        {
            "request_id": f"eq.{request_id}",
            "select": (
                "*,"
                "pickup:locations!delivery_requests_pickup_location_id_fkey(*),"
                "dropoff:locations!delivery_requests_dropoff_location_id_fkey(*)"
            ),
            "limit": 1,
        },
    )
    if not req_rows:
        req_rows = _sb_get(
            "delivery_requests",
            {
                "request_id": f"eq.{request_id}",
                "limit": 1,
            },
        )
    if not req_rows:
        return None

    req = req_rows[0]
    req["pickup"] = _extract_joined_row(req.get("pickup"))
    req["dropoff"] = _extract_joined_row(req.get("dropoff"))

    pickup_id = req.get("pickup_location_id")
    dropoff_id = req.get("dropoff_location_id")

    if not req["pickup"] and pickup_id is not None:
        p_rows = _sb_get("locations", {"location_id": f"eq.{pickup_id}", "limit": 1})
        if p_rows:
            req["pickup"] = p_rows[0]

    if not req["dropoff"] and dropoff_id is not None:
        d_rows = _sb_get("locations", {"location_id": f"eq.{dropoff_id}", "limit": 1})
        if d_rows:
            req["dropoff"] = d_rows[0]

    deliveries = _sb_get(
        "deliveries",
        {
            "request_id": f"eq.{request_id}",
            "select": "*,vehicle:vehicles(*),provider:users!deliveries_provider_id_fkey(first_name,last_name,phone_number,profile_photo,is_verified)",
            "order": "accepted_at.desc",
            "limit": 1,
        },
    )
    delivery = deliveries[0] if deliveries else None

    qr = None
    if delivery:
        qr_rows = _sb_get(
            "qr_verifications",
            {"delivery_id": f"eq.{delivery['delivery_id']}", "select": "pickup_verified,dropoff_verified", "limit": 1},
        )
        qr = qr_rows[0] if qr_rows else None

    fix = None
    if delivery:
        fix_rows = _sb_get(
            "delivery_locations",
            {"delivery_id": f"eq.{delivery['delivery_id']}", "select": "latitude,longitude,heading,speed,accuracy,updated_at", "limit": 1},
        )
        if not fix_rows and delivery.get("provider_id"):
            fix_rows = _sb_get(
                "provider_live_locations",
                {"provider_id": f"eq.{delivery['provider_id']}", "select": "latitude,longitude,heading,speed,accuracy,updated_at", "limit": 1},
            )
        fix = fix_rows[0] if fix_rows else None

    return {"request": req, "delivery": delivery, "qr": qr, "fix": fix}

# ==========================================
# 3. GOOGLE MAPS LIVE COMPONENT
# ==========================================
def render_tracking_map_html(bundle: dict) -> str:
    req = bundle["request"]
    delivery = bundle.get("delivery")
    qr = bundle.get("qr")
    fix = bundle.get("fix")

    pickup = req.get("pickup") or {}
    dropoff = req.get("dropoff") or {}

    def num(v, d):
        try:
            if v is None:
                return d
            f = float(v)
            return f if f == f else d
        except Exception:
            return d

    p_lat = num(pickup.get("latitude"), 10.3157)
    p_lng = num(pickup.get("longitude"), 123.8854)
    d_lat = num(dropoff.get("latitude"), 10.3157)
    d_lng = num(dropoff.get("longitude"), 123.8854)

    p_addr, _ = _format_location_display(pickup)
    d_addr, _ = _format_location_display(dropoff)
    p_addr_safe = p_addr.replace("'", "\\'").replace('"', "&quot;")
    d_addr_safe = d_addr.replace("'", "\\'").replace('"', "&quot;")

    pickup_verified = bool(qr and qr.get("pickup_verified"))
    target_is_dropoff = pickup_verified and not (delivery and delivery.get("completed_at"))

    courier = None
    if fix and fix.get("latitude") is not None and fix.get("longitude") is not None:
        courier = [float(fix["latitude"]), float(fix["longitude"])]

    gmaps_dir_url = f"https://www.google.com/maps/dir/?api=1&origin={p_lat},{p_lng}&destination={d_lat},{d_lng}&travelmode=driving"

    return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@600;700;800;900&display=swap');
        * {{ box-sizing: border-box; }}
        html, body {{
            margin: 0; padding: 0; width: 100%; height: 100%;
            background: #F8FAFC; font-family: 'Inter', -apple-system, sans-serif;
        }}
        .map-shell {{
            position: relative; width: 100%; height: 100%;
            border-radius: 22px; overflow: hidden;
            border: 1px solid #E5E7EB;
            box-shadow: 0 14px 36px rgba(15, 23, 42, 0.06);
        }}
        #map {{ width: 100%; height: 100%; background: #E5E7EB; }}
        @keyframes pulseCourier {{
            0% {{ transform: scale(1); opacity: 0.65; }}
            100% {{ transform: scale(2.3); opacity: 0; }}
        }}
        .pin-wrap {{
            position: relative; width: 34px; height: 34px;
            display: flex; align-items: center; justify-content: center;
        }}
        .pin-pulse {{
            position: absolute; inset: 0; border-radius: 50%;
            background: #FF751F; animation: pulseCourier 1.6s ease-out infinite;
        }}
        .pin {{
            position: relative; z-index: 2;
            display: flex; align-items: center; justify-content: center;
            font-weight: 900; color: #FFF;
            box-shadow: 0 6px 16px rgba(15,23,42,0.32);
            border-radius: 50%; letter-spacing: -0.3px;
            border: 3px solid #FFFFFF;
        }}
        .pin-pickup {{ background: #2563EB; width: 32px; height: 32px; font-size: 12px; }}
        .pin-dropoff {{ background: #059669; width: 32px; height: 32px; font-size: 12px; }}
        .pin-courier {{ background: #FF751F; width: 36px; height: 36px; font-size: 13px; }}

        .top-controls {{
            position: absolute; top: 14px; left: 14px; right: 14px; z-index: 1000;
            display: flex; justify-content: space-between; align-items: center;
            pointer-events: none; gap: 8px; flex-wrap: wrap;
        }}
        .control-group {{
            pointer-events: auto;
            display: inline-flex; align-items: center; gap: 4px;
            background: rgba(255,255,255,0.95); backdrop-filter: blur(10px);
            padding: 4px; border-radius: 12px;
            border: 1px solid rgba(15,23,42,0.08);
            box-shadow: 0 8px 20px rgba(15,23,42,0.10);
        }}
        .ctrl-btn {{
            border: none; background: transparent; color: #4B5563;
            font-family: inherit; font-size: 11px; font-weight: 800;
            padding: 6px 11px; border-radius: 9px; cursor: pointer;
            text-transform: uppercase; letter-spacing: 0.5px;
            transition: all 0.18s ease; text-decoration: none;
            display: inline-flex; align-items: center; gap: 5px;
        }}
        .ctrl-btn:hover {{ color: #111827; background: #F3F4F6; }}
        .ctrl-btn.active {{
            background: #FF751F; color: #FFFFFF;
            box-shadow: 0 4px 10px rgba(255,117,31,0.3);
        }}
        .gmaps-link {{
            color: #FF751F !important; font-weight: 800;
        }}

        .bottom-bar {{
            position: absolute; bottom: 14px; left: 14px; right: 14px; z-index: 1000;
            display: flex; justify-content: space-between; align-items: center;
            pointer-events: none; flex-wrap: wrap; gap: 8px;
        }}
        .map-legend {{
            pointer-events: auto;
            background: rgba(255,255,255,0.95); backdrop-filter: blur(10px);
            padding: 8px 14px; border-radius: 12px;
            border: 1px solid rgba(15,23,42,0.08);
            box-shadow: 0 8px 20px rgba(15,23,42,0.10);
            display: flex; gap: 14px; align-items: center;
            font-size: 11px; font-weight: 800; color: #1F2937;
        }}
        .legend-item {{ display: flex; align-items: center; gap: 6px; }}
        .legend-dot {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; border: 2px solid #FFF; box-shadow: 0 1px 3px rgba(0,0,0,0.2); }}
        .google-badge {{
            pointer-events: auto;
            background: rgba(17,24,39,0.88); backdrop-filter: blur(8px);
            color: #FFFFFF; font-size: 10.5px; font-weight: 800;
            padding: 7px 12px; border-radius: 10px; letter-spacing: 0.4px;
            display: inline-flex; align-items: center; gap: 6px;
        }}
        .google-badge .g-dot {{
            width: 7px; height: 7px; border-radius: 50%; background: #4ADE80;
        }}
    </style>
</head>
<body>
    <div class="map-shell">
        <div class="top-controls">
            <div class="control-group">
                <button type="button" id="btnRoad" class="ctrl-btn active" onclick="setLayer('road')">Google Map</button>
                <button type="button" id="btnSat" class="ctrl-btn" onclick="setLayer('sat')">Satellite</button>
            </div>
            <div class="control-group">
                <button type="button" class="ctrl-btn" onclick="recenterMap()">Recenter</button>
                <a href="{gmaps_dir_url}" target="_blank" rel="noopener noreferrer" class="ctrl-btn gmaps-link">Open Google Maps ↗</a>
            </div>
        </div>

        <div id="map"></div>

        <div class="bottom-bar">
            <div class="map-legend">
                <div class="legend-item"><span class="legend-dot" style="background:#2563EB;"></span>Pickup (P)</div>
                <div class="legend-item"><span class="legend-dot" style="background:#059669;"></span>Drop-off (D)</div>
                <div class="legend-item"><span class="legend-dot" style="background:#FF751F;"></span>Courier (C)</div>
            </div>
            <div class="google-badge">
                <span class="g-dot"></span> Google Maps Telemetry
            </div>
        </div>
    </div>

    <script>
        var PICKUP = [{p_lat}, {p_lng}];
        var DROPOFF = [{d_lat}, {d_lng}];
        var COURIER = {f"[{courier[0]}, {courier[1]}]" if courier else "null"};
        var TARGET_IS_DROPOFF = {"true" if target_is_dropoff else "false"};

        var map = L.map("map", {{ zoomControl: false, attributionControl: false }}).setView(PICKUP, 14);
        L.control.zoom({{ position: "bottomright" }}).addTo(map);

        var googleRoad = L.tileLayer("https://mt1.google.com/vt/lyrs=m&x={{x}}&y={{y}}&z={{z}}", {{ maxZoom: 20 }});
        var googleSat  = L.tileLayer("https://mt1.google.com/vt/lyrs=y&x={{x}}&y={{y}}&z={{z}}", {{ maxZoom: 20 }});
        googleRoad.addTo(map);

        function setLayer(mode) {{
            var btnRoad = document.getElementById("btnRoad");
            var btnSat  = document.getElementById("btnSat");
            if (mode === "sat") {{
                if (map.hasLayer(googleRoad)) map.removeLayer(googleRoad);
                if (!map.hasLayer(googleSat)) googleSat.addTo(map);
                btnSat.classList.add("active");
                btnRoad.classList.remove("active");
            }} else {{
                if (map.hasLayer(googleSat)) map.removeLayer(googleSat);
                if (!map.hasLayer(googleRoad)) googleRoad.addTo(map);
                btnRoad.classList.add("active");
                btnSat.classList.remove("active");
            }}
        }}

        var pickupIcon  = L.divIcon({{ className: "", html: '<div class="pin-wrap"><div class="pin pin-pickup">P</div></div>', iconSize: [34,34], iconAnchor: [17,17] }});
        var dropoffIcon = L.divIcon({{ className: "", html: '<div class="pin-wrap"><div class="pin pin-dropoff">D</div></div>', iconSize: [34,34], iconAnchor: [17,17] }});
        var courierIcon = L.divIcon({{ className: "", html: '<div class="pin-wrap"><span class="pin-pulse"></span><div class="pin pin-courier">C</div></div>', iconSize: [36,36], iconAnchor: [18,18] }});

        L.marker(PICKUP, {{ icon: pickupIcon }}).bindPopup("<b>Pickup Location</b><br>{p_addr_safe}").addTo(map);
        L.marker(DROPOFF, {{ icon: dropoffIcon }}).bindPopup("<b>Drop-off Destination</b><br>{d_addr_safe}").addTo(map);

        var allBoundsPoints = [PICKUP, DROPOFF];
        if (COURIER) {{
            L.marker(COURIER, {{ icon: courierIcon }}).bindPopup("<b>Live Courier Position</b>").addTo(map);
            allBoundsPoints.push(COURIER);
        }}

        function recenterMap() {{
            if (allBoundsPoints.length >= 2 && (PICKUP[0] !== DROPOFF[0] || PICKUP[1] !== DROPOFF[1])) {{
                map.fitBounds(L.latLngBounds(allBoundsPoints), {{ padding: [58, 58], maxZoom: 16 }});
            }} else {{
                map.setView(PICKUP, 15);
            }}
        }}
        recenterMap();

        function drawRoadRoute(start, target) {{
            if (Math.abs(start[0] - target[0]) < 0.0001 && Math.abs(start[1] - target[1]) < 0.0001) return;
            var url = "https://router.project-osrm.org/route/v1/driving/" +
                      start[1] + "," + start[0] + ";" + target[1] + "," + target[0] +
                      "?overview=full&geometries=geojson";
            fetch(url).then(function(r) {{ return r.json(); }}).then(function(data) {{
                if (data && data.code === "Ok" && data.routes && data.routes[0]) {{
                    var coords = data.routes[0].geometry.coordinates.map(function(c) {{ return [c[1], c[0]]; }});
                    L.polyline(coords, {{ color: "#111827", weight: 8, opacity: 0.22, lineJoin: "round", lineCap: "round" }}).addTo(map);
                    L.polyline(coords, {{ color: "#FF751F", weight: 5, opacity: 0.96, lineJoin: "round", lineCap: "round" }}).addTo(map);
                    allBoundsPoints = coords.slice();
                    if (COURIER) allBoundsPoints.push(COURIER);
                    recenterMap();
                }}
            }}).catch(function() {{
                L.polyline([start, target], {{ color: "#FF751F", weight: 4, dashArray: "8, 8" }}).addTo(map);
            }});
        }}

        if (COURIER) {{
            drawRoadRoute(COURIER, TARGET_IS_DROPOFF ? DROPOFF : PICKUP);
        }} else {{
            drawRoadRoute(PICKUP, DROPOFF);
        }}
    </script>
</body>
</html>'''


# ==========================================
# 4. ENTERPRISE CSS (MATCHING streamlit_app.py)
# ==========================================
css = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

:root {
  --orange-50:  #fff7ed;
  --orange-100: #ffedd5;
  --orange-200: #fed7aa;
  --orange-300: #fdba74;
  --orange-400: #ff9d54;
  --orange-500: #FF751F;
  --orange-600: #E4650F;
  --orange-700: #B84708;
  --ink-900: #0a0a0a;
  --ink-800: #111827;
  --ink-700: #1f2937;
  --ink-600: #4b5563;
  --ink-500: #6b7280;
  --ink-400: #9ca3af;
  --line: #f3f4f6;
  --line-2: #e5e7eb;
  --spring: cubic-bezier(.22,1,.36,1);
  --ease: cubic-bezier(.4,0,.2,1);
}

html, body {
  margin: 0 !important;
  padding: 0 !important;
  background: #ffffff;
  overflow-x: hidden;
  scroll-behavior: smooth;
}

html, body, [class*="css"] {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  color: var(--ink-800);
}

header[data-testid="stHeader"], [data-testid="stHeader"], .stApp > header, #MainMenu, footer,
[data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"],
[data-testid="stAppDeployButton"], .stAppDeployButton {
  display: none !important;
  visibility: hidden !important;
  height: 0 !important;
}

.block-container, [data-testid="stAppViewContainer"] > .main .block-container {
  padding: 0 !important;
  margin: 0 !important;
  max-width: 100% !important;
}

[data-testid="stAppViewContainer"], .stApp, .stMain, section.main {
  background: #ffffff !important;
  padding: 0 !important;
  margin: 0 !important;
}

[data-testid="stHorizontalBlock"] { gap: 1.5rem !important; }
* { -webkit-tap-highlight-color: transparent; box-sizing: border-box; }
::selection { background: rgba(255,117,31,0.22); color: inherit; }

::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-track { background: #f9fafb; }
::-webkit-scrollbar-thumb {
  background: linear-gradient(180deg, var(--orange-500), var(--orange-600));
  border-radius: 10px;
  border: 2px solid #f9fafb;
}

/* Streamlit Form & Input Styling */
div[data-testid="stForm"] {
  background: #FFFFFF !important;
  border: 1.5px solid #E5E7EB !important;
  border-radius: 22px !important;
  padding: 14px 18px !important;
  box-shadow: 0 20px 50px -12px rgba(15, 23, 42, 0.08) !important;
  margin-bottom: 1.75rem !important;
}

div[data-testid="stTextInput"] input {
  background: #F9FAFB !important;
  border: 1.5px solid #E5E7EB !important;
  border-radius: 14px !important;
  color: #111827 !important;
  font-weight: 700 !important;
  font-size: 15px !important;
  padding: 12px 18px !important;
  height: 50px !important;
  letter-spacing: 0.3px !important;
  transition: all 0.2s ease !important;
}

div[data-testid="stTextInput"] input:focus {
  border-color: #FF751F !important;
  background: #FFFFFF !important;
  box-shadow: 0 0 0 4px rgba(255, 117, 31, 0.14) !important;
}

div[data-testid="stFormSubmitButton"] button {
  background: linear-gradient(135deg, #FF751F, #E4650F) !important;
  color: #FFFFFF !important;
  border: none !important;
  border-radius: 14px !important;
  height: 50px !important;
  font-weight: 800 !important;
  font-size: 13.5px !important;
  letter-spacing: 0.5px !important;
  text-transform: uppercase !important;
  box-shadow: 0 10px 24px rgba(255, 117, 31, 0.32) !important;
  transition: all 0.25s ease !important;
}

div[data-testid="stFormSubmitButton"] button:hover {
  transform: translateY(-1px) !important;
  box-shadow: 0 14px 30px rgba(255, 117, 31, 0.45) !important;
}

div.stButton > button {
  background: #111827 !important;
  color: #FFFFFF !important;
  border: 1px solid #1F2937 !important;
  border-radius: 14px !important;
  height: 48px !important;
  font-weight: 800 !important;
  font-size: 13px !important;
  letter-spacing: 0.4px !important;
  text-transform: uppercase !important;
  margin-top: 1rem !important;
  transition: all 0.2s ease !important;
}

div.stButton > button:hover {
  background: #FF751F !important;
  border-color: #FF751F !important;
  box-shadow: 0 10px 24px rgba(255, 117, 31, 0.3) !important;
}

@keyframes slideDown { from { opacity: 0; transform: translateY(-12px); } to { opacity: 1; transform: translateY(0); } }
@keyframes livePulse { 0%,100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.4; transform: scale(1.35); } }
@keyframes pulseRing { 0% { box-shadow: 0 0 0 0 rgba(255,117,31,0.55); } 70% { box-shadow: 0 0 0 10px rgba(255,117,31,0); } 100% { box-shadow: 0 0 0 0 rgba(255,117,31,0); } }

/* NAVBAR */
.topnav {
  position: fixed; top: 0; left: 0; right: 0; height: 74px; z-index: 1000;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 3.5rem;
  background: rgba(255,255,255,0.92);
  backdrop-filter: saturate(180%) blur(18px);
  -webkit-backdrop-filter: saturate(180%) blur(18px);
  border-bottom: 1px solid rgba(17,24,39,0.07);
  animation: slideDown 0.5s var(--spring) both;
}
.brand {
  display: flex; align-items: center; gap: 12px;
  font-size: 20px; font-weight: 900; letter-spacing: -0.7px;
  color: var(--ink-800); text-decoration: none; flex-shrink: 0;
}
.brand .brand-logo {
  width: 40px; height: 40px; border-radius: 12px;
  background: linear-gradient(135deg, #FFF7ED, #FFEDD5);
  border: 1px solid var(--orange-200);
  box-shadow: 0 4px 12px rgba(255,117,31,0.16);
  display: inline-flex; align-items: center; justify-content: center;
  overflow: hidden; flex-shrink: 0;
}
.brand .brand-text .n { color: var(--orange-500); }
.nav-actions { display: flex; align-items: center; gap: 12px; flex-shrink: 0; }
.live-pill {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 7px 13px; background: #FFF7ED; border: 1px solid #FED7AA;
  border-radius: 999px; font-size: 10.5px; font-weight: 800;
  color: var(--orange-600); letter-spacing: 0.5px; text-transform: uppercase;
}
.live-pill .live-dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: var(--orange-500); animation: livePulse 1.6s infinite;
}
.nav-signup {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 10px 20px; border-radius: 11px;
  font-size: 12.5px; font-weight: 800; text-transform: uppercase;
  letter-spacing: 0.4px; text-decoration: none; color: white !important;
  background: linear-gradient(135deg, var(--orange-500), var(--orange-600));
  box-shadow: 0 8px 18px rgba(255,117,31,0.3);
  transition: all 0.25s var(--ease); white-space: nowrap;
}
.nav-signup:hover { transform: translateY(-1px); box-shadow: 0 12px 24px rgba(255,117,31,0.42); }

/* TRACKER HERO HEADER */
.tracker-hero {
  position: relative;
  background: linear-gradient(135deg, #09090b 0%, #150d06 48%, #261405 100%);
  padding: 7.5rem 2rem 3.75rem 2rem;
  text-align: center;
  overflow: hidden;
  isolation: isolate;
}
.tracker-hero::before {
  content: ''; position: absolute; inset: 0;
  background-image:
    linear-gradient(rgba(255,117,31,0.05) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,117,31,0.05) 1px, transparent 1px);
  background-size: 56px 56px;
  mask-image: radial-gradient(ellipse at 50% 45%, black 25%, transparent 75%);
  -webkit-mask-image: radial-gradient(ellipse at 50% 45%, black 25%, transparent 75%);
  pointer-events: none;
}
.hero-eyebrow {
  display: inline-flex; align-items: center; gap: 10px;
  padding: 8px 16px; background: rgba(255,117,31,0.13);
  border: 1px solid rgba(255,117,31,0.34); border-radius: 999px;
  color: #ffb066; font-size: 11px; font-weight: 800;
  letter-spacing: 1.8px; text-transform: uppercase; margin-bottom: 1.25rem;
}
.hero-eyebrow .dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: var(--orange-500); animation: pulseRing 2s infinite; flex-shrink: 0;
}
.tracker-hero-title {
  font-size: clamp(2.1rem, 4.2vw, 3.35rem); font-weight: 900;
  color: #FFFFFF; letter-spacing: -0.04em; margin: 0 0 0.85rem 0; line-height: 1.05;
}
.tracker-hero-sub {
  color: rgba(255,255,255,0.75); font-size: 1.02rem; max-width: 640px;
  margin: 0 auto; font-weight: 500; line-height: 1.65;
}

/* FOOTER */
.site-footer {
  background: #09090b; color: rgba(255,255,255,0.62);
  padding: 2.5rem 3.5rem; margin-top: 4rem;
}
.footer-bottom {
  max-width: 1200px; margin: 0 auto;
  display: flex; justify-content: space-between; align-items: center;
  font-size: 0.82rem; flex-wrap: wrap; gap: 1rem;
}
.footer-brand-row { display: flex; align-items: center; gap: 10px; }
.footer-brand-logo {
  width: 32px; height: 32px; border-radius: 9px;
  background: rgba(255,255,255,0.95);
  display: inline-flex; align-items: center; justify-content: center; overflow: hidden;
}
.footer-brand { font-size: 1.15rem; font-weight: 900; color: white; letter-spacing: -0.5px; }
.footer-brand span { color: var(--orange-500); }

@media (max-width: 1024px) {
  .live-pill { display: none; }
  .topnav { padding: 0 1.5rem; }
  .site-footer { padding: 2rem 1.5rem; }
}
</style>
"""
st.markdown(css, unsafe_allow_html=True)

# ==========================================
# 5. NAVBAR
# ==========================================
logo_nav_html = icon_img("logo", 30, "📦", radius=8)
logo_footer_html = icon_img("logo", 24, "📦", radius=6)

nav_html = (
    '<nav class="topnav">'
    f'<a href="{HOME_SITE_LINK}" class="brand">'
    f'<span class="brand-logo">{logo_nav_html}</span>'
    '<span class="brand-text">Pack-<span class="n">N</span>-Ship</span>'
    '</a>'
    '<div class="nav-actions">'
    '<span class="live-pill"><span class="live-dot"></span> Cebu Corridor Live</span>'
    f'<a href="{APK_DOWNLOAD_LINK}" target="_blank" rel="noopener noreferrer" class="nav-signup">'
    '<span>Get App</span>'
    '<span>→</span>'
    '</a>'
    '</div>'
    '</nav>'
)
st.markdown(nav_html, unsafe_allow_html=True)

# ==========================================
# 6. TRACKER HERO HEADER
# ==========================================
tracker_hero_html = (
    '<section class="tracker-hero">'
    '<div class="hero-eyebrow"><span class="dot"></span> Real-Time Google Maps Telemetry</div>'
    '<h1 class="tracker-hero-title">Track your package.</h1>'
    '<p class="tracker-hero-sub">Enter your Pack-N-Ship tracking reference (e.g. PNS-0001) for live Google Maps route coordinates, courier verification, escrow status, and Philippine Standard Time (PHT) milestones.</p>'
    '</section>'
)
st.markdown(tracker_hero_html, unsafe_allow_html=True)

# ==========================================
# 7. TRACK SHIPMENT BODY (AUTO-LOAD FROM URL)
# ==========================================
def _get_query_tracking() -> str:
    qp = st.query_params
    for key in ("tracking", "id", "code", "ref"):
        val = qp.get(key)
        if val:
            if isinstance(val, list):
                val = val[0] if val else ""
            val = str(val).strip()
            if val:
                return val
    return ""

default_tracking = _get_query_tracking()

st.markdown('<div style="height:28px;"></div>', unsafe_allow_html=True)

_, track_col, _ = st.columns([0.35, 3.3, 0.35])
with track_col:
    with st.form("tracking_form", clear_on_submit=False):
        col_in, col_btn = st.columns([3.6, 1])
        with col_in:
            tracking_input = st.text_input(
                "Tracking ID",
                value=default_tracking,
                placeholder="Enter Tracking ID (e.g. PNS-0001 or PNS-0368)",
                label_visibility="collapsed",
            )
        with col_btn:
            track_submit = st.form_submit_button("Track Shipment", use_container_width=True)

    active_query = (tracking_input or default_tracking).strip()

    if track_submit or active_query:
        request_id = _parse_tracking_id(active_query)
        if request_id is None:
            st.warning("Please enter a valid tracking ID, e.g. **PNS-0001**.")
        else:
            normalized_code = f"PNS-{request_id:04d}"
            if st.query_params.get("tracking") != normalized_code:
                st.query_params["tracking"] = normalized_code

            with st.spinner("Retrieving live Google Maps telemetry and verification records…"):
                bundle = fetch_tracking_bundle(request_id)

            if bundle is None:
                st.error(f"No shipment record found for **{normalized_code}**.")
            else:
                req = bundle["request"]
                delivery = bundle.get("delivery") or {}
                qr = bundle.get("qr") or {}
                fix = bundle.get("fix") or {}

                pickup_verified = bool(qr.get("pickup_verified"))
                dropoff_verified = bool(qr.get("dropoff_verified"))
                completed = (
                    bool(delivery.get("completed_at"))
                    or dropoff_verified
                    or str(req.get("delivery_status", "")).lower() in ("completed", "delivered")
                )
                cancelled = str(req.get("delivery_status", "")).lower() in ("cancelled", "canceled")

                meta = _status_meta(req.get("delivery_status"), completed=completed)

                p = req.get("pickup") or {}
                d = req.get("dropoff") or {}

                p_label, p_sub = _format_location_display(p)
                d_label, d_sub = _format_location_display(d)

                created_at = req.get("created_at")
                accepted_at = delivery.get("accepted_at")
                completed_at = delivery.get("completed_at")
                eta = delivery.get("estimated_eta")

                provider = _extract_joined_row(delivery.get("provider"))
                vehicle = _extract_joined_row(delivery.get("vehicle"))
                provider_name = " ".join(
                    [pt for pt in [provider.get("first_name"), provider.get("last_name")] if pt]
                ).strip() or "Assigned Courier Partner"
                initials = "".join([w[0].upper() for w in provider_name.split()[:2]]) or "CP"
                vehicle_type = str(vehicle.get("vehicle_type") or "Standard Vehicle").upper()
                plate_num = str(vehicle.get("plate_number") or "").upper()
                vehicle_display = f"{vehicle_type} · {plate_num}" if plate_num else vehicle_type

                est_cost = req.get("estimated_cost")
                try:
                    cost_str = f"₱{float(est_cost):,.2f}"
                except Exception:
                    cost_str = "—"
                pay_status = str(req.get("payment_status") or "unpaid").upper()
                escrow_status = str(req.get("escrow_status") or "pending").title()

                out_for_delivery_done = pickup_verified or completed
                if completed:
                    out_for_delivery_sub = "Completed route handoff"
                elif pickup_verified and fix:
                    out_for_delivery_sub = f"Last GPS ping · {_fmt_dt(fix.get('updated_at'))}"
                elif pickup_verified:
                    out_for_delivery_sub = "In transit along Cebu corridor"
                else:
                    out_for_delivery_sub = "Awaiting pickup verification"

                steps = [
                    {
                        "label": "Booking placed",
                        "time": _fmt_dt(created_at),
                        "done": True,
                        "current": not bool(accepted_at) and not completed and not cancelled,
                    },
                    {
                        "label": "Courier accepted",
                        "time": _fmt_dt(accepted_at) if accepted_at else "Waiting for a courier",
                        "done": bool(accepted_at) or completed,
                        "current": bool(accepted_at) and not pickup_verified and not completed and not cancelled,
                    },
                    {
                        "label": "Package picked up",
                        "time": "Verified with sender QR / PIN" if (pickup_verified or completed) else "Awaiting courier scan",
                        "done": pickup_verified or completed,
                        "current": pickup_verified and not completed and not cancelled,
                    },
                    {
                        "label": "Out for delivery",
                        "time": out_for_delivery_sub,
                        "done": out_for_delivery_done,
                        "current": pickup_verified and not completed and not cancelled,
                    },
                    {
                        "label": "Cancelled" if cancelled else "Delivered",
                        "time": _fmt_dt(completed_at) if completed_at else (f"ETA {_fmt_dt(eta, short_date=True)}" if eta else "Pending completion"),
                        "done": completed or cancelled,
                        "current": completed or cancelled,
                        "danger": cancelled,
                    },
                ]

                timeline_rows = ""
                for i, s in enumerate(steps):
                    dot_bg = "#DC2626" if s.get("danger") else ("#FF751F" if s["done"] else "#E5E7EB")
                    dot_color = "#FFFFFF" if (s["done"] or s.get("danger")) else "#9CA3AF"
                    icon = "✕" if s.get("danger") else ("✓" if s["done"] else "•")
                    title_color = "#111827" if s["done"] else "#6B7280"
                    sub_color = "#FF751F" if (s["current"] and not s.get("danger") and not completed) else "#6B7280"

                    if i == len(steps) - 1:
                        line_html = ""
                    else:
                        next_done = steps[i + 1]["done"]
                        line_color = "#FF751F" if (s["done"] and next_done) else "#E5E7EB"
                        line_html = f'<div style="position:absolute;left:11px;top:26px;bottom:-6px;width:2px;background:{line_color};"></div>'

                    timeline_rows += (
                        f'<div style="position:relative;display:flex;gap:14px;padding-bottom:16px;">'
                        f'<div style="position:relative;flex-shrink:0;">'
                        f'<div style="width:24px;height:24px;border-radius:50%;background:{dot_bg};color:{dot_color};display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:900;box-shadow:0 2px 6px rgba(0,0,0,0.08);">{icon}</div>'
                        f'{line_html}'
                        f'</div>'
                        f'<div style="flex:1;padding-top:1px;">'
                        f'<div style="font-size:14px;font-weight:800;color:{title_color};letter-spacing:-0.2px;line-height:1.25;">{s["label"]}</div>'
                        f'<div style="font-size:12px;font-weight:600;color:{sub_color};margin-top:2px;">{s["time"]}</div>'
                        f'</div>'
                        f'</div>'
                    )

                col_map, col_details = st.columns([1.35, 1.15])

                with col_map:
                    components.html(render_tracking_map_html(bundle), height=470, scrolling=False)

                    courier_card_html = (
                        f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px;">'
                        f'<div style="background:#FFFFFF;border:1px solid #E5E7EB;border-radius:20px;padding:18px;box-shadow:0 10px 28px rgba(15,23,42,0.04);display:flex;flex-direction:column;justify-content:space-between;">'
                        f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:14px;">'
                        f'<div style="width:46px;height:46px;border-radius:14px;background:linear-gradient(135deg,#FF751F,#E4650F);color:#FFFFFF;display:flex;align-items:center;justify-content:center;font-weight:900;font-size:16px;flex-shrink:0;">{initials}</div>'
                        f'<div style="min-width:0;">'
                        f'<div style="font-size:14.5px;font-weight:900;color:#111827;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{provider_name if delivery else "Pending Courier"}</div>'
                        f'<div style="font-size:11.5px;font-weight:700;color:#FF751F;margin-top:2px;">✓ Verified courier partner</div>'
                        f'</div>'
                        f'</div>'
                        f'<div style="background:#F9FAFB;border:1px solid #F3F4F6;border-radius:12px;padding:10px 12px;display:flex;justify-content:space-between;align-items:center;">'
                        f'<span style="font-size:10px;font-weight:800;color:#6B7280;letter-spacing:1px;text-transform:uppercase;">VEHICLE</span>'
                        f'<span style="font-size:12.5px;font-weight:900;color:#111827;">{vehicle_display if delivery else "Awaiting Match"}</span>'
                        f'</div>'
                        f'</div>'
                        f'<div style="background:#FFFFFF;border:1px solid #E5E7EB;border-radius:20px;padding:18px;box-shadow:0 10px 28px rgba(15,23,42,0.04);display:flex;flex-direction:column;justify-content:space-between;">'
                        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">'
                        f'<span style="font-size:10.5px;font-weight:800;color:#6B7280;letter-spacing:1px;text-transform:uppercase;">ESCROW</span>'
                        f'<span style="font-size:10.5px;font-weight:800;color:#059669;background:#ECFDF5;border:1px solid #A7F3D0;padding:3px 9px;border-radius:999px;">{pay_status} · {escrow_status}</span>'
                        f'</div>'
                        f'<div style="background:linear-gradient(135deg,#FF751F,#E4650F);border-radius:14px;padding:14px 16px;color:#FFFFFF;display:flex;justify-content:space-between;align-items:center;box-shadow:0 8px 20px rgba(255,117,31,0.28);">'
                        f'<span style="font-size:12.5px;font-weight:700;color:rgba(255,255,255,0.92);">Total Amount</span>'
                        f'<span style="font-size:21px;font-weight:900;letter-spacing:-0.5px;">{cost_str}</span>'
                        f'</div>'
                        f'</div>'
                        f'</div>'
                    )
                    st.markdown(courier_card_html, unsafe_allow_html=True)

                with col_details:
                    details_card_html = (
                        f'<div style="background:#FFFFFF;border:1px solid #E5E7EB;border-radius:22px;padding:24px;box-shadow:0 16px 40px rgba(15,23,42,0.05);">'
                        f'<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:20px;padding-bottom:16px;border-bottom:1px solid #F3F4F6;flex-wrap:wrap;gap:12px;">'
                        f'<div>'
                        f'<div style="font-size:10px;font-weight:800;letter-spacing:1.4px;color:#9CA3AF;margin-bottom:4px;">TRACKING REFERENCE</div>'
                        f'<div style="font-size:26px;font-weight:900;color:#111827;letter-spacing:-0.6px;line-height:1;">PNS-{req["request_id"]:04d}</div>'
                        f'</div>'
                        f'<div style="background:{meta["bg"]};color:{meta["color"]};border:1px solid {meta["border"]};padding:7px 14px;border-radius:999px;font-size:12px;font-weight:800;">{meta["icon"]} {meta["label"]}</div>'
                        f'</div>'
                        f'<div style="display:flex;gap:14px;margin-bottom:14px;">'
                        f'<div style="display:flex;flex-direction:column;align-items:center;">'
                        f'<div style="width:20px;height:20px;border-radius:50%;border:4px solid #2563EB;background:#FFF;flex-shrink:0;"></div>'
                        f'<div style="width:2px;flex:1;background:#DBEAFE;margin-top:4px;margin-bottom:4px;min-height:22px;"></div>'
                        f'</div>'
                        f'<div style="padding-bottom:4px;">'
                        f'<div style="font-size:10px;font-weight:800;color:#2563EB;letter-spacing:1.2px;margin-bottom:2px;">PICKUP LOCATION (P)</div>'
                        f'<div style="font-size:14px;font-weight:800;color:#111827;line-height:1.35;">{p_label}</div>'
                        f'<div style="font-size:11.5px;font-weight:600;color:#6B7280;margin-top:2px;font-family:ui-monospace,monospace;">{p_sub}</div>'
                        f'</div>'
                        f'</div>'
                        f'<div style="display:flex;gap:14px;margin-bottom:20px;">'
                        f'<div style="display:flex;flex-direction:column;align-items:center;">'
                        f'<div style="width:20px;height:20px;border-radius:50%;background:#059669;display:flex;align-items:center;justify-content:center;flex-shrink:0;">'
                        f'<div style="width:7px;height:7px;background:#FFF;border-radius:50%;"></div>'
                        f'</div>'
                        f'</div>'
                        f'<div>'
                        f'<div style="font-size:10px;font-weight:800;color:#059669;letter-spacing:1.2px;margin-bottom:2px;">DROP-OFF DESTINATION (D)</div>'
                        f'<div style="font-size:14px;font-weight:800;color:#111827;line-height:1.35;">{d_label}</div>'
                        f'<div style="font-size:11.5px;font-weight:600;color:#6B7280;margin-top:2px;font-family:ui-monospace,monospace;">{d_sub}</div>'
                        f'</div>'
                        f'</div>'
                        f'<div style="height:1px;background:#F3F4F6;margin:0 0 18px 0;"></div>'
                        f'<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;">'
                        f'<div style="display:flex;align-items:center;gap:10px;">'
                        f'<div style="width:28px;height:28px;border-radius:8px;background:#FFF7ED;border:1px solid #FED7AA;display:flex;align-items:center;justify-content:center;color:#FF751F;font-weight:900;font-size:14px;">🕒</div>'
                        f'<div style="font-size:15px;font-weight:900;color:#111827;letter-spacing:-0.3px;">Delivery timeline</div>'
                        f'</div>'
                        f'<span style="font-size:10.5px;font-weight:700;color:#9CA3AF;letter-spacing:0.5px;">PHT (UTC+8)</span>'
                        f'</div>'
                        f'{timeline_rows}'
                        f'</div>'
                    )
                    st.markdown(details_card_html, unsafe_allow_html=True)

                if st.button("🔄 Refresh Live Telemetry", use_container_width=True):
                    st.rerun()

# ==========================================
# 8. FOOTER
# ==========================================
footer_html = (
    '<div class="site-footer">'
    '<div class="footer-bottom">'
    '<div class="footer-brand-row">'
    f'<span class="footer-brand-logo">{logo_footer_html}</span>'
    '<div class="footer-brand">Pack-<span>N</span>-Ship</div>'
    '</div>'
    '<span>© 2026 Pack-N-Ship · Cebu Technological University — Main Campus</span>'
    '</div>'
    '</div>'
)
st.markdown(footer_html, unsafe_allow_html=True)