#!/usr/bin/env python3
"""Plain-English -> code -> deploy kernel.

The kernel turns a natural-language build request into a deterministic project
manifest, optionally asks an LLM for source files, validates the generated
project, and can deploy it through a local command or Docker.

Safety boundary: deployment is opt-in with --deploy. Generated shell commands
are never executed implicitly.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


@dataclass
class ProjectSpec:
    name: str
    description: str
    language: str = "python"
    framework: str = "fastapi"
    entrypoint: str = "app.py"
    port: int = 8000
    files: dict[str, str] | None = None


class PlainEnglishKernel:
    """Small orchestration kernel with an LLM-optional compilation path."""

    def parse(self, prompt: str) -> ProjectSpec:
        p = prompt.strip()
        lower = p.lower()
        name_match = re.search(r"(?:called|named)\s+([a-zA-Z0-9_-]+)", p, re.I)
        name = name_match.group(1).lower() if name_match else "instant-app"
        port_match = re.search(r"port\s+(\d{2,5})", lower)
        port = int(port_match.group(1)) if port_match else 8000

        if "node" in lower or "javascript" in lower or "typescript" in lower:
            language, framework, entrypoint = "javascript", "express", "server.js"
        elif "flask" in lower:
            language, framework, entrypoint = "python", "flask", "app.py"
        else:
            language, framework, entrypoint = "python", "fastapi", "app.py"

        return ProjectSpec(
            name=name,
            description=p,
            language=language,
            framework=framework,
            entrypoint=entrypoint,
            port=port,
        )

    def compile(self, spec: ProjectSpec) -> ProjectSpec:
        if spec.framework == "fastapi":
            spec.files = {
                "app.py": self._fastapi_app(spec),
                "requirements.txt": "fastapi>=0.115,<1\nuvicorn[standard]>=0.30,<1\n",
                "Dockerfile": self._dockerfile(spec),
                ".dockerignore": ".git\n__pycache__\n*.pyc\n",
                "deploy.sh": self._deploy_script(spec),
            }
        elif spec.framework == "flask":
            spec.files = {
                "app.py": self._flask_app(spec),
                "requirements.txt": "flask>=3,<4\nwaitress>=3,<4\n",
                "Dockerfile": self._dockerfile(spec, "waitress-serve --listen=0.0.0.0:$PORT app:app"),
                "deploy.sh": self._deploy_script(spec),
            }
        else:
            spec.files = {
                "server.js": self._express_app(spec),
                "package.json": json.dumps({
                    "name": spec.name,
                    "private": True,
                    "scripts": {"start": "node server.js"},
                    "dependencies": {"express": "^5.1.0"},
                }, indent=2) + "\n",
                "Dockerfile": self._node_dockerfile(spec),
                "deploy.sh": self._deploy_script(spec),
            }
        return spec

    def _fastapi_app(self, spec: ProjectSpec) -> str:
        desc = json.dumps(spec.description)
        return f'''from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title={json.dumps(spec.name)}, description={desc})

class BuildRequest(BaseModel):
    prompt: str

@app.get("/health")
def health():
    return {{"status": "ok", "kernel": "plain-english", "app": {json.dumps(spec.name)}}}

@app.get("/")
def root():
    return {{"name": {json.dumps(spec.name)}, "description": {desc}, "status": "running"}}

@app.post("/build")
def build(req: BuildRequest):
    return {{"accepted": True, "prompt": req.prompt}}
'''

    def _flask_app(self, spec: ProjectSpec) -> str:
        return f'''from flask import Flask, jsonify
app = Flask(__name__)

@app.get("/health")
def health():
    return jsonify(status="ok", kernel="plain-english", app={json.dumps(spec.name)})

@app.get("/")
def root():
    return jsonify(name={json.dumps(spec.name)}, description={json.dumps(spec.description)}, status="running")
'''

    def _express_app(self, spec: ProjectSpec) -> str:
        return f'''const express = require("express");
const app = express();
app.use(express.json());
const port = Number(process.env.PORT || {spec.port});
app.get("/health", (_req, res) => res.json({{status: "ok", kernel: "plain-english", app: {json.dumps(spec.name)}}}));
app.get("/", (_req, res) => res.json({{name: {json.dumps(spec.name)}, description: {json.dumps(spec.description)}, status: "running"}}));
app.listen(port, "0.0.0.0", () => console.log(`listening on ${{port}}`));
'''

    def _dockerfile(self, spec: ProjectSpec, cmd: str | None = None) -> str:
        command = cmd or f"uvicorn app:app --host 0.0.0.0 --port $PORT"
        return f'''FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT={spec.port}
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE {spec.port}
CMD ["sh", "-c", {json.dumps(command)}]
'''

    def _node_dockerfile(self, spec: ProjectSpec) -> str:
        return f'''FROM node:22-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install --omit=dev
COPY . .
ENV PORT={spec.port}
EXPOSE {spec.port}
CMD ["npm", "start"]
'''

    def _deploy_script(self, spec: ProjectSpec) -> str:
        return f'''#!/usr/bin/env sh
set -eu
IMAGE="${{IMAGE_NAME:-{spec.name}:latest}}"
docker build -t "$IMAGE" .
docker run --rm -p "${{PORT:-{spec.port}}}:{spec.port}" "$IMAGE"
'''

    def write(self, spec: ProjectSpec, output: Path) -> Path:
        output.mkdir(parents=True, exist_ok=True)
        for name, content in (spec.files or {}).items():
            path = output / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            if name == "deploy.sh":
                path.chmod(0o755)
        (output / "manifest.json").write_text(
            json.dumps(asdict(spec), indent=2), encoding="utf-8"
        )
        return output

    def validate(self, output: Path) -> list[str]:
        errors: list[str] = []
        manifest = output / "manifest.json"
        if not manifest.exists():
            errors.append("missing manifest.json")
        if not ((output / "Dockerfile").exists()):
            errors.append("missing Dockerfile")
        if not ((output / "deploy.sh").exists()):
            errors.append("missing deploy.sh")
        if (output / "app.py").exists():
            result = subprocess.run(
                ["python", "-m", "py_compile", str(output / "app.py")],
                capture_output=True, text=True,
            )
            if result.returncode:
                errors.append(result.stderr.strip() or "Python syntax validation failed")
        return errors

    def deploy(self, output: Path, image: str | None = None) -> None:
        if not (output / "Dockerfile").exists():
            raise RuntimeError("No Dockerfile found")
        image = image or f"{output.name}:latest"
        subprocess.run(["docker", "build", "-t", image, str(output)], check=True)
        port = json.loads((output / "manifest.json").read_text())["port"]
        subprocess.run(["docker", "run", "--rm", "-p", f"{port}:{port}", image], check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Plain English -> code -> deploy kernel")
    parser.add_argument("prompt", help="Plain-English application request")
    parser.add_argument("--output", default="./generated", help="Generated project directory")
    parser.add_argument("--deploy", action="store_true", help="Build and run the generated Docker image")
    parser.add_argument("--json", action="store_true", help="Print the compiled manifest")
    args = parser.parse_args()

    kernel = PlainEnglishKernel()
    spec = kernel.compile(kernel.parse(args.prompt))
    output = kernel.write(spec, Path(args.output))
    errors = kernel.validate(output)
    if errors:
        print(json.dumps({"status": "invalid", "errors": errors}, indent=2))
        return 1

    result: dict[str, Any] = {
        "status": "ready",
        "project": spec.name,
        "path": str(output.resolve()),
        "framework": spec.framework,
        "port": spec.port,
        "files": sorted(spec.files or {}),
    }
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"READY: {spec.name}")
        print(f"PROJECT: {output.resolve()}")
        print(f"RUN: cd {output} && ./deploy.sh")

    if args.deploy:
        kernel.deploy(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
