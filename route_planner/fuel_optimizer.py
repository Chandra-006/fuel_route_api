"""
fuel_optimizer.py
-----------------
This is the core logic file for the Fuel Route Planner API.
It handles:
  1. Loading fuel price data from CSV
  2. Geocoding start/finish locations
  3. Fetching the driving route
  4. Finding cheapest fuel stops along the route
  5. Calculating total fuel cost
"""

import pandas as pd
import requests
from math import radians, sin, cos, sqrt, atan2
from django.conf import settings


# =============================================================================
# US STATE CENTROIDS (Latitude, Longitude)
# =============================================================================
# Since the CSV only has City and State (no lat/lon), we use the geographic
# center of each US state as an approximation for station coordinates.
# This avoids making thousands of geocoding API calls for every station.
# Key = 2-letter state code, Value = (latitude, longitude)
# =============================================================================
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


# =============================================================================
# LOAD FUEL DATA FROM CSV
# =============================================================================
# This function runs ONCE when the Django server starts up.
# It reads the CSV into a Pandas DataFrame and keeps it in memory.
# This means we never read the file again during requests — very fast!
# =============================================================================
def load_fuel_data():
    # Read the CSV file from the path defined in settings.py
    df = pd.read_csv(settings.FUEL_PRICES_CSV)

    # Strip any accidental whitespace from column names
    df.columns = df.columns.str.strip()

    # Remove rows where Retail Price is missing
    df = df.dropna(subset=['Retail Price'])

    # Convert Retail Price column to numeric (in case of any string values)
    df['Retail Price'] = pd.to_numeric(df['Retail Price'], errors='coerce')

    # Drop any rows that failed to convert to numeric
    df = df.dropna(subset=['Retail Price'])

    # Add lat/lon columns by mapping each station's state to its centroid
    # This gives every station a coordinate without any API calls
    df['lat'] = df['State'].map(
        lambda s: STATE_COORDS.get(str(s).strip().upper(), (None, None))[0]
    )
    df['lon'] = df['State'].map(
        lambda s: STATE_COORDS.get(str(s).strip().upper(), (None, None))[1]
    )

    # Drop stations from unknown states (no coordinates found)
    df = df.dropna(subset=['lat', 'lon'])

    return df


# Load the fuel data into memory at startup — stored as a module-level variable
# so it's shared across all requests without reloading
FUEL_DF = load_fuel_data()


# =============================================================================
# HAVERSINE DISTANCE FORMULA
# =============================================================================
# Calculates the straight-line distance between two GPS coordinates in miles.
# Uses the Haversine formula which accounts for Earth's curvature.
# Parameters: lat1, lon1 = point A | lat2, lon2 = point B
# Returns: distance in miles (float)
# =============================================================================
def haversine(lat1, lon1, lat2, lon2):
    R = 3958.8  # Earth's radius in miles

    # Convert degrees to radians for math functions
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

    # Difference in coordinates
    dlat = lat2 - lat1
    dlon = lon2 - lon1

    # Haversine formula
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2

    # Return distance in miles
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


# =============================================================================
# GEOCODE A LOCATION (City Name → Lat/Lon)
# =============================================================================
# Uses the FREE Nominatim API from OpenStreetMap.
# No API key required.
# Called only TWICE per request — once for start, once for finish.
# Parameters: location = string like "New York, NY"
# Returns: (latitude, longitude) as floats
# =============================================================================
def geocode(location: str):
    url = "https://nominatim.openstreetmap.org/search"

    # Query parameters — restrict to USA results
    params = {
        "q": location + ", USA",
        "format": "json",
        "limit": 1  # We only need the top result
    }

    # Nominatim requires a User-Agent header to identify the app
    headers = {"User-Agent": "FuelRouteAPI/1.0"}

    # Make the API request with a 10 second timeout
    resp = requests.get(url, params=params, headers=headers, timeout=10)
    resp.raise_for_status()  # Raise error if request failed

    results = resp.json()

    # If no results found, raise a clear error message
    if not results:
        raise ValueError(f"Could not geocode location: {location}")

    # Return lat and lon from the first result
    return float(results[0]['lat']), float(results[0]['lon'])


# =============================================================================
# GET DRIVING ROUTE FROM OSRM
# =============================================================================
# Uses the FREE OSRM (Open Source Routing Machine) API.
# No API key required.
# Called only ONCE per request.
# Returns the full route as a list of waypoints and total distance in miles.
# Parameters: start and end coordinates (lat/lon floats)
# Returns: (waypoints list, total_miles float)
# =============================================================================
def get_route(start_lat, start_lon, end_lat, end_lon):
    # OSRM expects coordinates in lon,lat order (opposite of standard!)
    url = (
        f"http://router.project-osrm.org/route/v1/driving/"
        f"{start_lon},{start_lat};{end_lon},{end_lat}"
        f"?overview=full&geometries=geojson&steps=false"
        # overview=full    → gives us the complete route geometry
        # geometries=geojson → returns coordinates as GeoJSON
        # steps=false      → we don't need turn-by-turn directions
    )

    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    # Extract the first (best) route from the response
    route = data['routes'][0]

    # GeoJSON coordinates are [longitude, latitude] pairs
    coords = route['geometry']['coordinates']

    # Convert distance from meters to miles
    distance_miles = route['legs'][0]['distance'] / 1609.34

    # Flip to [lat, lon] format for consistency in our code
    waypoints = [[c[1], c[0]] for c in coords]

    return waypoints, distance_miles


# =============================================================================
# FIND THE CHEAPEST FUEL STATION NEAR A POINT
# =============================================================================
# Given a lat/lon point on the route, finds the cheapest fuel station
# within the given radius using vectorized distance calculation.
# Parameters: lat, lon = route point | radius_miles = search radius
# Returns: a single DataFrame row (the best station)
# =============================================================================
def find_best_station(lat, lon, radius_miles=150):
    # Work on a copy so we don't modify the global DataFrame
    df = FUEL_DF.copy()

    # Calculate distance from the given point to every station in the CSV
    # Using .apply() runs haversine on every row — fast with Pandas
    df['dist'] = df.apply(
        lambda row: haversine(lat, lon, row['lat'], row['lon']), axis=1
    )

    # Filter to only stations within the search radius
    nearby = df[df['dist'] <= radius_miles]

    # If no stations found within radius, fall back to the 5 closest stations
    if nearby.empty:
        nearby = df.nsmallest(5, 'dist')

    # Return the station with the lowest Retail Price
    best = nearby.loc[nearby['Retail Price'].idxmin()]
    return best


# =============================================================================
# MAIN ROUTE PLANNER FUNCTION
# =============================================================================
# This is the main function called by the API view.
# It orchestrates all the steps:
#   1. Geocode start & finish (2 API calls)
#   2. Get driving route (1 API call)
#   3. Walk the route and find cheap fuel stops every 450 miles
#   4. Calculate cost at each stop
#   5. Build Google Maps URL
#   6. Return the complete result
# Parameters: start, finish = location strings
# Returns: dictionary with all route and fuel stop data
# =============================================================================
def plan_route(start: str, finish: str):

    # --- Vehicle & fuel constants ---
    MAX_RANGE = 500   # Maximum miles the vehicle can travel on a full tank
    REFUEL_AT = 450   # Trigger a fuel stop search after this many miles
                      # (50 mile buffer before running out)
    MPG = 10          # Vehicle fuel efficiency in miles per gallon

    # -------------------------------------------------------------------------
    # STEP 1: Geocode the start and finish locations
    # Converts "New York, NY" → (40.71, -74.00) etc.
    # This uses 2 Nominatim API calls
    # -------------------------------------------------------------------------
    start_lat, start_lon = geocode(start)
    end_lat,   end_lon   = geocode(finish)

    # -------------------------------------------------------------------------
    # STEP 2: Get the driving route between start and finish
    # Returns a list of waypoints (lat/lon pairs) along the route
    # and the total distance in miles
    # This uses 1 OSRM API call
    # -------------------------------------------------------------------------
    waypoints, total_miles = get_route(start_lat, start_lon, end_lat, end_lon)

    # -------------------------------------------------------------------------
    # STEP 3: Walk along the route and find fuel stops
    # We divide the total miles evenly across all waypoints to know
    # how many miles each waypoint step represents
    # -------------------------------------------------------------------------
    num_wps          = len(waypoints)
    miles_per_wp     = total_miles / max(num_wps - 1, 1)  # miles between each waypoint
    miles_since_fill = 0.0   # tracks miles driven since last fuel stop
    fuel_stops       = []    # list to collect all fuel stop details
    total_cost       = 0.0   # accumulates total fuel cost in USD
    total_gallons    = 0.0   # accumulates total gallons used

    # Iterate through every waypoint on the route
    for i in range(1, num_wps):
        # Add the distance of this waypoint step to our running total
        miles_since_fill += miles_per_wp

        # Check if we've hit the refuel threshold (450 miles)
        if miles_since_fill >= REFUEL_AT:
            # Get the current waypoint coordinates
            wp = waypoints[i]

            # Find the cheapest station within 150 miles of this waypoint
            station = find_best_station(wp[0], wp[1], radius_miles=150)

            # Calculate how many gallons needed to cover the miles driven
            gallons = miles_since_fill / MPG

            # Calculate cost at this station
            cost = gallons * float(station['Retail Price'])

            # Add to running totals
            total_cost    += cost
            total_gallons += gallons

            # Add this stop's details to the fuel_stops list
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

            # Reset the miles counter after fueling up
            miles_since_fill = 0.0

    # -------------------------------------------------------------------------
    # STEP 4: Handle the remaining miles after the last fuel stop
    # (the final leg to the destination)
    # -------------------------------------------------------------------------
    if miles_since_fill > 0:
        # Calculate gallons for the remaining distance
        gallons = miles_since_fill / MPG

        # Find cheapest station near the destination
        station = find_best_station(end_lat, end_lon, radius_miles=150)

        # Calculate cost for this final leg
        cost = gallons * float(station['Retail Price'])

        total_cost    += cost
        total_gallons += gallons

        # Add the final stop
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

    # -------------------------------------------------------------------------
    # STEP 5: Build a Google Maps URL with all stops
    # Format: https://www.google.com/maps/dir/Start/Stop1/Stop2/Finish
    # -------------------------------------------------------------------------
    map_points = (
        [start] +
        [f"{s['city']}, {s['state']}" for s in fuel_stops] +
        [finish]
    )

    # Replace spaces with + for URL encoding
    map_points_encoded = "/".join(p.replace(" ", "+") for p in map_points)
    google_maps_url = f"https://www.google.com/maps/dir/{map_points_encoded}"

    # -------------------------------------------------------------------------
    # STEP 6: Return the complete result as a dictionary
    # This gets serialized to JSON by Django REST Framework
    # route_waypoints is thinned (every 20th point) to keep response size small
    # -------------------------------------------------------------------------
    return {
        "start":               start,
        "finish":              finish,
        "total_route_miles":   round(total_miles, 1),
        "total_gallons_used":  round(total_gallons, 2),
        "total_fuel_cost_usd": round(total_cost, 2),
        "fuel_stops":          fuel_stops,
        "google_maps_url":     google_maps_url,
        "route_waypoints":     waypoints[::20],  # Every 20th waypoint to reduce response size
    }