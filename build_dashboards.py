"""
build_dashboards.py

Regenerates both dashboard HTML files from their templates and today's
data, writing them to dashboard_output/. This is the "recompute the
numbers" half of a daily refresh -- publishing the resulting files to
the live Artifact URLs is a separate step (the Artifact tool isn't
available from plain Python, only from a Claude session), documented in
README.md's "Keeping the dashboards current" section.

Usage: python build_dashboards.py [--refresh]
"""

import argparse
import json
import os

import build_dashboard1_data
import build_dashboard2_data

TEMPLATE_1 = "dashboard1_template.html"
TEMPLATE_2 = "dashboard2_template.html"
OUTPUT_DIR = "dashboard_output"
OUTPUT_1 = os.path.join(OUTPUT_DIR, "dashboard1.html")
OUTPUT_2 = os.path.join(OUTPUT_DIR, "dashboard2.html")


def render(template_path: str, placeholder: str, data: dict, output_path: str):
    with open(template_path) as f:
        html = f.read()
    html = html.replace(placeholder, json.dumps(data))
    with open(output_path, "w") as f:
        f.write(html)


def main(force_refresh: bool = False):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    data1 = build_dashboard1_data.build_data(force_refresh=force_refresh)
    render(TEMPLATE_1, "__DASHBOARD1_DATA_JSON__", data1, OUTPUT_1)
    print(f"Wrote {OUTPUT_1} -- as of {data1['as_of']}, composite {data1['composite']}, zone {data1['confirmed_zone']}")

    data2 = build_dashboard2_data.build_data(force_refresh=force_refresh)
    render(TEMPLATE_2, "__DATA_JSON__", data2, OUTPUT_2)
    print(f"Wrote {OUTPUT_2} -- as of {data2['as_of']}, composite {data2['composite']}, zone {data2['confirmed_zone']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="force-refresh cached price/F&G data")
    args = parser.parse_args()

    main(force_refresh=args.refresh)
