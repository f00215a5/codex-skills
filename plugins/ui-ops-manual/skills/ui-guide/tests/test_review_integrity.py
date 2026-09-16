"""Reject plausible but incomplete or stale independent-review records."""
import copy
import json
import unittest

import test_audit_delivery as fixtures
from test_audit_delivery import _table, _write_docx, _sha256, audit_delivery


class ReviewIntegrityTests(unittest.TestCase):
    setUp = fixtures.AuditDeliveryTests.setUp
    tearDown = fixtures.AuditDeliveryTests.tearDown

    def fixture(self):
        docx = _write_docx(self.root, 'manual.docx', _table([1000], [[(1, 1000)]]),
                           media=['image1.png'], referenced_media=['image1.png'])
        files = [('page', 'page.png', b'render'),
                 ('image', 'image1.png', b'image1.png'),
                 ('support', 'requirements.md', b'confirmed requirements')]
        reviewed = []
        for kind, name, data in files:
            path = self.root / name
            path.write_bytes(data)
            reviewed.append({'kind': kind, 'path': name, 'sha256': _sha256(path)})
        evidence = {'requirements': 'requirements.md', 'redaction': 'image1.png',
                    'visual': 'page.png', 'operation': 'image1.png'}
        review = {'schema_version': 1, 'artifact': {'sha256': _sha256(docx)},
                  'builder': {'id': 'builder-1'}, 'reviewer': {'id': 'reviewer-2'},
                  'reviewed_files': reviewed,
                  'checks': {name: {'status': 'pass', 'reason': 'Directly reviewed',
                                    'evidence': [path]} for name, path in evidence.items()},
                  'overall': 'pass'}
        return docx, review

    def assess(self, docx, review):
        path = self.root / 'review.json'
        path.write_text(json.dumps(review), encoding='utf-8')
        return audit_delivery.audit_docx(docx, path)['independent_review']['status']

    def test_complete_hash_bound_record_is_accepted(self):
        docx, review = self.fixture()
        self.assertEqual(self.assess(docx, review), 'pass')

    def test_output_cannot_replace_later_evidence_after_nested_path(self):
        docx, review = self.fixture()
        nested = self.root / 'render'
        nested.mkdir()
        page = nested / 'page.png'
        page.write_bytes(b'render')
        review['reviewed_files'][0]['path'] = 'render/page.png'
        review_path = self.root / 'review.json'
        review_path.write_text(json.dumps(review), encoding='utf-8')
        support = self.root / 'requirements.md'
        before = support.read_bytes()
        code = audit_delivery.main(['--docx', str(docx), '--review', str(review_path),
                                    '--output', str(support)])
        self.assertEqual(code, 2)
        self.assertEqual(support.read_bytes(), before)

    def test_incomplete_and_stale_records_cannot_pass(self):
        docx, original = self.fixture()
        cases = {}
        def case(name):
            value = copy.deepcopy(original)
            cases[name] = value
            return value
        case('schema mismatch')['schema_version'] = 2
        case('pending reviewer')['reviewer']['id'] = 'pending'
        case('same reviewer')['reviewer']['id'] = 'builder-1'
        case('missing check')['checks'].pop('operation')
        case('missing overall').pop('overall')
        case('unknown evidence')['checks']['visual']['evidence'] = ['not-reviewed.png']
        case('missing reason')['checks']['requirements']['reason'] = ''
        case('required check not applicable')['checks']['visual']['status'] = 'na'
        case('changed docx')['artifact']['sha256'] = '0' * 64
        for index, kind in enumerate(['page', 'image', 'support']):
            case('stale ' + kind)['reviewed_files'][index]['sha256'] = '0' * 64
        value = case('missing support')
        value['reviewed_files'] = value['reviewed_files'][:2]
        value['checks']['requirements']['evidence'] = ['page.png']
        value = case('unrelated image with valid hash')
        value['reviewed_files'][1] = {'kind': 'image', 'path': 'page.png',
                                      'sha256': original['reviewed_files'][0]['sha256']}
        value['checks']['redaction']['evidence'] = ['page.png']
        value['checks']['operation']['evidence'] = ['page.png']
        case('failed operation')['checks']['operation']['status'] = 'fail'
        for name, value in cases.items():
            with self.subTest(name=name):
                self.assertNotEqual(self.assess(docx, value), 'pass')


if __name__ == '__main__':
    unittest.main()
