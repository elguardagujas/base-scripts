#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import glob, os, re, subprocess, sys, requests
from datetime import datetime

def resolve_nap(api_url):
  key = os.environ.get("NAP_API_KEY")
  if not key:
    raise RuntimeError("NAP_API_KEY not set")
  r = requests.get(api_url, headers={"ApiKey": key})
  r.raise_for_status()
  payload = r.json()
  if not payload.get("success"):
    raise RuntimeError(payload.get("message", "API error"))
  return payload["data"]["enlaceDescarga"]

RESOLVERS = [
  (r"^https://nap\.transportes\.gob\.es/", resolve_nap),
  (r".*",                                   lambda url: url),
]

def resolve(url):
  return next(fn for pattern, fn in RESOLVERS if re.match(pattern, url))(url)

def latest_zip(basename):
  matches = sorted(glob.glob(f"data/{basename}_????-??-??_??-??.zip"))
  return matches[-1] if matches else None

def run_dump(basename, src):
  try:
    url = resolve(src)
  except Exception as e:
    print(f"\n[{basename}] resolve failed: {e}", file=sys.stderr)
    return False

  ts       = datetime.utcnow().strftime("%Y-%m-%d_%H-%M")
  output   = f"data/{basename}_{ts}.zip"
  existing = latest_zip(basename)

  cmd = [sys.executable, "tools/gtfs_dump.py", url, output]
  if existing:
    cmd += ["--input", existing]

  print(f"\n[{basename}] {existing or '(no local file)'} -> {output}")
  return subprocess.run(cmd).returncode == 0

def process(SOURCES):
  os.makedirs("data", exist_ok=True)
  failures = [b for b, u in SOURCES.items() if not run_dump(b, u)]

  print()
  if failures:
    print(f"Failed: {', '.join(failures)}", file=sys.stderr)
    sys.exit(1)
  print("Done.")

