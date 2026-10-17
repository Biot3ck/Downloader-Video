import unittest
from clipora_v8_web.os_review import review,version


def inventory():
    return {'os':{'ID':'debian','VERSION_CODENAME':'trixie'},'packages':[
        {'binary':'libexample1:arm64','binary_version':'1:2.0-1+b2','source':'example',
         'source_version':'1:2.0-1','status':'installed'}]}


def tracker(**state):return {'example':{'CVE-TEST':{'releases':{'trixie':state}}}}


class OSReviewTests(unittest.TestCase):
    def test_compares_source_version_not_binary_rebuild_and_never_approves(self):
        calls=[]
        def compare(a,b):calls.append((a,b));return False
        result=review(inventory(),tracker(status='resolved',fixed_version='1:2.0-2'),compare)
        self.assertEqual(calls,[('1:2.0-1','1:2.0-2')])
        self.assertEqual(result['counts'],{'upgrade_required':1})
        self.assertFalse(result['production_security_approved']);self.assertFalse(result['public_downloads_enabled'])

    def test_patched_and_not_affected_records_do_not_become_upgrade_findings(self):
        result=review(inventory(),tracker(status='resolved',fixed_version='1:2.0-1'),lambda *_:True)
        self.assertEqual(result['findings'],[])
        def forbidden(*_):raise AssertionError('Marker must not be compared as a version')
        result=review(inventory(),tracker(status='resolved',fixed_version='0'),forbidden)
        self.assertEqual(result['counts'],{'not_affected_marker':1})

    def test_no_dsa_is_not_a_clean_bill_and_unimportant_is_explicit(self):
        result=review(inventory(),tracker(status='open',urgency='not yet assigned',nodsa='Minor issue'))
        self.assertEqual(result['counts'],{'open_review_required':1})
        result=review(inventory(),tracker(status='open',urgency='unimportant'))
        self.assertEqual(result['counts'],{'debian_unimportant':1})
        self.assertFalse(result['triage_complete'])

    def test_unknown_status_or_missing_fixed_version_stays_undetermined(self):
        for state in ({'status':'undetermined'},{'status':'resolved'},
                      {'status':'unexpected','urgency':'unimportant'}):
            self.assertEqual(review(inventory(),tracker(**state))['counts'],{'undetermined':1})

    def test_missing_source_and_release_are_visible_coverage_gaps(self):
        result=review(inventory(),{'different':{}})
        self.assertEqual(result['sources_without_tracker_record'],['example'])
        result=review(inventory(),{'example':{'CVE-TEST':{'releases':{'bookworm':{'status':'open'}}}}})
        self.assertEqual(result['sources_without_release_record'],['example'])
        self.assertFalse(result['production_security_approved'])

    def test_malformed_inventory_or_tracker_fails_instead_of_reporting_zero(self):
        for data in ({},[],{'os':{'ID':'ubuntu'},'packages':[]}):
            with self.assertRaises(ValueError):review(data,tracker(status='open'))
        with self.assertRaises(ValueError):review(inventory(),{})
        with self.assertRaises(ValueError):review(inventory(),{'example':{'CVE-TEST':{}}})
        for value in ('--help','1;touch /tmp/x','1\n2',None,'x'*300):
            with self.assertRaises(ValueError):version(value)


if __name__=='__main__':unittest.main()
