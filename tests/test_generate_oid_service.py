import pytest
from unittest.mock import MagicMock
from utils.generate_oid_service import build_s3_url, assemble_service_metadata, update_oid_image_paths, ensure_portal_folder

# Test build_s3_url
@pytest.mark.parametrize("bucket,region,bucket_folder,filename,expected_url", [
    ("mybucket", "us-west-2", "images", "img1.jpg", "https://mybucket.s3.us-west-2.amazonaws.com/images/img1.jpg"),
    ("b", "r", "f", "file.png", "https://b.s3.r.amazonaws.com/f/file.png"),
])
def test_build_s3_url(bucket, region, bucket_folder, filename, expected_url):
    assert build_s3_url(bucket, region, bucket_folder, filename) == expected_url

# Test assemble_service_metadata
class DummyCfg:
    def __init__(self, vals):
        self.vals = vals
    def get(self, k, default=None):
        return self.vals.get(k, default)
    def resolve(self, v):
        if isinstance(v, list):
            return [f"RESOLVED_{x}" for x in v]
        return f"RESOLVED_{v}" if v else v

def test_assemble_service_metadata():
    vals = {
        "portal.project_folder": "myfolder",
        "portal.share_with": "PUBLIC",
        "portal.add_footprint": "NO_FOOTPRINT",
        "portal.portal_tags": ["tag1", "tag2"],
        "portal.summary": "summarytext"
    }
    cfg = DummyCfg(vals)
    result = assemble_service_metadata(cfg, "oidname")
    service_name, portal_folder, share_with, add_footprint, tags_str, summary = result
    assert service_name == "oidname"
    assert portal_folder.startswith("RESOLVED_")
    assert share_with == "PUBLIC"
    assert add_footprint == "NO_FOOTPRINT"
    assert "RESOLVED_tag1" in tags_str and "RESOLVED_tag2" in tags_str
    assert summary.startswith("RESOLVED_")

# Test update_oid_image_paths (mocked arcpy)
def test_update_oid_image_paths(monkeypatch):
    # Mock arcpy.da.UpdateCursor
    rows = [["/tmp/abc.jpg"], ["/tmp/def.png"]]
    class DummyCursor:
        def __init__(self, data):
            self.data = data
            self.idx = 0
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def __iter__(self): return iter(self.data)
        def updateRow(self, row):
            self.updated = getattr(self, 'updated', [])
            self.updated.append(row[0])
    dummy_logger = MagicMock()
    monkeypatch.setattr("arcpy.da.UpdateCursor", lambda oid_fc, fields: DummyCursor(rows))
    monkeypatch.setattr("os.path.basename", lambda p: p.split("/")[-1])
    updated_count = update_oid_image_paths("dummy_fc", "bucket", "region", "folder", dummy_logger)
    assert updated_count == 2
    dummy_logger.info.assert_called_with("Updated 2 image paths to AWS URLs.")

# Test ensure_portal_folder (mock GIS)
def test_ensure_portal_folder_creates(monkeypatch):
    dummy_logger = MagicMock()
    class DummyFolders:
        def __init__(self, folders): self.folders = folders
        def __iter__(self): return iter(self.folders)
    class DummyUser:
        def __init__(self, folders): self.folders = folders
    class DummyContent:
        def __init__(self): pass
        def folders(self): return self
        def create(self, folder): self.created = folder
    class DummyGIS:
        def __init__(self, folders):
            self.users = MagicMock()
            self.users.me = DummyUser(folders)
            self.content = MagicMock()
            self.content.folders.create = MagicMock()
    # Test folder does not exist
    gis = DummyGIS([{"title": "existing"}])
    ensure_portal_folder(gis, "newfolder", dummy_logger)
    dummy_logger.warning.assert_any_call("Portal folder 'newfolder' does not exist. Attempting to create it...")
    dummy_logger.info.assert_any_call("✅ Portal folder 'newfolder' created successfully.")
    # Test folder exists
    dummy_logger.reset_mock()
    gis = DummyGIS([{"title": "existing"}, {"title": "newfolder"}])
    ensure_portal_folder(gis, "newfolder", dummy_logger)
    dummy_logger.info.assert_any_call("📁 Portal folder found: newfolder")
