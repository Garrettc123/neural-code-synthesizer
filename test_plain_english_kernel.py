import json
import tempfile
import unittest
from pathlib import Path

from plain_english_kernel import PlainEnglishKernel


class PlainEnglishKernelTests(unittest.TestCase):
    def test_fastapi_compile(self):
        kernel = PlainEnglishKernel()
        with tempfile.TemporaryDirectory() as tmp:
            spec = kernel.compile(kernel.parse("build a FastAPI service called demo-api on port 8081"))
            out = kernel.write(spec, Path(tmp) / "demo")
            self.assertEqual(spec.name, "demo-api")
            self.assertEqual(spec.port, 8081)
            self.assertIn("app.py", spec.files)
            self.assertTrue((out / "Dockerfile").exists())
            self.assertEqual(kernel.validate(out), [])
            manifest = json.loads((out / "manifest.json").read_text())
            self.assertEqual(manifest["framework"], "fastapi")

    def test_node_detection(self):
        kernel = PlainEnglishKernel()
        with tempfile.TemporaryDirectory() as tmp:
            spec = kernel.compile(kernel.parse("make a node javascript API called edge-api"))
            self.assertEqual(spec.framework, "express")
            out = kernel.write(spec, Path(tmp) / "edge")
            self.assertTrue((out / "server.js").exists())
            self.assertTrue((out / "package.json").exists())


if __name__ == "__main__":
    unittest.main()
