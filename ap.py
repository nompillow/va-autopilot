"""Client for the TransferHub autopilot: sends one command to the server and
prints what it says. See RUNBOOK.md.

    python ap.py flights --date 03-NOV-26 --resort PARK --direction ARRIVAL

The token comes from AP_TOKEN or ~/.ap_token.
"""
import json
import os
import sys
import urllib.error
import urllib.request

URL = os.environ.get("AP_URL", "https://transferhub-app-production.up.railway.app") + "/autopilot/cmd"


def token():
    t = os.environ.get("AP_TOKEN")
    if not t:
        with open(os.path.expanduser("~/.ap_token"), encoding="utf-8") as f:
            t = f.read().strip()
    return t


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    req = urllib.request.Request(
        URL, method="POST", data=json.dumps({"args": sys.argv[1:]}).encode(),
        headers={"Authorization": "Bearer " + token(), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=1000) as r:
            sys.stdout.write(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        sys.stdout.write(e.read().decode("utf-8", "replace"))
        sys.exit(f"\n[server answered {e.code}]")


if __name__ == "__main__":
    main()
