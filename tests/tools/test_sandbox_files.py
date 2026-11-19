"""沙箱文件工具的下载地址格式：相对 harness，且对中文文件名做转义。"""
import unittest

from src.agent.tools.sandbox_files import _download_url


class DownloadUrlTests(unittest.TestCase):
    def test_returns_relative_url(self):
        self.assertEqual(_download_url("chart.png"), "/api/download/chart.png")

    def test_encodes_chinese_and_spaces(self):
        self.assertEqual(
            _download_url("2026年度前5大供应商采购金额对比.png"),
            "/api/download/2026%E5%B9%B4%E5%BA%A6%E5%89%8D5%E5%A4%A7%E4%BE%9B%E5%BA%94%E5%95%86%E9%87%87%E8%B4%AD%E9%87%91%E9%A2%9D%E5%AF%B9%E6%AF%94.png",
        )
        self.assertEqual(_download_url("a b.md"), "/api/download/a%20b.md")


if __name__ == "__main__":
    unittest.main()
