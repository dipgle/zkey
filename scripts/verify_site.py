# SPDX-License-Identifier: AGPL-3.0-or-later
"""Compare source bytes fetched INSIDE the public page, not serialized DOM.

Exit 0 matches, 1 differs/HTTP failure, 2 measurement unavailable.
"""
import hashlib
from urllib.parse import urlsplit


BROWSER_READ = r"""(() => {
  window.__zkeySiteBytes = {pending: true};
  (async () => {
    try {
      const response = await fetch('/', {cache: 'no-store', credentials: 'omit'});
      const bytes = await response.arrayBuffer();
      const digest = await crypto.subtle.digest('SHA-256', bytes);
      window.__zkeySiteBytes = {
        url: response.url, status: response.status,
        content_type: response.headers.get('content-type'),
        size: bytes.byteLength,
        sha256: Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, '0')).join('')
      };
    } catch (error) {
      window.__zkeySiteBytes = {error: String(error)};
    }
  })();
  return 'started';
})()"""


def compare(result, expected, url):
    """Reject incomplete observations, redirects and non-HTML error documents."""
    if not isinstance(result, dict) or result.get('pending') or result.get('error'):
        return 2, 'browser byte read incomplete or unavailable'
    if not {'url', 'status', 'content_type', 'size', 'sha256'} <= result.keys():
        return 2, 'browser byte read lacks required fields'
    if (not isinstance(result['url'], str) or not isinstance(result['content_type'], str)
            or not isinstance(result['sha256'], str)
            or type(result['status']) is not int or type(result['size']) is not int):
        return 2, 'browser byte read has invalid field types'
    target, observed = urlsplit(url), urlsplit(result['url'])
    if (observed.scheme, observed.netloc, observed.path, observed.query) != (
        target.scheme, target.netloc, target.path or '/', target.query
    ):
        return 1, 'response URL differs from requested public page'
    if result['status'] != 200:
        return 1, f"HTTP status {result['status']}"
    if not (result['content_type'] or '').lower().startswith('text/html'):
        return 1, 'response is not HTML'
    if result['size'] != len(expected) or result['sha256'] != hashlib.sha256(expected).hexdigest():
        return 1, 'source byte length or SHA-256 differs'
    return 0, 'source byte length and SHA-256 match'
