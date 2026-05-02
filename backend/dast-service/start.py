#!/usr/bin/env python3
# backend/dast-service/start.py

import subprocess
import os

def check_docker():
    try:
        r = subprocess.run(["docker", "info"], capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False

def pull_images():
    images = [
        # ── Original languages ─────────────────────────────────────────────
        "python:3.11-alpine",
        "node:18-alpine",
        "golang:1.21-alpine",
        # FIX: openjdk:17-alpine was REMOVED from Docker Hub (Feb 2024).
        #      eclipse-temurin:17-jdk-alpine is the official Adoptium replacement —
        #      same JDK 17, same Alpine base, maintained by Eclipse Foundation.
        "eclipse-temurin:17-jdk-alpine",

        # ── NEW languages ──────────────────────────────────────────────────
        # PHP: lightweight Alpine-based CLI image (~50MB), direct script execution
        "php:8.2-cli-alpine",
        # Ruby: lightweight Alpine-based image (~60MB), direct script execution
        "ruby:3.2-alpine",
        # C#: Mono provides mcs (compiler) + mono (runtime), lighter than dotnet SDK
        "mono:latest",
        # Rust: Alpine-based image with rustc compiler (~300MB compressed)
        "rust:1.75-alpine",
    ]
    print("\n🐳 Pre-pulling sandbox images...")
    for image in images:
        check = subprocess.run(
            ["docker", "image", "inspect", image],
            capture_output=True, timeout=5
        )
        if check.returncode == 0:
            print(f"  ✔ Already pulled: {image}")
            continue
        print(f"  ⬇️  Pulling {image}...")
        result = subprocess.run(["docker", "pull", image], timeout=300)
        if result.returncode == 0:
            print(f"  ✔ Pulled: {image}")
        else:
            print(f"  ⚠️  Failed to pull: {image} (sandbox for this language will be skipped)")

def main():
    print("=" * 60)
    print("🔬 DAST Microservice — Port 7095")
    print("=" * 60)

    docker_ok = check_docker()
    print(f"\n🐳 Docker: {'✔ available' if docker_ok else '⚠️  not available (pattern scan only)'}")

    if docker_ok:
        pull_images()
        print("\n📦 Sandbox language support:")
        print("   ✔ Python      (python:3.11-alpine)              ← direct run")
        print("   ✔ JavaScript  (node:18-alpine)                  ← direct run")
        print("   ✔ TypeScript  (node:18-alpine)                  ← direct run")
        print("   ✔ Go          (golang:1.21-alpine)              ← go run (compile + run)")
        print("   ✔ Java        (eclipse-temurin:17-jdk-alpine)   ← javac compile + java run")
        print("   ✔ PHP         (php:8.2-cli-alpine)              ← direct run")
        print("   ✔ Ruby        (ruby:3.2-alpine)                 ← direct run")
        print("   ✔ C#          (mono:latest)                     ← mcs compile + mono run")
        print("   ✔ Rust        (rust:1.75-alpine)                ← rustc compile + run")
    else:
        print("\n💡 To enable Docker sandbox execution:")
        print("   1. Install Docker Desktop from https://docker.com")
        print("   2. Start Docker Desktop")
        print("   3. Restart this service")

    print("\n Starting FastAPI server on http://localhost:7095")
    print("=" * 60 + "\n")

    os.execvp("uvicorn", [
        "uvicorn", "main:app",
        "--host", "0.0.0.0",
        "--port", "7095",
        "--reload",
    ])

if __name__ == "__main__":
    main()