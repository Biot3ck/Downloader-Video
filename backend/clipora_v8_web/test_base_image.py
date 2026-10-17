"""The pinned base image is declared once and cannot drift from the Dockerfile."""
from pathlib import Path
import re
import unittest
from clipora_v8_web.build_image import base_image, HERE


class BaseImagePinTests(unittest.TestCase):
    def test_pin_is_well_formed(self):
        image,digest=base_image()
        self.assertRegex(digest,r'^sha256:[a-f0-9]{64}$')
        self.assertNotIn('*',image)
        self.assertNotIn('@',image)

    def test_dockerfile_from_matches_pin(self):
        image,_=base_image()
        lines=(HERE/'Dockerfile').read_text().splitlines()
        self.assertEqual([line.split(None,1)[1].strip() for line in lines if line.upper().startswith('FROM ')],[image])

    def test_review_document_points_at_the_pin_instead_of_quoting_an_image_id(self):
        # A built image ID changes on every rebuild, so quoting one in prose
        # makes the audit record look stale. Reference the lock file instead.
        text=(HERE/'docs'/'OS_PACKAGE_REVIEW.md').read_text()
        self.assertIn('base_image.lock',text)
        for match in re.findall(r'--image-id (\S+)',text):
            self.assertFalse(re.fullmatch(r'sha256:[a-f0-9]{64}',match),
                             'Review document quotes a rebuild-dependent image id')


if __name__=='__main__':unittest.main()
