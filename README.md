# ⛽ Fuel Route Planner API

A Django REST API that calculates the optimal fuel stops along a driving route within the USA, based on real fuel prices. Returns cheapest stations to refuel, total fuel cost, and a Google Maps link.

---

## 🚀 Features

- Takes a **start** and **finish** location within the USA
- Returns **optimal fuel stops** based on cheapest prices along the route
- Supports routes requiring **multiple fuel stops** (vehicle max range: 500 miles)
- Calculates **total fuel cost** assuming 10 miles per gallon
- Returns a **Google Maps URL** with all stops plotted
- Uses only **3 free API calls** per request — no paid APIs needed

---

## 🛠️ Tech Stack

| Tool | Purpose |
|---|---|
| Django 5.x | Web framework |
| Django REST Framework | API layer |
| Pandas | CSV fuel price data processing |
| OSRM (free) | Driving route & distance |
| Nominatim / OSM (free) | Geocoding start & finish locations |
| CSV File | Fuel price data (no database needed) |

---

## 📁 Project Structure

```
fuel_route_api/
├── fuel_route/
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── route_planner/
│   ├── fuel_optimizer.py   # Core logic
│   ├── views.py            # API view
│   └── urls.py             # App URLs
├── fuel-prices-for-be-assessment.csv
├── manage.py
└── README.md
```

---

## ⚙️ Setup & Installation

### 1. Clone the project and navigate into it
```bash
cd fuel_route_api
```

### 2. Create and activate virtual environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Mac/Linux
python -m venv venv
source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install django djangorestframework pandas requests
```

### 4. Place the fuel prices CSV in the root folder
```
fuel_route_api/
└── fuel-prices-for-be-assessment.csv   ✅
```

### 5. Run migrations
```bash
python manage.py migrate
```

### 6. Start the server
```bash
python manage.py runserver
```

---

## 📡 API Usage

### Endpoint
```
POST http://127.0.0.1:8000/api/route/plan/
```

### Request Body (JSON)
```json
{
    "start": "New York, NY",
    "finish": "Los Angeles, CA"
}
```

### Example Response
```json
{
    "start": "New York, NY",
    "finish": "Los Angeles, CA",
    "total_route_miles": 2791.5,
    "total_gallons_used": 279.15,
    "total_fuel_cost_usd": 845.23,
    "fuel_stops": [
        {
            "stop_number": 1,
            "truckstop_name": "PILOT TRAVEL CENTER #123",
            "address": "I-70, EXIT 162",
            "city": "Columbus",
            "state": "OH",
            "retail_price_per_gallon": 2.999,
            "gallons_needed": 45.0,
            "cost_at_this_stop": 134.95,
            "lat": 40.4,
            "lon": -82.8
        }
    ],
    "google_maps_url": "https://www.google.com/maps/dir/New+York,+NY/Columbus,+OH/Los+Angeles,+CA",
    "route_waypoints": [[40.71, -74.00], [40.50, -80.10], ...]
}
```

---

## 🔁 How It Works

1. **Geocode** start and finish using Nominatim (2 API calls)
2. **Fetch driving route** using OSRM (1 API call)
3. **Walk the route** every 450 miles and find the cheapest fuel station from the CSV near that point
4. **Calculate cost** at each stop based on gallons needed at 10 MPG
5. **Return** all stops, total cost, and a Google Maps URL

> Total external API calls per request: **3 maximum**

---

## 🗺️ Free APIs Used

### OSRM — Open Source Routing Machine
- URL: `http://router.project-osrm.org`
- No API key required
- Provides full driving route with coordinates

### Nominatim — OpenStreetMap
- URL: `https://nominatim.openstreetmap.org`
- No API key required
- Converts city names to lat/lon coordinates

---

## 📌 Key Assumptions

| Parameter | Value |
|---|---|
| Vehicle max range | 500 miles |
| Refuel trigger | Every 450 miles |
| Fuel efficiency | 10 miles per gallon |
| Search radius for stations | 150 miles from route point |

---

## 🧪 Test Routes to Try

```json
{ "start": "New York, NY", "finish": "Los Angeles, CA" }
{ "start": "Chicago, IL", "finish": "Houston, TX" }
{ "start": "Seattle, WA", "finish": "Miami, FL" }
{ "start": "Boston, MA", "finish": "Denver, CO" }
```

---

## 📄 License

MIT License — free to use and modify.
