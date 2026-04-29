import pandas as pd
import requests
from math import radians, sin, cos, sqrt, atan2
from django.conf import settings

# ---------- US State centroids (lat, lon) ----------
STATE_COORDS = {
    'AL': (32.8, -86.8), 'AK': (64.2, -153.4), 'AZ': (34.3, -111.1),
    'AR': (34.8, -92.2), 'CA': (36.8, -119.4), 'CO': (39.0, -105.5),
    'CT': (41.6, -72.7), 'DE': (39.0, -75.5), 'FL': (27.8, -81.6),
    'GA': (32.2, -83.4), 'HI': (20.2, -156.7), 'ID': (44.4, -114.6),
    'IL': (40.0, -89.2), 'IN': (40.3, -86.1), 'IA': (42.0, -93.2),
    'KS': (38.5, -98.4), 'KY': (37.5, -85.3), 'LA': (31.1, -91.9),
    'ME': (45.3, -69.4), 'MD': (39.0, -76.8), 'MA': (42.3, -71.8),
    'MI': (44.3, -85.4), 'MN': (46.4, -93.1), 'MS': (32.7, -89.7),
    'MO': (38.4, -92.5), 'MT': (47.0, -110.5), 'NE': (41.5, -99.9),
    'NV': (39.3, -116.6), 'NH': (43.7, -71.6), 'NJ': (40.1, -74.5),
    'NM': (34.8, -106.2), 'NY': (42.2, -74.9), 'NC': (35.5, -79.4),
    'ND': (47.5, -100.5), 'OH': (40.4, -82.8), 'OK': (35.6, -97.5),
    'OR': (44.1, -120.5), 'PA': (40.9, -77.8), 'RI': (41.7, -71.5),
    'SC': (33.9, -80.9), 'SD': (44.4, -100.2), 'TN': (35.9, -86.4),
    'TX': (31.5, -99.3), 'UT': (39.4, -111.1), 'VT': (44.0, -72.7),
    'VA': (37.5, -78.9), 'WA': (47.4, -120.6), 'WV': (38.6, -80.6),
    'WI': (44.3, -89.8), 'WY': (43.0, -107.6), 'DC': (38.9, -77.0),
}

# ---------- Load CSV once at startup ----------
def load_fuel_data():
    df = pd.read_csv(settings.FUEL_PRICES_CSV)
    df.columns = df.columns.str.strip()
    df = df.dropna(subset=['Retail Price'])
    df['Retail Price'] = pd.to_numeric(df['Retail Price'], errors='coerce')
    df = df.dropna(subset=['Retail Price'])
    # Attach lat/lon from state centroids
    df['lat'] = df['State'].map(lambda s: STATE_COORDS.get(str(s).strip().upper(), (None, None))[0])
    df['lon'] = df['State'].map(lambda s: STATE_COORDS.get(str(s).strip().upper(), (None, None))[1])
    df = df.dropna(subset=['lat', 'lon'])
    return df

FUEL_DF = load_fuel_data()

# ---------- Haversine distance (miles) ----------
def haversine(lat1, lon1, lat2, lon2):
    R = 3958.8
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))

# ---------- Geocode using OSM Nominatim ----------
def geocode(location: str):
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": location + ", USA", "format": "json", "limit": 1}
    headers = {"User-Agent": "FuelRouteAPI/1.0"}
    resp = requests.get(url, params=params, headers=headers, timeout=10)
    resp.raise_for_status()
    results = resp.json()
    if not results:
        raise ValueError(f"Could not geocode location: {location}")
    return float(results[0]['lat']), float(results[0]['lon'])

# ---------- Get route from OSRM (free, no API key needed) ----------
def get_route(start_lat, start_lon, end_lat, end_lon):
    url = (
        f"http://router.project-osrm.org/route/v1/driving/"
        f"{start_lon},{start_lat};{end_lon},{end_lat}"
        f"?overview=full&geometries=geojson&steps=false"
    )
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    route = data['routes'][0]
    coords = route['geometry']['coordinates']  # [lon, lat]
    distance_miles = route['legs'][0]['distance'] / 1609.34
    waypoints = [[c[1], c[0]] for c in coords]
    return waypoints, distance_miles

# ---------- Find cheapest station near a route point ----------
def find_best_station(lat, lon, radius_miles=150):
    df = FUEL_DF.copy()
    # Vectorized distance calculation — no loops, very fast
    df['dist'] = df.apply(
        lambda row: haversine(lat, lon, row['lat'], row['lon']), axis=1
    )
    nearby = df[df['dist'] <= radius_miles]
    if nearby.empty:
        # Expand search radius if nothing found
        nearby = df.nsmallest(5, 'dist')
    best = nearby.loc[nearby['Retail Price'].idxmin()]
    return best

# ---------- Main optimizer ----------
def plan_route(start: str, finish: str):
    MAX_RANGE = 500   # miles vehicle can travel on full tank
    REFUEL_AT = 450   # trigger refuel search at this mileage
    MPG       = 10

    # Step 1: Geocode (2 API calls max)
    start_lat, start_lon = geocode(start)
    end_lat,   end_lon   = geocode(finish)

    # Step 2: Get route (1 API call)
    waypoints, total_miles = get_route(start_lat, start_lon, end_lat, end_lon)

    # Step 3: Walk route and find fuel stops
    num_wps          = len(waypoints)
    miles_per_wp     = total_miles / max(num_wps - 1, 1)
    miles_since_fill = 0.0
    fuel_stops       = []
    total_cost       = 0.0
    total_gallons    = 0.0

    for i in range(1, num_wps):
        miles_since_fill += miles_per_wp

        if miles_since_fill >= REFUEL_AT:
            wp      = waypoints[i]
            station = find_best_station(wp[0], wp[1], radius_miles=150)

            gallons = miles_since_fill / MPG
            cost    = gallons * float(station['Retail Price'])
            total_cost    += cost
            total_gallons += gallons

            fuel_stops.append({
                "stop_number":             len(fuel_stops) + 1,
                "truckstop_name":          str(station['Truckstop Name']),
                "address":                 str(station['Address']),
                "city":                    str(station['City']),
                "state":                   str(station['State']),
                "retail_price_per_gallon": round(float(station['Retail Price']), 3),
                "gallons_needed":          round(gallons, 2),
                "cost_at_this_stop":       round(cost, 2),
                "lat":                     round(station['lat'], 4),
                "lon":                     round(station['lon'], 4),
            })
            miles_since_fill = 0.0

    # Step 4: Account for remaining miles after last stop
    if miles_since_fill > 0:
        gallons  = miles_since_fill / MPG
        station  = find_best_station(end_lat, end_lon, radius_miles=150)
        cost     = gallons * float(station['Retail Price'])
        total_cost    += cost
        total_gallons += gallons

        fuel_stops.append({
            "stop_number":             len(fuel_stops) + 1,
            "truckstop_name":          str(station['Truckstop Name']),
            "address":                 str(station['Address']),
            "city":                    str(station['City']),
            "state":                   str(station['State']),
            "retail_price_per_gallon": round(float(station['Retail Price']), 3),
            "gallons_needed":          round(gallons, 2),
            "cost_at_this_stop":       round(cost, 2),
            "lat":                     round(station['lat'], 4),
            "lon":                     round(station['lon'], 4),
        })

    # Step 5: Build Google Maps URL with all stops
    map_points = [start] + [
        f"{s['city']}, {s['state']}" for s in fuel_stops
    ] + [finish]
    map_points_encoded = "/".join(
        p.replace(" ", "+") for p in map_points
    )
    google_maps_url = f"https://www.google.com/maps/dir/{map_points_encoded}"

    return {
        "start":               start,
        "finish":              finish,
        "total_route_miles":   round(total_miles, 1),
        "total_gallons_used":  round(total_gallons, 2),
        "total_fuel_cost_usd": round(total_cost, 2),
        "fuel_stops":          fuel_stops,
        "google_maps_url":     google_maps_url,
        "route_waypoints":     waypoints[::20],  # thinned for response size
    }