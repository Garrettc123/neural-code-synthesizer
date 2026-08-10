# neural-code-synthesizer

Plain-English to runnable code with an explicit instant-deploy path.

## One command

```bash
python plain_english_kernel.py "build a FastAPI service called hello-api on port 8080"
```

The kernel creates `./generated` containing application source, dependencies, a Dockerfile, a deploy script, and `manifest.json`. It validates the generated project before reporting `READY`.

## Build and run immediately

```bash
python plain_english_kernel.py "build a FastAPI service called hello-api on port 8080" --deploy
```

Deployment is explicit. Natural-language input is never executed as shell syntax.

## Supported fast paths

- Python + FastAPI (default)
- Python + Flask
- Node.js + Express

The deterministic compiler is the execution core. An LLM/compiler adapter can later produce richer `ProjectSpec` objects without changing the deployment contract.

## Architecture

```text
Plain English -> Parser -> ProjectSpec -> Compiler -> Validator -> READY
                                      |              |
                                      +-> source     +-> optional Docker deploy
                                      +-> deps
                                      +-> Dockerfile
                                      +-> deploy.sh
                                      +-> manifest.json
```
