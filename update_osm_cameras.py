import os
import requests
import json
import time

# CONFIGURATION
bboxes = [
    (49.9, -8.6, 55.0, -2.0),
    (55.0, -8.6, 60.9, -2.0),
    (49.9, -2.0, 55.0, 1.8),
    (55.0, -2.0, 60.9, 1.8)
]
CONF_FIXED = 80
CONF_MOBILE_POSSIBLE = 60
OUTPUT_FILE = "docs/osm_cameras.json"

# Make sure the folder exists
os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

# OVERPASS URL (mirror to reduce timeouts)
overpass_url = "https://lz4.overpass-api.de/api/interpreter"

all_results = []

def fetch_bbox(bbox):
    query = f"""
    [out:json][timeout:180];
    (
      node["highway"="speed_camera"]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
      node["camera:type"="mobile"]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
      node["radar"="yes"]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
    );
    out;
    """
    for attempt in range(3):
        try:
            print(f"Fetching OSM data for bbox {bbox} (attempt {attempt+1})...")
            response = requests.get(overpass_url, params={'data': query}, timeout=300)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Attempt {attempt+1} failed: {e}")
            if attempt < 2:
                time.sleep(10)
            else:
                raise

for bbox in bboxes:
    data = fetch_bbox(bbox)
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
        all_results.append(camera)

# Remove duplicates (by id)
unique_results = {cam["id"]: cam for cam in all_results}.values()

final_json = {"results": list(unique_results)}
with open(OUTPUT_FILE, "w") as f:
    json.dump(final_json, f, indent=2)

print(f"Saved {len(final_json['results'])} cameras to {OUTPUT_FILE}")
