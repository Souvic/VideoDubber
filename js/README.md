# videodubber

**Official JavaScript/TypeScript client for [VideoDubber.ai](https://videodubber.ai)** — AI video translation, audio dubbing, and voice cloning in **150+ languages**. Automate the Partner API at `api.videodubber.ai` from Node.js, Deno, or any JavaScript runtime with native `fetch`.

[![npm version](https://img.shields.io/npm/v/videodubber.svg)](https://www.npmjs.com/package/videodubber)
[![PyPI](https://img.shields.io/pypi/v/videodubber.svg)](https://pypi.org/project/videodubber/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://github.com/Souvic/VideoDubber/blob/main/LICENSE)

| | |
|---|---|
| **Website** | [videodubber.ai](https://videodubber.ai) |
| **Developer portal** | [videodubber.ai/developers](https://videodubber.ai/developers/) |
| **npm (this package)** | [npmjs.com/package/videodubber](https://www.npmjs.com/package/videodubber) |
| **PyPI (Python client)** | [pypi.org/project/videodubber](https://pypi.org/project/videodubber/) |
| **Full API reference** | [GitHub: videodubber_client.md](https://github.com/Souvic/VideoDubber/blob/main/videodubber_client.md) |
| **Pricing & API access** | [videodubber.ai/pricing](https://videodubber.ai/pricing/) |

---

## What does this package do?

Translate video or audio **programmatically**:

1. **POST** `/api/p/jobs` with a public media URL, target language, and voices
2. **Poll** `/api/p/jobs/{pid}/status` until `status` is `complete`
3. Download the translated file from `output_urls.translated_media`

This client handles **rate-limit throttling** (12 s minimum between calls), **429 retries**, polling, and optional CLI download — the same workflow as the [Video Translation app](https://app.videodubber.ai/).

Also available for **Python**: `pip install videodubber` on [PyPI](https://pypi.org/project/videodubber/).

---

## Installation

```bash
npm install videodubber
```

**Requirements:** Node.js **18+** (native `fetch`), a [VideoDubber API key](https://videodubber.ai/pricing/), and a stable public `http`/`https` URL to your source media.

---

## Quick start (library)

```javascript
import { VideoDubberClient } from "videodubber";

const client = new VideoDubberClient({
  apiKey: process.env.VIDEODUBBER_API_KEY,
});

const status = await client.translateFromUrl({
  fileUrl: "https://example.com/video.mp4",
  targetLanguage: "Spanish",
  originalLanguage: "English",
  selectedVoices: ["Elvira"],
  speakers: ["Speaker 1"],
  filetype: "mp4",
});

console.log(status.translatedMediaUrl);
```

### TypeScript

Full types are included. Import `TranslationJobParams`, `JobStatus`, and error classes from `"videodubber"`.

---

## CLI

After install, use the `videodubber` command (Node 18+):

```bash
export VIDEODUBBER_API_KEY="your-api-key"

npx videodubber \
  --file-url "https://example.com/video.mp4" \
  --target-language Spanish \
  --voice Elvira \
  --output ./translated.mp4
```

Or without installing globally:

```bash
npm install -g videodubber
videodubber --help
```

---

## How to get an API key

API access is on [paid plans](https://videodubber.ai/pricing/):

1. Log in at [app.videodubber.ai](https://app.videodubber.ai/)
2. Open **API Keys** in your account
3. Click **Generate API key** and store it securely

Use via environment variable:

```bash
export VIDEODUBBER_API_KEY="your-api-key"
# optional: export VIDEODUBBER_API_BASE="https://api.videodubber.ai"
```

Or pass `{ apiKey: "..." }` to `VideoDubberClient`.

---

## API methods

| Method | Description |
|--------|-------------|
| `createJobFromUrl(params)` | Submit job; returns `{ pid, status, ... }` |
| `getJobStatus(pid)` | Single status poll |
| `waitForJob(pid, options?)` | Poll until complete, failed, or timeout |
| `translateFromUrl(params, options?)` | Create + wait (full workflow) |
| `health()` | `GET /` health check |

See the [developer portal](https://videodubber.ai/developers/) and [full API docs on GitHub](https://github.com/Souvic/VideoDubber/blob/main/videodubber_client.md) for request fields, languages, voices, and error codes.

---

## Rate limits

- **5 requests / minute** per API key on `/api/p/*` endpoints
- Minimum **12 s** between calls (enforced by this client)
- Default poll interval: **15 s**

Do not run many parallel jobs on one API key.

---

## Keywords

VideoDubber · video translation API · AI dubbing · voice cloning · subtitle translation · localization · text-to-speech · Node.js SDK · TypeScript client · media translation · 150+ languages

---

## Links

- [VideoDubber.ai](https://videodubber.ai) — try free in the browser
- [Developer API docs](https://videodubber.ai/developers/)
- [Python client on PyPI](https://pypi.org/project/videodubber/)
- [GitHub repository](https://github.com/Souvic/VideoDubber)
- [Support](mailto:contact@videodubber.ai)

**License:** [GPL-3.0-or-later](https://github.com/Souvic/VideoDubber/blob/main/LICENSE)
