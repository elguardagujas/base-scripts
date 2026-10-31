#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse, csv, hashlib, io, json, sys, time, zipfile, requests


def download_zip(url, retries=5, delay=2):
    for attempt in range(1, retries + 1):
        try:
            print(f"Downloading {url} (attempt {attempt}/{retries})...")
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.content
            if not zipfile.is_zipfile(io.BytesIO(data)):
                print("Error: downloaded content is not a valid ZIP file.", file=sys.stderr)
                sys.exit(1)
            print(f"Downloaded {len(data):,} bytes.")
            return data
        except Exception as e:
            print(f"Attempt {attempt} failed: {e}", file=sys.stderr)
            if attempt < retries:
                time.sleep(delay)
    print("Error: all download attempts failed.", file=sys.stderr)
    sys.exit(1)


def zip_fingerprint(fileobj):
    """Return {name: sha256_hex} for every entry in a ZIP file-like object."""
    with zipfile.ZipFile(fileobj) as zf:
        return {name: hashlib.sha256(zf.read(name)).hexdigest() for name in zf.namelist()}


def zips_match(converted_bytes, local_path):
    """Compare a converted zip (bytes) against the existing file on disk."""
    try:
        a = zip_fingerprint(io.BytesIO(converted_bytes))
        with open(local_path, "rb") as fh:
            b = zip_fingerprint(fh)
    except zipfile.BadZipFile as e:
        print(f"Error reading ZIP: {e}", file=sys.stderr)
        sys.exit(1)

    if a.keys() != b.keys():
        print(f"ZIPs differ - mismatched entries: {', '.join(sorted(a.keys() ^ b.keys()))}")
        return False

    for name in a:
        if a[name] != b[name]:
            print(f"ZIPs differ - content mismatch in: {name}")
            return False

    return True


def read_gtfs_txt(zf, filename):
    """Parse a .txt entry from an open ZipFile; strips all header/value whitespace."""
    with zf.open(filename) as f:
        reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))
        reader.fieldnames = [h.strip() for h in reader.fieldnames]
        return [{k.strip(): v.strip() for k, v in row.items()} for row in reader]


def convert(data):
    """Convert raw GTFS zip bytes to a JSON zip in memory (uncompressed). Returns bytes."""
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as zin, \
         zipfile.ZipFile(buf, "w") as zout:
        for name in sorted(zin.namelist()):
            if name.endswith(".txt"):
                records = read_gtfs_txt(zin, name)
                content = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
                zout.writestr(name.replace(".txt", ".json"), content)
                print(f"  {name} → {name.replace('.txt', '.json')} ({len(records)} rows)")
            else:
                zout.writestr(name, zin.read(name))
                print(f"  {name} (copied)")
    return buf.getvalue()


def compress_and_write(data, output_path):
    """LZMA-compress a zip and write it directly to disk."""
    print(f"Compressing → {output_path} ...")
    with zipfile.ZipFile(io.BytesIO(data)) as zin, \
         zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_LZMA, compresslevel=9) as zout:
        for name in zin.namelist():
            zout.writestr(name, zin.read(name))
    print("Done.")


def main():
    parser = argparse.ArgumentParser(description="Download a GTFS ZIP, convert .txt→JSON, write LZMA zip if changed.")
    parser.add_argument("url", help="URL of the ZIP file to download")
    parser.add_argument("output", help="Output path for the converted ZIP")
    parser.add_argument("-i", "--input", metavar="INPUT_ZIP", help="Existing converted ZIP to compare against (optional)")
    parser.add_argument("-r", "--retries", type=int, default=5, metavar="N", help="Number of download attempts (default: 5)")
    args = parser.parse_args()

    raw = download_zip(args.url, retries=args.retries)

    print("Converting...")
    converted = convert(raw)

    if args.input:
        try:
            if zips_match(converted, args.input):
                print("ZIPs match - nothing to do.")
                sys.exit(0)
        except OSError as e:
            print(f"Error reading input file: {e}", file=sys.stderr)
            sys.exit(1)

    compress_and_write(converted, args.output)


if __name__ == "__main__":
    main()

