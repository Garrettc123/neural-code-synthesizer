import json
from pathlib import Path

from plain_english_kernel import PlainEnglishKernel


def test_fastapi_compile(tmp_path: Path):
    kernel = PlainEnglishKernel()
    spec = kernel.compile(kernel.parse("build a FastAPI service called demo-api on port 8081"))
    out = kernel.write(spec, tmp_path / "demo")
    assert spec.name == "demo-api"
    assert spec.port == 8081
    assert "app.py" in spec.files
    assert (out / "Dockerfile").exists()
    assert kernel.validate(out) == []
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["framework"] == "fastapi"


def test_node_detection(tmp_path: Path):
    kernel = PlainEnglishKernel()
    spec = kernel.compile(kernel.parse("make a node javascript API called edge-api"))
    assert spec.framework == "express"
    out = kernel.write(spec, tmp_path / "edge")
    assert (out / "server.js").exists()
    assert (out / "package.json").exists()
