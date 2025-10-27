import requests
import json

# CONFIGURATION
bbox = (49.9, -8.6, 60.9, 1.8)  # UK bounding box
CONF_FIXED = 80
CONF_MOBILE_POSSIBLE = 60
OUTPUT_FILE = "docs/osm_cameras.json"

# OVERPASS QUERY
overpass_url = "https://overpass-api.de/api/interpreter"
query = f"""
[out:json][timeout:180];
(
  node["highway"="speed_camera"]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
  node["camera:type"="mobile"]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
  node["radar"="yes"]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
);
out;
"""

print("Fetching OSM data for the UK...")
response = requests.get(overpass_url, params={'data': query})
response.raise_for_status()
data = response.json()

results = []
for node in data.get("elements", []):
    tags = node.get("tags", {})
    if tags.get("highway") == "speed_camera":
        camera_type = "fixed_camera"
        conf = CONF_FIXED
    else:
        camera_type = "mobile_possible_camera"
        conf = CONF_MOBILE_POSSIBLE

    camera = {
        "id": f"osm-{node['id']}",
        "lat": node["lat"],
        "lon": node["lon"],
        "type": camera_type,
        "confidence": conf
    }
    results.append(camera)

final_json = {"results": results}
with open(OUTPUT_FILE, "w") as f:
    json.dump(final_json, f, indent=2)

print(f"Saved {len(results)} cameras to {OUTPUT_FILE}")
