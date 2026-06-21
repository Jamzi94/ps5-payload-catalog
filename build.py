#!/usr/bin/env python3
"""
Genere payloads.json a partir des releases GitHub listees dans repos.json.
Aucune dependance externe : stdlib uniquement.

Payload Manager affiche le NOM DE FICHIER comme titre et en extrait la version.
On encode donc "label_version.elf" dans le filename, et la date de publication
dans la description (seul champ libre affiche par PM).

Options par repo (repos.json) :
  owner, repo            (requis)
  label                  nom affiche (defaut: repo)
  keep                   nb de releases (avec asset) a garder (defaut: 1).
                         keep > 1 inclut aussi les test/pre-releases.

Options globales :
  catalog_name, asset_extensions, compute_checksum

Env : GITHUB_TOKEN (recommande, augmente le rate limit).
"""

import json
import os
import re
import hashlib
import urllib.request
import urllib.error
from collections import defaultdict
from datetime import datetime

LATEST = "https://api.github.com/repos/{owner}/{repo}/releases/latest"
LIST = "https://api.github.com/repos/{owner}/{repo}/releases?per_page=30"

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


def sanitize(s):
    return re.sub(r"[^A-Za-z0-9._-]+", "-", s or "").strip("-")


def fmt_date(iso):
    """'2026-06-12T17:50:00Z' -> '12/06/2026'."""
    if not iso:
        return ""
    try:
        return datetime.strptime(iso[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return ""


def releases_for(entry):
    owner, repo = entry["owner"], entry["repo"]
    keep = int(entry.get("keep", 1))
    if keep <= 1:
        return [http_get_json(LATEST.format(owner=owner, repo=repo))]
    rels = http_get_json(LIST.format(owner=owner, repo=repo))
    return [r for r in rels if not r.get("draft", False)]


def assets_from(release, exts):
    version = release.get("tag_name") or release.get("name") or ""
    is_pre = bool(release.get("prerelease", False))
    date = fmt_date(release.get("published_at"))
    matched = [a for a in release.get("assets", []) if a["name"].lower().endswith(exts)]
    return version, is_pre, date, matched


def main():
    cfg = json.load(open("repos.json", encoding="utf-8"))
    exts = tuple(e.lower() for e in cfg.get("asset_extensions", [".elf", ".bin"]))
    want_checksum = bool(cfg.get("compute_checksum", False))

    items = []

    for entry in cfg["repos"]:
        owner, repo = entry["owner"], entry["repo"]
        label = entry.get("label", repo)
        slug = sanitize(label)
        keep = int(entry.get("keep", 1))
        print(f"-> {owner}/{repo}", flush=True)

        try:
            releases = releases_for(entry)
        except urllib.error.HTTPError as e:
            print(f"   ! {e.code} {e.reason} - ignore", flush=True)
            continue
        except Exception as e:
            print(f"   ! erreur reseau: {e} - ignore", flush=True)
            continue

        kept = 0
        for rel in releases:
            if kept >= keep:
                break
            version, is_pre, date, matched = assets_from(rel, exts)
            if not matched:
                if keep > 1:
                    print(f"   . {version} : aucun asset {exts} - cherche plus loin", flush=True)
                continue
            tag = " (pre-release)" if is_pre else ""
            kept += 1

            for a in matched:
                ext = os.path.splitext(a["name"])[1] or ".elf"
                # nom de fichier = label_version(.ext)  -> PM affiche label + version
                fname = f"{slug}_{sanitize(version)}{ext}"
                if len(matched) > 1:  # plusieurs binaires dans la meme release
                    stem = sanitize(os.path.splitext(a["name"])[0])
                    fname = f"{slug}_{sanitize(version)}_{stem}{ext}"

                date_txt = f"Publie le {date} - " if date else ""
                items.append({
                    "name": f"{label} {version}{tag}".strip(),
                    "filename": fname,
                    "url": a["browser_download_url"],
                    "description": f"{date_txt}{label}{tag} - github.com/{owner}/{repo}",
                    "version": version,
                })
                print(f"   + {fname}  [{version}]{tag}  {date}", flush=True)

        if kept == 0:
            print(f"   ! aucune release avec asset {exts}", flush=True)

    # securite : si deux entrees finissent avec le meme filename -> suffixe numerique
    groups = defaultdict(list)
    for it in items:
        groups[it["filename"]].append(it)
    for fn, grp in groups.items():
        if len(grp) > 1:
            root, ext = os.path.splitext(fn)
            for i, it in enumerate(grp[1:], start=2):
                it["filename"] = f"{root}_{i}{ext}"

    # checksums optionnels
    if want_checksum:
        for it in items:
            try:
                print(f"   sha256 {it['filename']} ...", flush=True)
                it["checksum"] = sha256_of_url(it["url"])
            except Exception as e:
                print(f"   ! checksum echoue: {e}", flush=True)

    catalog = {"name": cfg.get("catalog_name", "Custom Payloads"), "payloads": items}

    with open("payloads.json", "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"\nOK : {len(items)} payload(s) ecrit(s) dans payloads.json", flush=True)
    if not items:
        print("ATTENTION : catalogue vide.", flush=True)


if __name__ == "__main__":
    main()
