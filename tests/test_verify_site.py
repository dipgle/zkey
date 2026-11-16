# SPDX-License-Identifier: AGPL-3.0-or-later
import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from verify_site import compare


class VerifySiteTests(unittest.TestCase):
    def setUp(self):
        self.source = b'<!doctype html><title>zkey</title>'
        self.url = 'https://zkey.dipgle.com/'
        self.observation = dict(url=self.url, status=200, content_type='text/html; charset=utf-8',
                                size=len(self.source), sha256=hashlib.sha256(self.source).hexdigest())

    def test_real_bytes_match_and_changed_source_is_red_then_green(self):
        self.assertEqual(compare(self.observation, self.source, self.url)[0], 0)
        self.assertEqual(compare(self.observation, self.source.replace(b'zkey', b'fake'), self.url)[0], 1)
        self.assertEqual(compare(self.observation, self.source + b'\n', self.url)[0], 1)
        self.assertEqual(compare(self.observation, self.source, self.url)[0], 0)

    def test_incomplete_read_is_not_measurable_not_green(self):
        for value in (None, {}, {'pending': True}, {'error': 'offline'}):
            with self.subTest(value=value):
                self.assertEqual(compare(value, self.source, self.url)[0], 2)
        for field in self.observation:
            value = dict(self.observation)
            del value[field]
            with self.subTest(field=field):
                self.assertEqual(compare(value, self.source, self.url)[0], 2)
        for field in self.observation:
            with self.subTest(invalid_type=field):
                self.assertEqual(compare({**self.observation, field: None}, self.source, self.url)[0], 2)

    def test_http_error_redirect_non_html_or_tampered_digest_is_red(self):
        for field, value in (('status', 404), ('url', self.url + 'login'),
                             ('url', 'https://other.example/'), ('content_type', 'text/plain'),
                             ('sha256', '0' * 64), ('size', len(self.source) + 1)):
            with self.subTest(field=field, value=value):
                self.assertEqual(compare({**self.observation, field: value}, self.source, self.url)[0], 1)
