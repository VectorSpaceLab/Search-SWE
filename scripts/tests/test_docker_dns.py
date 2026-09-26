import unittest

from scripts.docker_dns import parse_servers


class DockerDNSTests(unittest.TestCase):
    def test_servers(self):
        self.assertEqual(parse_servers('198.18.254.30, 198.18.254.31,198.18.254.30'),
                         ['198.18.254.30', '198.18.254.31'])

    def test_reject_invalid_servers(self):
        for value in ('', '127.0.0.53', '::1', '1.1.1.1;echo bad', 'example.org', '0.0.0.0', '224.0.0.1'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_servers(value)
