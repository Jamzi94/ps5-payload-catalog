#!/usr/bin/env python3
"""
Genere payloads.json a partir des releases GitHub listees dans repos.json.
Aucune dependance externe : stdlib uniquement.

Options par repo (repos.json) :
  owner, repo            (requis)
  label                  nom affiche (defaut: repo)
  keep                   nb de releases recentes a garder (defaut: 1).
                         keep > 1 inclut aussi les test/pre-releases.

Options globales :
  catalog_name           nom du catalogue
  asset_extensions       extensions considerees comme payloads
  compute_checksum       true -> calcule le SHA-256 de chaque asset

Env : GITHUB_TOKEN (recommande, augmente le rate limit).
"""

import json
import os
import re
import hashlib
import urllib.request
import urllib.error
from collections import defaultdict

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
    return re.sub(r"[^A-Za-z0-9._-]+", "-", s).strip("-")


def releases_for(entry):
    """Retourne la liste des releases a traiter pour un repo (plus recent d'abord)."""
    owner, repo = entry["owner"], entry["repo"]
    keep = int(entry.get("keep", 1))

    if keep <= 1:
        # comportement historique : la 'latest' (ignore les pre-releases)
        return [http_get_json(LATEST.format(owner=owner, repo=repo))]

    # keep > 1 : on prend les N plus recentes (test/pre-releases inclus, drafts exclus)
    rels = http_get_json(LIST.format(owner=owner, repo=repo))
    rels = [r for r in rels if not r.get("draft", False)]
    return rels[:keep]


def assets_from(release, exts):
    version = release.get("tag_name") or release.get("name") or ""
    is_pre = bool(release.get("prerelease", False))
    matched = [a for a in release.get("assets", []) if a["name"].lower().endswith(exts)]
    return version, is_pre, matched


def main():
    cfg = json.load(open("repos.json", encoding="utf-8"))
    exts = tuple(e.lower() for e in cfg.get("asset_extensions", [".elf", ".bin"]))
    want_checksum = bool(cfg.get("compute_checksum", False))

    items = []  # entrees brutes avec metadonnees internes (_repo, _version)

    for entry in cfg["repos"]:
        owner, repo = entry["owner"], entry["repo"]
        label = entry.get("label", repo)
        print(f"-> {owner}/{repo}", flush=True)

        try:
            releases = releases_for(entry)
        except urllib.error.HTTPError as e:
            print(f"   ! {e.code} {e.reason} - ignore", flush=True)
            continue
        except Exception as e:
            print(f"   ! erreur reseau: {e} - ignore", flush=True)
            continue

        for rel in releases:
            version, is_pre, matched = assets_from(rel, exts)
            if not matched:
                print(f"   . {version} : aucun asset {exts} - saute", flush=True)
                continue
            tag = f" (pre-release)" if is_pre else ""
            for a in matched:
                items.append({
                    "name": f"{label} {version}{tag}".strip(),
                    "filename": a["name"],
                    "url": a["browser_download_url"],
                    "description": f"{label} - source: github.com/{owner}/{repo}",
                    "version": version,
                    "_repo": repo,
                    "_version": version,
                })
                print(f"   + {a['name']}  [{version}]{tag}", flush=True)

    # --- dedup des filenames (eviter les ecrasements sur le PS5) ---
    # passe 1 : meme filename sur des repos differents -> prefixe le repo
    groups = defaultdict(list)
    for it in items:
        groups[it["filename"]].append(it)
    for fn, grp in groups.items():
        if len(grp) > 1 and len({it["_repo"] for it in grp}) > 1:
            for it in grp:
                it["filename"] = f"{sanitize(it['_repo'])}_{it['filename']}"

    # passe 2 : meme filename restant (meme repo, versions differentes) -> insere la version
    groups = defaultdict(list)
    for it in items:
        groups[it["filename"]].append(it)
    for fn, grp in groups.items():
        if len(grp) > 1:
            root, ext = os.path.splitext(fn)
            for it in grp:
                it["filename"] = f"{root}_{sanitize(it['_version'])}{ext}"

    # passe 3 : securite, si jamais il reste un doublon -> suffixe numerique
    groups = defaultdict(list)
    for it in items:
        groups[it["filename"]].append(it)
    for fn, grp in groups.items():
        if len(grp) > 1:
            root, ext = os.path.splitext(fn)
            for i, it in enumerate(grp[1:], start=2):
                it["filename"] = f"{root}_{i}{ext}"

    # checksums (optionnel) + nettoyage des champs internes
    payloads = []
    for it in items:
        if want_checksum:
            try:
                print(f"   sha256 {it['filename']} ...", flush=True)
                it["checksum"] = sha256_of_url(it["url"])
            except Exception as e:
                print(f"   ! checksum echoue: {e}", flush=True)
        payloads.append({
            "name": it["name"],
            "filename": it["filename"],
            "url": it["url"],
            "description": it["description"],
            "version": it["version"],
            **({"checksum": it["checksum"]} if "checksum" in it else {}),
        })

    # "name" DOIT apparaitre avant "payloads" (exigence du parser)
    catalog = {"name": cfg.get("catalog_name", "Custom Payloads"), "payloads": payloads}

    with open("payloads.json", "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"\nOK : {len(payloads)} payload(s) ecrit(s) dans payloads.json", flush=True)
    if not payloads:
        print("ATTENTION : catalogue vide.", flush=True)


if __name__ == "__main__":
    main()
