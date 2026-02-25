"""
blob_api.py – Pure Python wrapper over the Vercel Blob REST API.
Tested against: https://blob.vercel-storage.com (API version 11)

Key insight: private stores require the header  `x-vercel-blob-access: private`
on all PUT upload requests (unlike older API versions that used an `access` body param).
"""
import os
import urllib.parse
import requests

BLOB_API_BASE = "https://blob.vercel-storage.com"
_DEFAULT_TOKEN = "vercel_blob_rw_AzoZdhQLpZEgI3Z3_TIc2K8OtH4qQPt8tCeK2sF6ZCshhDV"


def _token():
    return os.environ.get("BLOB_READ_WRITE_TOKEN", _DEFAULT_TOKEN)


def _base_headers():
    return {
        "Authorization": f"Bearer {_token()}",
        "x-api-version":  "11",
    }


# ── Upload ─────────────────────────────────────────────────────────────────────

def upload_blob(pathname, file_content, content_type="application/octet-stream"):
    """
    PUT file bytes to the private Vercel Blob store.
    Returns the blob metadata dict or None on failure.
    """
    params = urllib.parse.urlencode({"pathname": pathname})
    headers = {
        **_base_headers(),
        "x-vercel-blob-access": "private",   # key header for private stores
        "x-add-random-suffix":  "0",          # keep stable filename for overwriting
        "x-allow-overwrite":    "1",
        "x-content-type":       content_type,
    }
    try:
        r = requests.put(
            f"{BLOB_API_BASE}/?{params}",
            headers=headers,
            data=file_content,
            timeout=120,
        )
        r.raise_for_status()
        data = r.json()
        print(f"[Blob] Uploaded {pathname} → {data.get('pathname')}")
        return data
    except Exception as e:
        body = getattr(getattr(e, "response", None), "text", "")
        print(f"[Blob] Upload error for {pathname}: {e} | {body}")
        return None


# ── List ───────────────────────────────────────────────────────────────────────

def list_blobs():
    """Return list of blob metadata dicts from the store."""
    try:
        r = requests.get(BLOB_API_BASE, headers=_base_headers(), timeout=20)
        r.raise_for_status()
        return r.json().get("blobs", [])
    except Exception as e:
        print(f"[Blob] List error: {e}")
        return []


# ── Download ────────────────────────────────────────────────────────────────────

def fetch_blob(pathname, dest_path):
    """
    Download a private blob to dest_path using its signed downloadUrl.
    Returns dest_path on success, None on failure.
    """
    blobs = list_blobs()
    target = next((b for b in blobs if b.get("pathname") == pathname), None)
    if not target:
        print(f"[Blob] Not found in store: {pathname}")
        return None

    download_url = target.get("downloadUrl") or target.get("url")
    try:
        r = requests.get(
            download_url,
            headers={"Authorization": f"Bearer {_token()}"},
            timeout=120,
        )
        r.raise_for_status()
        os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(r.content)
        print(f"[Blob] Downloaded {pathname} → {dest_path}")
        return dest_path
    except Exception as e:
        print(f"[Blob] Download error for {pathname}: {e}")
        return None


# ── Delete ─────────────────────────────────────────────────────────────────────

def delete_blob_by_pathname(pathname):
    """Delete all blobs whose pathname matches."""
    blobs = list_blobs()
    targets = [b["url"] for b in blobs if b.get("pathname") == pathname]
    if not targets:
        return
    try:
        r = requests.post(
            f"{BLOB_API_BASE}/delete",
            headers={**_base_headers(), "content-type": "application/json"},
            json={"urls": targets},
            timeout=20,
        )
        r.raise_for_status()
        print(f"[Blob] Deleted {pathname}")
    except Exception as e:
        print(f"[Blob] Delete error: {e}")
