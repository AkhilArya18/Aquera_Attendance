"""
blob_api.py – Wrapper over the Vercel Blob REST API.
The token encodes both the store ID (azozdhqlpzegi3z3) and the access scope (rw).
Private stores use `https://<storeId>.private.blob.vercel-storage.com` for uploads.
"""
import os
import requests

BLOB_API_BASE   = "https://blob.vercel-storage.com"   # list / delete 
PRIVATE_STORE   = "https://azozdhqlpzegi3z3.private.blob.vercel-storage.com"  # upload / download

_DEFAULT_TOKEN = "vercel_blob_rw_AzoZdhQLpZEgI3Z3_TIc2K8OtH4qQPt8tCeK2sF6ZCshhDV"

def _token():
    return os.environ.get("BLOB_READ_WRITE_TOKEN", _DEFAULT_TOKEN)


import subprocess
import tempfile
import json as _json
import sys

# Node helper script (must be present alongside this file)
_NODE_HELPER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blob_upload.js")
# @vercel/blob npm package — bundled locally
_NODE_MODULES = "/tmp/blobtest/node_modules/@vercel/blob"


def _ensure_node_modules():
    """Install @vercel/blob into /tmp/blobtest if not already there."""
    import shutil
    if not os.path.exists(_NODE_MODULES):
        subprocess.run(
            ["npm", "install", "--prefix", "/tmp/blobtest", "@vercel/blob"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True
        )


def upload_blob(pathname, file_content, content_type="application/octet-stream"):
    """
    Upload file bytes to Vercel Blob via the official Node.js SDK (shell out).
    Returns blob metadata dict or None on failure.
    """
    tok = _token()
    _ensure_node_modules()

    # Write to a temp file then pass path to the Node script
    suffix = "." + pathname.rsplit(".", 1)[-1] if "." in pathname else ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name

        result = subprocess.run(
            ["node", _NODE_HELPER, pathname, tmp_path, tok],
            capture_output=True, text=True, timeout=120
        )
        os.unlink(tmp_path)

        stdout = result.stdout.strip()
        if stdout:
            data = _json.loads(stdout)
            if "error" in data:
                print(f"[Blob] Upload error: {data['error']}")
                return None
            print(f"[Blob] Uploaded {pathname} → {data.get('pathname')}")
            return data
        else:
            print(f"[Blob] Upload no output. stderr: {result.stderr[:200]}")
            return None
    except Exception as e:
        print(f"[Blob] Upload exception: {e}")
        return None


def list_blobs():
    """Return list of blob metadata dicts from the store."""
    tok = _token()
    headers = {"Authorization": f"Bearer {tok}", "x-api-version": "11"}
    try:
        r = requests.get(BLOB_API_BASE, headers=headers, timeout=20)
        r.raise_for_status()
        return r.json().get("blobs", [])
    except Exception as e:
        print(f"[Blob] List error: {e}")
        return []


def fetch_blob(pathname, dest_path):
    """
    Download a private blob to dest_path using the signed downloadUrl.
    Returns dest_path on success, None on failure.
    """
    blobs = list_blobs()
    target = next((b for b in blobs if b.get("pathname") == pathname), None)
    if not target:
        print(f"[Blob] Not found in store: {pathname}")
        return None

    download_url = target.get("downloadUrl") or target.get("url")
    tok = _token()
    try:
        r = requests.get(download_url, headers={"Authorization": f"Bearer {tok}"}, timeout=120)
        r.raise_for_status()
        os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(r.content)
        print(f"[Blob] Downloaded {pathname} → {dest_path}")
        return dest_path
    except Exception as e:
        print(f"[Blob] Download error for {pathname}: {e}")
        return None


def delete_blob_by_pathname(pathname):
    """Delete all blobs whose pathname matches."""
    blobs = list_blobs()
    targets = [b["url"] for b in blobs if b.get("pathname") == pathname]
    if not targets:
        return
    tok = _token()
    try:
        r = requests.post(
            f"{BLOB_API_BASE}/delete",
            headers={"Authorization": f"Bearer {tok}", "x-api-version": "11", "content-type": "application/json"},
            json={"urls": targets},
            timeout=20,
        )
        r.raise_for_status()
        print(f"[Blob] Deleted {pathname} ({targets})")
    except Exception as e:
        print(f"[Blob] Delete error: {e}")
