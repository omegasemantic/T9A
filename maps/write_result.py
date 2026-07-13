#!/usr/bin/env python3
# write_result.py — read steps.json, print plain text summary

import json

with open('steps.json') as f:
    data = json.load(f)

print(f"{data.get('origin', '')} > {data.get('dest', '')}")
print(f"Arrive   : {data.get('arrival', 'unknown')}")

for step in data['steps']:
    if step['type'] == 'WALK':
        print(f"WALK: {step['instruction']} ({step['distance']})")
    else:
        print()
        print(f"{step['dep_time']} {step['type']} {step['line']} towards {step['headsign']}. Depart {step['depart']}")
        print(f"{step['arr_time']} arrive {step['arrive']}. {step['stops']} stops")
        print()

print()
print(f"Duration : {data['duration']} ({data['distance']})")
