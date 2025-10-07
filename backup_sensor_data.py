#!/usr/bin/env python3
import os
import requests
import pandas as pd
from datetime import datetime

THINGSPEAK_URL = "https://api.thingspeak.com/channels/2974588/feeds.json"

def fetch_lahn_sensors_df() -> pd.DataFrame:
    print("Fetching Lahn sensor data...")
    resp = requests.get(THINGSPEAK_URL)
    resp.raise_for_status()
    data = resp.json()
    # extract channel metadata → human-friendly column names
    channel_meta = data["channel"]
    field_map = {
        f"field{i}": channel_meta[f"field{i}"]
        for i in range(1, 7)
    }
    # load feeds into DataFrame
    df = pd.json_normalize(data["feeds"])
    df = df.rename(columns=field_map)
    df["created_at"] = pd.to_datetime(df["created_at"])
    for col in field_map.values():
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df

def main():
    # 1) fetch
    df = fetch_lahn_sensors_df()

    # 2) ensure backup dir
    backup_dir = os.path.join(os.path.dirname(__file__), "backups")
    os.makedirs(backup_dir, exist_ok=True)

    # 3) build filename with UTC date
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    filename = f"lahn_backup_{ts}.csv"
    path = os.path.join(backup_dir, filename)

    # 4) save
    df.to_csv(path, index=False)
    print(f"Saved backup to {path}")

if __name__ == "__main__":
    main()
