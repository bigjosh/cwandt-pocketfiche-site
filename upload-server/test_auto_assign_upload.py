#!/usr/bin/env python3
"""Focused tests for upload-time random parcel assignment."""

import atexit
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


LOCK_DATA_DIR = tempfile.TemporaryDirectory()
atexit.register(LOCK_DATA_DIR.cleanup)
os.environ['PF_DATA_DIR'] = LOCK_DATA_DIR.name

APP_PATH = Path(__file__).with_name('app.py')
SPEC = importlib.util.spec_from_file_location('pocketfiche_upload_app', APP_PATH)
app = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = app
SPEC.loader.exec_module(app)


def make_parcel_png(size=(500, 500), fill=1):
    output = io.BytesIO()
    Image.new('1', size, fill).save(output, format='PNG')
    return output.getvalue()


def response_json(response):
    _status, _headers, body = response
    return json.loads(body.decode('utf-8'))


class AutoAssignUploadTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        for dirname in ('access', 'admins', 'locations', 'parcels'):
            (self.data_dir / dirname).mkdir()
        self.image_data = make_parcel_png()

    def tearDown(self):
        self.temp_dir.cleanup()

    def create_access_code(self, code='TESTCODE'):
        (self.data_dir / 'access' / f'{code}.txt').write_text(
            'backer@example.com\nAdmin\nnotes',
            encoding='utf-8'
        )
        return code

    def create_admin_id(self, admin_id='ADMINID'):
        (self.data_dir / 'admins' / f'{admin_id}.txt').write_text(
            'Admin\nnotes',
            encoding='utf-8'
        )
        return admin_id

    def upload(self, form_data, code='TESTCODE'):
        self.create_access_code(code)
        form_data = {'code': [code], **form_data}
        return response_json(app.handle_upload(
            form_data,
            {'image': self.image_data},
            self.data_dir
        ))

    def test_manual_location_upload_still_succeeds(self):
        data = self.upload({'parcel-location': ['S19']})

        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['location'], 'S19')
        self.assertTrue((self.data_dir / 'parcels' / 'S19.png').exists())

    def test_auto_assign_upload_picks_valid_location(self):
        data = self.upload({'auto-assign-location': ['true']})

        self.assertEqual(data['status'], 'success')
        self.assertIn(data['location'], app.build_valid_parcel_locations())
        self.assertEqual(
            (self.data_dir / 'locations' / 'TESTCODE.txt').read_text(encoding='utf-8'),
            data['location']
        )
        self.assertTrue((self.data_dir / 'parcels' / f"{data['location']}.png").exists())

    def test_auto_assign_rejects_ambiguous_location_mode(self):
        code = self.create_access_code()

        data = response_json(app.handle_upload(
            {
                'code': [code],
                'parcel-location': ['S19'],
                'auto-assign-location': ['true']
            },
            {'image': self.image_data},
            self.data_dir
        ))

        self.assertEqual(data['status'], 'error')
        self.assertEqual(
            data['message'],
            'Specify either parcel-location or auto-assign-location, not both'
        )

    def test_upload_requires_location_or_auto_assign(self):
        data = self.upload({})

        self.assertEqual(data['status'], 'error')
        self.assertEqual(data['message'], 'Need parcel-location or auto-assign-location')

    def test_auto_assign_skips_claimed_locations_and_real_images(self):
        code = self.create_access_code()
        valid_locations = sorted(app.build_valid_parcel_locations())
        target_location = valid_locations[0]
        real_image_location = valid_locations[1]

        for index, location in enumerate(valid_locations):
            if location == target_location:
                continue
            if location == real_image_location:
                (self.data_dir / 'parcels' / f'{location}.png').write_bytes(self.image_data)
            else:
                (self.data_dir / 'locations' / f'CLAIM{index}.txt').write_text(
                    location,
                    encoding='utf-8'
                )

        data = response_json(app.handle_upload(
            {'code': [code], 'auto-assign-location': ['true']},
            {'image': self.image_data},
            self.data_dir
        ))

        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['location'], target_location)

    def test_auto_assign_returns_error_when_no_locations_available(self):
        code = self.create_access_code()
        for index, location in enumerate(sorted(app.build_valid_parcel_locations())):
            (self.data_dir / 'locations' / f'CLAIM{index}.txt').write_text(
                location,
                encoding='utf-8'
            )

        data = response_json(app.handle_upload(
            {'code': [code], 'auto-assign-location': ['true']},
            {'image': self.image_data},
            self.data_dir
        ))

        self.assertEqual(data['status'], 'error')
        self.assertEqual(data['message'], 'No available parcel locations')

    def test_replace_image_replaces_existing_parcel_without_changing_metadata(self):
        code = self.create_access_code()
        admin_id = self.create_admin_id()
        location = 'S19'
        original_access_content = (self.data_dir / 'access' / f'{code}.txt').read_text(
            encoding='utf-8'
        )
        (self.data_dir / 'locations' / f'{code}.txt').write_text(location, encoding='utf-8')
        (self.data_dir / 'parcels' / f'{location}.png').write_bytes(make_parcel_png(fill=1))

        data = response_json(app.handle_replace_image(
            {'admin-id': [admin_id], 'location': [location]},
            {'image': make_parcel_png(fill=0)},
            self.data_dir
        ))

        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['location'], location)
        self.assertEqual(
            (self.data_dir / 'locations' / f'{code}.txt').read_text(encoding='utf-8'),
            location
        )
        self.assertEqual(
            (self.data_dir / 'access' / f'{code}.txt').read_text(encoding='utf-8'),
            original_access_content
        )
        with Image.open(self.data_dir / 'parcels' / f'{location}.png') as saved_image:
            self.assertEqual(saved_image.getpixel((0, 0)), 0)

    def test_replace_image_requires_existing_parcel_file(self):
        admin_id = self.create_admin_id()

        data = response_json(app.handle_replace_image(
            {'admin-id': [admin_id], 'parcel-location': ['S19']},
            {'image': make_parcel_png(fill=0)},
            self.data_dir
        ))

        self.assertEqual(data['status'], 'error')
        self.assertEqual(data['message'], 'No image file found')

    def test_replace_image_requires_admin_auth(self):
        location = 'S19'
        (self.data_dir / 'parcels' / f'{location}.png').write_bytes(make_parcel_png(fill=1))

        data = response_json(app.handle_replace_image(
            {'admin-id': ['BADID'], 'parcel-location': [location]},
            {'image': make_parcel_png(fill=0)},
            self.data_dir
        ))

        self.assertEqual(data['status'], 'error')
        self.assertEqual(data['message'], 'Not authorized')


if __name__ == '__main__':
    unittest.main()
