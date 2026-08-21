import argparse
import json
import random
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish simulated sensor data")
    parser.add_argument("--device-id", required=True)
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--count", type=int, default=10)
    args = parser.parse_args()
    if args.interval < 0:
        parser.error("--interval must be zero or greater")
    if args.count < 1:
        parser.error("--count must be one or greater")
    return args


def publish(url: str, payload: dict) -> None:
    request = urllib.request.Request(
        f"{url.rstrip('/')}/measurements",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        result = json.load(response)
    print(json.dumps(result, ensure_ascii=False))


def main() -> None:
    args = parse_args()
    for sequence in range(args.count):
        payload = {
            "device_id": args.device_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "temperature": round(random.uniform(20, 30), 2),
            "humidity": round(random.uniform(35, 80), 2),
            "pressure": round(random.uniform(990, 1030), 2),
        }
        try:
            publish(args.url, payload)
        except (urllib.error.URLError, TimeoutError) as error:
            raise SystemExit(f"Could not publish measurement: {error}") from error
        if sequence < args.count - 1:
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
