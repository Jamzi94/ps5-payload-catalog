#!/usr/bin/env python3
"""
Genere payloads.json a partir des dernieres releases GitHub listees dans repos.json.
Aucune dependance externe : utilise uniquement la stdlib.

Variables d'environnement :
  GITHUB_TOKEN  -> facultatif mais recommande (augmente le rate limit a ~1000/h)
"""

import json
import os
import sys
import hashlib
import urllib.request
import urllib.error

API = "https://api.github.com/repos/{owner}/{repo}/releases/latest"

TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()


def http_get_json(url):
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "ps5-payload-catalog-builder")
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def sha256_of_url(url):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "ps5-payload-catalog-builder")
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    h = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=120) as r:
        for chunk in iter(lambda: r.read(1024 * 256), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    cfg = json.load(open("repos.json", encoding="utf-8"))

    exts = tuple(e.lower() for e in cfg.get("asset_extensions", [".elf", ".bin"]))
    want_checksum = bool(cfg.get("compute_checksum", False))

    payloads = []

    for entry in cfg["repos"]:
        owner, repo = entry["owner"], entry["repo"]
        label = entry.get("label", repo)
        url = API.format(owner=owner, repo=repo)
        print(f"-> {owner}/{repo}", flush=True)

        try:
            data = http_get_json(url)
        except urllib.error.HTTPError as e:
            print(f"   ! {e.code} {e.reason} (pas de release 'latest' ?) - ignore", flush=True)
            continue
        except Exception as e:
            print(f"   ! erreur reseau: {e} - ignore", flush=True)
            continue

        version = data.get("tag_name") or data.get("name") or ""
        assets = data.get("assets", [])

        matched = [a for a in assets if a["name"].lower().endswith(exts)]
        if not matched:
            print(f"   ! aucun asset {exts} dans {version} - ignore", flush=True)
            continue

        for a in matched:
            filename = a["name"]
            dl = a["browser_download_url"]
            # nom lisible : "Label - fichier" si plusieurs assets, sinon juste "Label"
            name = label if len(matched) == 1 else f"{label} ({filename})"

            payload = {
                "name": name,
                "filename": filename,
                "url": dl,
                "description": f"{label} - source: github.com/{owner}/{repo}",
                "version": version,
            }

            if want_checksum:
                try:
                    print(f"   sha256 {filename} ...", flush=True)
                    payload["checksum"] = sha256_of_url(dl)
                except Exception as e:
                    print(f"   ! checksum echoue: {e}", flush=True)

            payloads.append(payload)
            print(f"   + {filename}  [{version}]", flush=True)

    # "name" DOIT apparaitre avant "payloads" (exigence du parser)
    catalog = {
        "name": cfg.get("catalog_name", "Custom Payloads"),
        "payloads": payloads,
    }

    with open("payloads.json", "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"\nOK : {len(payloads)} payload(s) ecrit(s) dans payloads.json", flush=True)
    if not payloads:
        # ne pas casser le workflow, mais signaler
        print("ATTENTION : catalogue vide.", flush=True)


if __name__ == "__main__":
    main()
