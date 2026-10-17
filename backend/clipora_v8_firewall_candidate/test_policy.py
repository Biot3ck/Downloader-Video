import unittest
from clipora_v8_firewall_candidate.policy import rules, validate


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.config = {'mode': 'offline-fixture', 'network': '10.94.8.0/24',
                       'gateway_ip': '10.94.8.2', 'destination_ip': '10.94.8.3',
                       'destination_port': 8443, 'uid': 65534, 'gid': 65534}

    def test_topology_not_tied_to_old_subnet(self):
        for network, gateway, destination in [('10.94.8.0/24', '10.94.8.2', '10.94.8.3'),
                                              ('192.168.73.0/24', '192.168.73.2', '192.168.73.3')]:
            p = {**self.config, 'network': network, 'gateway_ip': gateway, 'destination_ip': destination}
            ipv4, ipv6 = rules(p)
            self.assertIn(f'-d {destination}/32 -p tcp --dport 8443', ipv4)
            self.assertIn(f'-s {gateway}/32 -p tcp --dport 8888', ipv4)
            self.assertNotIn('ACCEPT', ipv6)

    def test_invalid_configuration_rejected(self):
        cases = [('mode', 'public'), ('network', '8.8.8.0/24'), ('network', '10.0.0.0/8'),
                 ('network', '10.94.8.1/24'), ('gateway_ip', '10.94.9.2'),
                 ('destination_ip', '169.254.169.254'), ('destination_ip', '127.0.0.1'),
                 ('destination_ip', '::1'), ('destination_ip', '10.94.8.2'),
                 ('destination_ip', '10.94.8.0'), ('destination_ip', '10.94.8.255'),
                 ('destination_ip', '10.094.8.3'), ('destination_ip', '10.94.8.3\n-A OUTPUT -j ACCEPT'),
                 ('destination_port', True), ('destination_port', '8443'), ('destination_port', 0),
                 ('uid', 0), ('gid', -1), ('uid', True)]
        for key, value in cases:
            with self.subTest(key=key, value=value), self.assertRaises((ValueError, TypeError)):
                validate({**self.config, key: value})
        for bad in ({}, {**self.config, 'unknown': 1}, None):
            with self.assertRaises(ValueError): validate(bad)


if __name__ == '__main__': unittest.main()
