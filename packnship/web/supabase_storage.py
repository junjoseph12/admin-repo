# web/supabase_storage.py
# Creates short-lived signed links for files in PRIVATE Supabase Storage buckets.
# The service role key is read from .env and is never sent to the browser.
import json
import os
import re
from urllib import error, parse, request as urlrequest


class StorageError(Exception):
    pass


# Matches .../storage/v1/object/public|sign|authenticated/<bucket>/<path>
_STORAGE_URL_RE = re.compile(
    r'/storage/v1/object/(?:public|sign|authenticated)/([^/]+)/(.+?)(?:\?.*)?$'
)


def parse_storage_ref(value, default_bucket=None):
    """Return (bucket, path) from a stored full URL or a plain path."""
    value = (value or '').strip()
    if not value:
        raise StorageError('No file stored.')

    match = _STORAGE_URL_RE.search(value)
    if match:
        return match.group(1), parse.unquote(match.group(2))

    if value.lower().startswith(('http://', 'https://')):
        raise StorageError('Stored value is not a Supabase Storage URL.')

    if not default_bucket:
        raise StorageError('Stored value is a plain path but no bucket name is configured.')
    return default_bucket, value.lstrip('/')


def create_signed_url(bucket, path, expires_in=120):
    base = os.environ.get('SUPABASE_URL', '').rstrip('/')
    key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '')
    if not base or not key:
        raise StorageError('SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is missing in .env.')

    endpoint = f"{base}/storage/v1/object/sign/{bucket}/{parse.quote(path)}"

    # Legacy service_role keys are JWTs (start with 'eyJ') and go in both headers.
    # New sb_secret_... keys are not JWTs, so they go in the apikey header only.
    headers = {'apikey': key, 'Content-Type': 'application/json'}
    if key.startswith('eyJ'):
        headers['Authorization'] = f'Bearer {key}'
    req = urlrequest.Request(
        endpoint,
        data=json.dumps({'expiresIn': expires_in}).encode('utf-8'),
        headers=headers,
        method='POST',
    )
    try:
        with urlrequest.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except error.HTTPError as e:
        raise StorageError(f'Supabase returned {e.code} (file missing or wrong bucket?).')
    except Exception as e:
        raise StorageError(f'Could not reach Supabase Storage: {e}')

    signed = data.get('signedURL') or data.get('signedUrl')
    if not signed:
        raise StorageError('Supabase did not return a signed link.')
    if signed.startswith('/storage/v1'):
        return f'{base}{signed}'
    return f'{base}/storage/v1{signed}'