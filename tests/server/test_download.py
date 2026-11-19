"""下载端点的回归测试：中文文件名不能把 Content-Disposition 打成 500。"""
import unittest
from urllib.parse import quote

from fastapi.testclient import TestClient

from src.server.main import DOWNLOAD_DIR, app


class DownloadEndpointTests(unittest.TestCase):
    def setUp(self):
        self.name = "测试图表_回归.png"
        self.target = DOWNLOAD_DIR / self.name
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        self.target.write_bytes(b"\x89PNG\r\n\x1a\nFakeImageBytes")
        self.client = TestClient(app)

    def tearDown(self):
        self.target.unlink(missing_ok=True)

    def test_chinese_filename_is_served(self):
        response = self.client.get("/api/download/" + quote(self.name))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.headers["content-type"].startswith("image/png"))
        disposition = response.headers["content-disposition"]
        self.assertIn("inline", disposition)
        self.assertIn("filename*=UTF-8''", disposition)

    def test_path_traversal_is_rejected(self):
        response = self.client.get("/api/download/..%2F..%2Fetc%2Fpasswd")
        self.assertEqual(response.status_code, 404)

    def test_missing_file_returns_404(self):
        response = self.client.get("/api/download/" + quote("不存在的文件.png"))
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
