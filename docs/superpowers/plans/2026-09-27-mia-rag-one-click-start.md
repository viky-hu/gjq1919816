# MiA-RAG One-Click Startup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the root `一键启动.bat` reliably launch the local FastAPI service, encrypted node service, and Next.js development frontend together, while clearly identifying missing local API configuration.

**Architecture:** Keep the BAT as a thin Windows entry point and use the existing `start-local.ps1` for checks, environment loading, dependency setup, and three service windows. Add explicit diagnostics for the ignored root `backend.local.env` file and its `DEEPSEEK_API_KEY` entry without placing secrets in tracked files.

**Tech Stack:** Windows batch, PowerShell, Python/FastAPI, pnpm/Next.js.

## Global Constraints

- Preserve the existing service ports: API `6006`, node server `6008`, frontend `3000`.
- Keep secrets out of Git-tracked files; read them from `backend.local.env`.
- Preserve relative project paths so the launcher works when double-clicked from Explorer.
- Do not require model weights to be committed to the repository.

### Task 1: Improve local configuration diagnostics

**Files:**
- Modify: `start-local.ps1`
- Modify: `一键启动.bat`
- Reference: `backend.local.env.example`

**Interfaces:**
- `start-local.ps1` continues to accept `-CheckOnly`, `-SkipInstall`, and `-NoBrowser`.
- The BAT continues to invoke the PowerShell script from `%~dp0`.

- [x] **Step 1: Add explicit configuration paths and API-key diagnostics**

  Load `backend.local.env` as today, report its exact absolute path, and warn when `DEEPSEEK_API_KEY` is absent or still set to the repository placeholder. Explain that the value belongs on the `DEEPSEEK_API_KEY=` line in `backend.local.env`; continue startup so model-only health checks remain possible.

- [x] **Step 2: Improve BAT failure messaging**

  Keep the wrapper directory-independent and make failures identify `backend.local.env` and `backend.local.env.example` as the configuration locations.

- [x] **Step 3: Run static checks**

  Parse the PowerShell script with PowerShell's parser, inspect the BAT text for the expected invocation, and run the launcher's `-CheckOnly -SkipInstall -NoBrowser` path only if all local prerequisites are already present.

- [x] **Step 4: Commit**

  Commit the launcher changes with message `feat: improve local one-click startup diagnostics`.
