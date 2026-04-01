#!/usr/bin/env python3
"""
check_versions.py — Check for available upgrades across the homelab stack.

Compares pinned versions in k8s-home-lab (ArgoCD apps, Helm values) and
truenas-home-lab (docker-compose images) against upstream registries.

Usage:
    python check_versions.py                    # check all, text output
    python check_versions.py --format markdown  # markdown table
    python check_versions.py --format json      # JSON for programmatic use
    python check_versions.py --type helm        # only Helm charts
    python check_versions.py --type docker      # only Docker images

Exit codes:
    0 — all up to date
    1 — upgrades available
    2 — error (network, parse, etc.)

Environment:
    GITEA_TOKEN  — (optional) Gitea API token for creating upgrade PRs
    GITHUB_TOKEN — (optional) GitHub token for higher rate limits on release API
"""

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yaml

# ── Paths ────────────────────────────────────────────────────────────────────
WORKSPACE = Path(__file__).parent.parent.parent
K8S_REPO = WORKSPACE / "k8s-home-lab"
TRUENAS_REPO = WORKSPACE / "truenas-home-lab"

# ── Helm charts managed by ArgoCD ────────────────────────────────────────────
# Parsed from k8s-home-lab/cluster/gitops/apps/*.yaml at runtime.
# Fallback static list if ArgoCD manifests aren't found.
HELM_CHARTS_FALLBACK = [
    {"name": "cilium", "repo": "https://helm.cilium.io", "chart": "cilium", "current": "1.19.0"},
    {"name": "longhorn", "repo": "https://charts.longhorn.io", "chart": "longhorn", "current": "1.7.3"},
    {"name": "cert-manager", "repo": "https://charts.jetstack.io", "chart": "cert-manager", "current": "v1.19.4"},
    {"name": "external-secrets", "repo": "https://charts.external-secrets.io", "chart": "external-secrets", "current": "0.14.4"},
    {"name": "vault", "repo": "https://helm.releases.hashicorp.com", "chart": "vault", "current": "0.29.1"},
    {"name": "semaphore", "repo": "https://semaphoreui.github.io/charts", "chart": "semaphore", "current": "16.0.11"},
    {"name": "mongodb", "repo": "oci://registry-1.docker.io/bitnamicharts", "chart": "mongodb", "current": "18.4.4"},
    {"name": "redis", "repo": "oci://registry-1.docker.io/bitnamicharts", "chart": "redis", "current": "24.1.3"},
]

# ── Docker images with pinned versions (not :latest) ────────────────────────
# Parsed from docker-compose.yml at runtime.
# Images tagged :latest or :release are skipped (auto-pull).


def _http_get_json(url: str, timeout: int = 15, token: str | None = None) -> dict:
    """GET JSON from a URL with optional auth."""
    req = Request(url)
    req.add_header("Accept", "application/json")
    if token:
        req.add_header("Authorization", f"token {token}")
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


# ── Helm repo version check ─────────────────────────────────────────────────

def parse_argocd_apps() -> list[dict]:
    """Parse ArgoCD Application manifests to extract chart versions."""
    apps_dir = K8S_REPO / "cluster" / "gitops" / "apps"
    if not apps_dir.exists():
        return HELM_CHARTS_FALLBACK

    charts = []
    for f in sorted(apps_dir.glob("*.yaml")):
        with open(f) as fh:
            docs = list(yaml.safe_load_all(fh))
        for doc in docs:
            if not doc or doc.get("kind") != "Application":
                continue
            spec = doc.get("spec", {})
            sources = spec.get("sources", [])
            # Also handle single-source apps
            if not sources and "source" in spec:
                sources = [spec["source"]]
            for src in sources:
                chart = src.get("chart")
                version = src.get("targetRevision")
                repo_url = src.get("repoURL", "")
                if chart and version and not repo_url.endswith(".git"):
                    charts.append({
                        "name": doc["metadata"]["name"],
                        "repo": repo_url,
                        "chart": chart,
                        "current": version,
                        "file": str(f.relative_to(WORKSPACE)),
                    })
    return charts if charts else HELM_CHARTS_FALLBACK


def check_helm_repo_latest(repo_url: str, chart_name: str) -> str | None:
    """Query a Helm repo index.yaml for the latest chart version."""
    if repo_url.startswith("oci://") or "docker.io" in repo_url:
        return _check_oci_chart(repo_url, chart_name)

    index_url = repo_url.rstrip("/") + "/index.yaml"
    try:
        req = Request(index_url)
        req.add_header("Accept", "application/x-yaml, text/yaml, */*")
        with urlopen(req, timeout=20) as resp:
            data = yaml.safe_load(resp.read())
    except (URLError, HTTPError, yaml.YAMLError):
        return None

    entries = data.get("entries", {}).get(chart_name, [])
    if not entries:
        return None

    # Filter out pre-release / RC versions
    stable = [e for e in entries if not _is_prerelease(e.get("version", ""))]
    if not stable:
        stable = entries

    # Sort by version (entries are usually sorted, but be safe)
    stable.sort(key=lambda e: _version_tuple(e.get("version", "0")), reverse=True)
    return stable[0].get("version")


def _check_oci_chart(repo_url: str, chart_name: str) -> str | None:
    """Check OCI registry for latest chart version via Docker Registry API v2."""
    # Normalize: oci://registry-1.docker.io/bitnamicharts or registry-1.docker.io/bitnamicharts
    clean_url = repo_url.replace("oci://", "").replace("https://", "").replace("http://", "")
    if "docker.io" in clean_url:
        namespace = clean_url.split("/", 1)[-1] if "/" in clean_url else ""
        return _check_dockerhub_chart(chart_name, namespace or "bitnamicharts")
    url = f"https://{clean_url}/{chart_name}/tags/list"
    try:
        data = _http_get_json(url)
        tags = data.get("tags", [])
        versions = [t for t in tags if re.match(r"^\d+\.\d+\.\d+$", t)]
        if not versions:
            return None
        versions.sort(key=_version_tuple, reverse=True)
        return versions[0]
    except (URLError, HTTPError):
        return None


def _check_dockerhub_chart(chart_name: str, namespace: str) -> str | None:
    """Check Docker Hub for Bitnami chart tags."""
    try:
        token_data = _http_get_json(
            f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:{namespace}/{chart_name}:pull"
        )
        token = token_data.get("token", "")
        req = Request(f"https://registry-1.docker.io/v2/{namespace}/{chart_name}/tags/list")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Accept", "application/json")
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        tags = data.get("tags", [])
        versions = [t for t in tags if re.match(r"^\d+\.\d+\.\d+$", t)]
        if not versions:
            return None
        versions.sort(key=_version_tuple, reverse=True)
        return versions[0]
    except (URLError, HTTPError):
        return None


# ── Docker image version check ───────────────────────────────────────────────

def parse_docker_compose_images() -> list[dict]:
    """Parse all docker-compose.yml for pinned image versions."""
    apps_dir = TRUENAS_REPO / "apps"
    if not apps_dir.exists():
        return []

    images = []
    for compose in sorted(apps_dir.glob("*/docker-compose.yml")):
        app_name = compose.parent.name
        with open(compose) as fh:
            try:
                data = yaml.safe_load(fh)
            except yaml.YAMLError:
                continue
        for svc_name, svc in (data.get("services") or {}).items():
            image = svc.get("image", "")
            if not image or ":" not in image:
                continue
            img_ref, tag = image.rsplit(":", 1)
            # Skip :latest and :release — these auto-update
            if tag in ("latest", "release"):
                continue
            images.append({
                "app": app_name,
                "service": svc_name,
                "image": img_ref,
                "current_tag": tag,
                "file": str(compose.relative_to(WORKSPACE)),
            })

    # Also check K8s manifests for direct image pins
    for manifest in sorted(K8S_REPO.rglob("*.yaml")):
        try:
            with open(manifest) as fh:
                docs = list(yaml.safe_load_all(fh))
        except (yaml.YAMLError, UnicodeDecodeError):
            continue
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            _extract_k8s_images(doc, manifest, images)

    return images


def _extract_k8s_images(doc: dict, manifest: Path, images: list):
    """Recursively find container image refs in K8s manifests."""
    kind = doc.get("kind", "")
    if kind in ("Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob"):
        spec = doc.get("spec", {})
        # CronJob nests deeper
        if kind == "CronJob":
            spec = spec.get("jobTemplate", {}).get("spec", {})
        pod_spec = spec.get("template", {}).get("spec", {})
        for container in pod_spec.get("containers", []) + pod_spec.get("initContainers", []):
            image = container.get("image", "")
            if not image or ":" not in image:
                continue
            img_ref, tag = image.rsplit(":", 1)
            if tag in ("latest", "release"):
                continue
            # Skip base images like python:3.x-slim
            if img_ref in ("python", "node", "golang", "alpine", "ubuntu", "debian"):
                continue
            images.append({
                "app": doc.get("metadata", {}).get("name", "unknown"),
                "service": container.get("name", "main"),
                "image": img_ref,
                "current_tag": tag,
                "file": str(manifest.relative_to(WORKSPACE)),
            })


def check_docker_latest(image: str, current_tag: str) -> str | None:
    """Check Docker Hub or GHCR for the latest stable tag."""
    if image.startswith("ghcr.io/"):
        return _check_ghcr_latest(image, current_tag)
    return _check_dockerhub_latest(image, current_tag)


def _check_dockerhub_latest(image: str, current_tag: str) -> str | None:
    """Check Docker Hub for the latest tag matching the current pinning pattern."""
    # Normalize: library images vs namespaced
    if "/" not in image:
        namespace = "library"
        repo = image
    else:
        parts = image.split("/", 1)
        # Handle registry prefix
        if "." in parts[0]:
            # e.g., registry.hub.docker.com/tensorchord/pgvecto-rs
            image = parts[1]
            if "/" not in image:
                namespace = "library"
                repo = image
            else:
                namespace, repo = image.split("/", 1)
        else:
            namespace, repo = parts

    try:
        token_data = _http_get_json(
            f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:{namespace}/{repo}:pull"
        )
        token = token_data.get("token", "")
        req = Request(f"https://registry-1.docker.io/v2/{namespace}/{repo}/tags/list")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Accept", "application/json")
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        tags = data.get("tags", [])
        return _find_best_upgrade(tags, current_tag)
    except (URLError, HTTPError):
        return None


def _check_ghcr_latest(image: str, current_tag: str) -> str | None:
    """Check GHCR for the latest tag."""
    # ghcr.io/org/repo → token scope
    path = image.replace("ghcr.io/", "")
    try:
        token_data = _http_get_json(
            f"https://ghcr.io/token?service=ghcr.io&scope=repository:{path}:pull"
        )
        token = token_data.get("token", "")
        req = Request(f"https://ghcr.io/v2/{path}/tags/list")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Accept", "application/json")
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        tags = data.get("tags", [])
        return _find_best_upgrade(tags, current_tag)
    except (URLError, HTTPError):
        return None


def _find_best_upgrade(tags: list[str], current_tag: str) -> str | None:
    """Find the best upgrade tag matching the current pinning pattern."""
    # Determine pinning pattern from current tag
    # E.g., "4.39.16" → semver, "v3.6" → minor pin, "15-alpine" → major+suffix
    current_clean = re.sub(r"^v", "", current_tag)

    # Full semver pin (e.g., 4.39.16, v1.13.2)
    if re.match(r"^\d+\.\d+\.\d+", current_clean):
        prefix = "v" if current_tag.startswith("v") else ""
        # Extract suffix like "-alpine"
        suffix_match = re.search(r"(-[a-zA-Z][\w-]*)$", current_tag.lstrip("v"))
        suffix = suffix_match.group(1) if suffix_match else ""

        pattern = re.compile(r"^" + re.escape(prefix) + r"\d+\.\d+\.\d+" + re.escape(suffix) + r"$")
        candidates = [t for t in tags if pattern.match(t) and not _is_prerelease(t)]
        if not candidates:
            return None
        candidates.sort(key=lambda t: _version_tuple(t.lstrip("v").split("-")[0]), reverse=True)
        latest = candidates[0]
        if _version_tuple(latest.lstrip("v").split("-")[0]) > _version_tuple(current_clean.split("-")[0]):
            return latest
        return None

    # Minor pin (e.g., "v3.6", "24.1")
    if re.match(r"^v?\d+\.\d+$", current_tag):
        prefix = "v" if current_tag.startswith("v") else ""
        major = current_clean.split(".")[0]
        pattern = re.compile(r"^" + re.escape(prefix) + re.escape(major) + r"\.\d+$")
        candidates = [t for t in tags if pattern.match(t)]
        if not candidates:
            return None
        candidates.sort(key=lambda t: _version_tuple(t.lstrip("v")), reverse=True)
        latest = candidates[0]
        if _version_tuple(latest.lstrip("v")) > _version_tuple(current_clean):
            return latest
        return None

    # Major pin with suffix (e.g., "15-alpine", "6.2-alpine")
    match = re.match(r"^(\d+(?:\.\d+)?)(-.+)$", current_tag)
    if match:
        ver_part, suffix = match.groups()
        pattern = re.compile(r"^\d+(?:\.\d+)?" + re.escape(suffix) + r"$")
        candidates = [t for t in tags if pattern.match(t)]
        if not candidates:
            return None
        candidates.sort(key=lambda t: _version_tuple(t.replace(suffix, "")), reverse=True)
        latest = candidates[0]
        if _version_tuple(latest.replace(suffix, "")) > _version_tuple(ver_part):
            return latest
        return None

    return None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _version_tuple(v: str) -> tuple:
    """Convert version string to comparable tuple."""
    v = re.sub(r"^v", "", v)
    parts = re.split(r"[.\-]", v)
    result = []
    for p in parts:
        try:
            result.append(int(p))
        except ValueError:
            result.append(p)
    return tuple(result)


def _is_prerelease(version: str) -> bool:
    """Check if version looks like a pre-release."""
    v = version.lower()
    return any(tag in v for tag in ("alpha", "beta", "rc", "dev", "snapshot", "nightly", "pre"))


# ── Main ─────────────────────────────────────────────────────────────────────

def check_all(types: list[str] | None = None) -> list[dict]:
    """Run all version checks. Returns list of upgrade records."""
    results = []
    types = types or ["helm", "docker"]

    if "helm" in types:
        charts = parse_argocd_apps()
        for chart in charts:
            latest = check_helm_repo_latest(chart["repo"], chart["chart"])
            current = chart["current"].lstrip("v")
            record = {
                "type": "helm",
                "name": chart["name"],
                "current": chart["current"],
                "latest": latest,
                "file": chart.get("file", ""),
                "repo": chart["repo"],
                "upgrade_available": False,
            }
            # Skip wildcard versions (e.g., "3.*") — can't compare
            if "*" in current:
                record["latest"] = None
                results.append(record)
                continue
            if latest and _version_tuple(latest.lstrip("v")) > _version_tuple(current):
                record["upgrade_available"] = True
            results.append(record)

    if "docker" in types:
        images = parse_docker_compose_images()
        # Deduplicate by image+tag (same image may appear in multiple compose files)
        seen = set()
        for img in images:
            key = f"{img['image']}:{img['current_tag']}"
            if key in seen:
                continue
            seen.add(key)
            latest = check_docker_latest(img["image"], img["current_tag"])
            record = {
                "type": "docker",
                "name": f"{img['app']}/{img['service']}",
                "current": img["current_tag"],
                "latest": latest,
                "image": img["image"],
                "file": img.get("file", ""),
                "upgrade_available": latest is not None,
            }
            results.append(record)

    return results


def format_text(results: list[dict]) -> str:
    """Format results as human-readable text."""
    lines = []
    upgrades = [r for r in results if r["upgrade_available"]]
    up_to_date = [r for r in results if not r["upgrade_available"]]

    if upgrades:
        lines.append(f"🔄 {len(upgrades)} upgrade(s) available:\n")
        for r in upgrades:
            if r["type"] == "helm":
                lines.append(f"  HELM  {r['name']}: {r['current']} → {r['latest']}  ({r['file']})")
            else:
                lines.append(f"  IMAGE {r['name']}: {r['current']} → {r['latest']}  ({r['image']})")
        lines.append("")

    lines.append(f"✅ {len(up_to_date)} component(s) up to date")
    errors = [r for r in results if r.get("latest") is None and not r["upgrade_available"]]
    if errors:
        lines.append(f"⚠️  {len(errors)} component(s) could not be checked (network/registry error)")

    return "\n".join(lines)


def format_markdown(results: list[dict]) -> str:
    """Format results as a Markdown table."""
    lines = [
        "| Type | Component | Current | Latest | Status | File |",
        "|------|-----------|---------|--------|--------|------|",
    ]
    for r in sorted(results, key=lambda x: (not x["upgrade_available"], x["type"], x["name"])):
        status = "⬆️ Upgrade" if r["upgrade_available"] else ("✅ Current" if r.get("latest") else "❓ Unknown")
        latest = r.get("latest") or "—"
        lines.append(f"| {r['type']} | {r['name']} | {r['current']} | {latest} | {status} | {r.get('file', '')} |")
    return "\n".join(lines)


def format_json(results: list[dict]) -> str:
    """Format results as JSON."""
    return json.dumps(results, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Check for available upgrades across the homelab stack")
    parser.add_argument("--format", choices=["text", "markdown", "json"], default="text")
    parser.add_argument("--type", choices=["helm", "docker", "all"], default="all",
                        help="Which component types to check")
    args = parser.parse_args()

    types = ["helm", "docker"] if args.type == "all" else [args.type]

    try:
        results = check_all(types)
    except Exception as e:
        print(f"ERROR: Version check failed: {e}", file=sys.stderr)
        sys.exit(2)

    formatter = {"text": format_text, "markdown": format_markdown, "json": format_json}
    print(formatter[args.format](results))

    has_upgrades = any(r["upgrade_available"] for r in results)
    sys.exit(1 if has_upgrades else 0)


if __name__ == "__main__":
    main()
