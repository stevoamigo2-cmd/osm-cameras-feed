#!/usr/bin/env python3
import os
import requests
import json
import time

# Configuration
CONF_FIXED = 80
CONF_MOBILE_POSSIBLE = 60
OVERPASS_URL = "https://lz4.overpass-api.de/api/interpreter"
OUTPUT_DIR = "docs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Country bounding boxes (lat_min, lon_min, lat_max, lon_max)
COUNTRY_BBOXES = {
    "uk": [
        (49.9, -8.6, 55.0, -2.0),
        (55.0, -8.6, 60.9, -2.0),
        (49.9, -2.0, 55.0, 1.8),
        (55.0, -2.0, 60.9, 1.8),
    ],
    "fr": [(41.3, -5.1, 51.1, 9.6)],
    "de": [(47.3, 5.9, 55.1, 15.0)],
    "es": [(36.0, -9.4, 43.8, 4.3)],
    "it": [(36.6, 6.6, 47.1, 18.5)],
    "nl": [(50.7, 3.4, 53.6, 7.2)],
    "be": [(49.5, 2.5, 51.5, 6.4)],
    "ie": [(51.4, -10.5, 55.4, -5.3)],
    "pt": [(36.9, -9.5, 42.1, -6.2)],
    "se": [(55.3, 11.1, 69.1, 24.2)],
    "no": [(57.9, 4.7, 71.2, 31.1)],
    "dk": [(54.5, 7.7, 57.9, 12.7)],
    "ch": [(45.8, 5.96, 47.8, 10.5)],
    "at": [(46.4, 9.5, 49.0, 17.2)],
    "pl": [(49.0, 14.1, 54.8, 24.1)],
    "cz": [(48.6, 12.1, 51.1, 19.1)],
    "hu": [(45.7, 16.1, 48.6, 22.9)],
    "ro": [(43.6, 20.3, 48.3, 29.7)],
    "bg": [(41.2, 22.4, 44.2, 28.6)],
    "gr": [(34.8, 19.6, 41.7, 28.3)],
    "us": [(24.5, -125.0, 49.5, -66.9)],
    "ca": [(41.7, -141.0, 83.1, -52.6)],
    "au": [(-44.0, 112.9, -10.7, 153.6)],
    "nz": [(-47.3, 166.3, -34.4, 178.7)],
}

def build_overpass_query(bbox, timeout=180):
    return f"""
    [out:json][timeout:{timeout}];
    (
      node["highway"="speed_camera"]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
      node["camera:type"="mobile"]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
      node["radar"="yes"]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
    );
    out;
    """

def fetch_bbox(bbox, timeout=180, attempts=8, initial_backoff=5):
    """
    Fetch Overpass data for a single bbox with retries and exponential backoff.
    Treat 429 specially by backing off longer. Returns parsed JSON or None.
    """
    query = build_overpass_query(bbox, timeout=timeout)
    backoff = initial_backoff
    for attempt in range(1, attempts + 1):
        try:
            print(f"  Fetching bbox {bbox} (attempt {attempt}/{attempts})...")
            resp = requests.get(OVERPASS_URL, params={"data": query}, timeout=timeout + 30)
            if resp.status_code == 429:
                print(f"    Received 429 Too Many Requests (attempt {attempt}). Backing off {backoff}s.")
                time.sleep(backoff)
                backoff = min(backoff * 2, 300)
                continue
            if resp.status_code >= 500:
                print(f"    Server error {resp.status_code} (attempt {attempt}). Backing off {backoff}s.")
                time.sleep(backoff)
                backoff = min(backoff * 2, 300)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            print(f"    Warning: fetch failed: {e}")
            if attempt < attempts:
                time.sleep(backoff)
                backoff = min(backoff * 2, 300)
            else:
                print("    Error: giving up on this bbox.")
                return None
    return None

def main():
    env_countries = os.environ.get("COUNTRIES")
    if env_countries:
        env_countries = env_countries.strip().lower()

    # Treat 'all' or empty as "use all defined countries"
    if not env_countries or env_countries == "all":
        country_bboxes = COUNTRY_BBOXES.copy()
    else:
        wanted = [c.strip().lower() for c in env_countries.split(",") if c.strip()]
        country_bboxes = {k: v for k, v in COUNTRY_BBOXES.items() if k in wanted}

    if not country_bboxes:
        print("No countries configured to fetch. Exiting.")
        return

    for cc, bboxes in country_bboxes.items():
        print(f"Processing country: {cc} with {len(bboxes)} bbox(es)")
        all_results = []

        for bbox in bboxes:
            data = fetch_bbox(bbox)
            # be gentle with Overpass
            time.sleep(2)
            if not data:
                print(f"    Skipping bbox {bbox} for {cc} due to fetch failures.")
                continue

            for node in data.get("elements", []):
                tags = node.get("tags", {})
                if tags.get("highway") == "speed_camera":
                    camera_type = "fixed_camera"
                    conf = CONF_FIXED
                else:
                    camera_type = "mobile_possible_camera"
                    conf = CONF_MOBILE_POSSIBLE

                camera = {
                    "id": f"osm-{node.get('id')}",
                    "lat": node.get("lat"),
                    "lon": node.get("lon"),
                    "type": camera_type,
                    "confidence": conf,
                }
                all_results.append(camera)

        # Remove duplicates by id
        unique_results = {cam["id"]: cam for cam in all_results if cam.get("id")}.values()
        final_json = {"results": list(unique_results)}

        # Choose filename: keep "osm_cameras.json" for UK to maintain backward compatibility
        if cc == "uk":
            output_file = os.path.join(OUTPUT_DIR, "osm_cameras.json")
        else:
            output_file = os.path.join(OUTPUT_DIR, f"{cc}_osm_cameras.json")

        # Safety guard: only refuse if the canonical filename would be overwritten by a non-UK country
        if os.path.basename(output_file) == "osm_cameras.json" and cc != "uk":
            print(f"    Safety: refusing to write non-UK country {cc} to canonical osm_cameras.json; skipping write.")
            continue

        # Always write per-country file (even if empty) so presence is visible
        try:
            with open(output_file, "w", encoding="utf-8") as fh:
                json.dump(final_json, fh, indent=2, ensure_ascii=False)
            print(f"  Saved {len(final_json['results'])} cameras to {output_file}")
        except Exception as e:
            print(f"  Error writing {output_file}: {e}")

if __name__ == "__main__":
    main()
