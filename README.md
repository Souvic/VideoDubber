# VideoDubber — AI Video Translation, Dubbing & Voice Cloning

**Official home of the [VideoDubber](https://videodubber.ai) API clients** — translate, dub, and clone voices in 150+ languages with AI. Premium quality at a fraction of the cost.

[![PyPI](https://img.shields.io/pypi/v/videodubber.svg)](https://pypi.org/project/videodubber/)
[![npm](https://img.shields.io/npm/v/videodubber.svg)](https://www.npmjs.com/package/videodubber)
[![Python](https://img.shields.io/pypi/pyversions/videodubber.svg)](https://pypi.org/project/videodubber/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)

| | |
|---|---|
| **Website** | [videodubber.ai](https://videodubber.ai) |
| **Developer portal** | [videodubber.ai/developers](https://videodubber.ai/developers/) |
| **PyPI (Python)** | [pypi.org/project/videodubber](https://pypi.org/project/videodubber/) |
| **npm (JavaScript)** | [npmjs.com/package/videodubber](https://www.npmjs.com/package/videodubber) |
| **API reference** | [videodubber_client.md](./videodubber_client.md) |
| **Pricing** | [videodubber.ai/pricing](https://videodubber.ai/pricing/) |

---

## For developers — automate video translation

Use the **official clients** to submit a public media URL to [`api.videodubber.ai`](https://api.videodubber.ai), poll for completion, and download the translated file.

### Python

```bash
pip install videodubber
```

```bash
export VIDEODUBBER_API_KEY="your-api-key"

videodubber \
  --file-url "https://example.com/video.mp4" \
  --target-language Spanish \
  --voice Elvira \
  --output ./translated.mp4
```

```python
from videodubber import VideoDubberClient, TranslationJobParams

client = VideoDubberClient(api_key="your-api-key")
status = client.translate_from_url(
    TranslationJobParams(
        file_url="https://example.com/video.mp4",
        target_language="Spanish",
        selectedvoices=["Elvira"],
        speakers=["Speaker 1"],
        filetype="mp4",
    )
)
print(status.translated_media_url)
```

### JavaScript / TypeScript

```bash
npm install videodubber
```

```javascript
import { VideoDubberClient } from "videodubber";

const client = new VideoDubberClient({ apiKey: process.env.VIDEODUBBER_API_KEY });
const status = await client.translateFromUrl({
  fileUrl: "https://example.com/video.mp4",
  targetLanguage: "Spanish",
  selectedVoices: ["Elvira"],
  speakers: ["Speaker 1"],
  filetype: "mp4",
});

console.log(status.translatedMediaUrl);
```

CLI (Node.js 18+):

```bash
export VIDEODUBBER_API_KEY="your-api-key"

npx videodubber \
  --file-url "https://example.com/video.mp4" \
  --target-language Spanish \
  --voice Elvira \
  --output ./translated.mp4
```

**Documentation**

- **[Developer portal](https://videodubber.ai/developers/)** — REST quickstart, auth, rate limits, and integration guide
- **[Full API & CLI reference](./videodubber_client.md)** — endpoints, arguments, error codes, and library methods
- **[PyPI: videodubber](https://pypi.org/project/videodubber/)** — Python package
- **[npm: videodubber](https://www.npmjs.com/package/videodubber)** — JavaScript/TypeScript package

---

## How to Generate VideoDubber API Key

API access is included on [paid plans](https://videodubber.ai/pricing/). Once subscribed:

1. **Log in** to [app.videodubber.ai](https://app.videodubber.ai/)
2. Open **API Keys** in your account
3. Click **Generate API key** and copy the key immediately — it is shown once
4. Store the key securely (password manager or secrets vault). Never commit it to git or expose it in browser/client-side code

**Use your key**

| Method | How |
|--------|-----|
| Python CLI | `export VIDEODUBBER_API_KEY="your-api-key"` or pass `--api-key "your-api-key"` |
| Python library | `VideoDubberClient(api_key="your-api-key")` |
| JavaScript / TypeScript | `new VideoDubberClient({ apiKey: "your-api-key" })` |
| Node CLI | `export VIDEODUBBER_API_KEY="your-api-key"` or pass `--api-key "your-api-key"` |
| REST / curl | Add header `x-api-key: your-api-key` on every `/api/p/*` request |

You can also manage keys programmatically while authenticated:

| Action | Endpoint |
|--------|----------|
| View existing key | `GET /api/p/api-key` |
| Generate new key | `POST /api/p/api-key` |
| Revoke key | `DELETE /api/p/api-key` |

Need help? Email [contact@videodubber.ai](mailto:contact@videodubber.ai) or see the [developer portal](https://videodubber.ai/developers/).

---

## For everyone — translate videos in the app

No code required. Translate your video in three steps:

1. Go to **[VideoDubber.ai](https://videodubber.ai)** and click **Get Started**
2. Upload your video (or paste a YouTube link)
3. Choose target languages and voices — or clone the original speaker

Download translated MP4s and subtitles in seconds. **Free for short videos, no watermark.**

---

## Why VideoDubber?

- **20× cheaper** than typical premium AI dubbing — see [pricing](https://videodubber.ai/pricing/)
- **150+ languages** — scale your audience without re-shooting
- **Voice cloning** powered by in-house research (no third-party TTS API)
- **Studio-quality output** — subtitles, lip-sync, and editing in one place
- **Free tier** for short clips — test quality before you commit
- **Human support** at [contact@videodubber.ai](mailto:contact@videodubber.ai)

---

## Supported by

<p align="center">
  <img src="https://raw.githubusercontent.com/Souvic/VideoDubber/main/assets/supported-by/google-for-startups.svg" alt="Google for Startups" height="48"/>
  &nbsp;&nbsp;
  <img src="https://raw.githubusercontent.com/Souvic/VideoDubber/main/assets/supported-by/aws.webp" alt="AWS for Startups" height="48"/>
  &nbsp;&nbsp;
  <img src="https://raw.githubusercontent.com/Souvic/VideoDubber/main/assets/supported-by/microsoft-for-startups.jpg" alt="Microsoft for Startups" height="48"/>
</p>

---

<p align="center">
  <a href="https://videodubber.ai">Try VideoDubber free</a> ·
  <a href="https://videodubber.ai/developers/">Developer API</a> ·
  <a href="https://pypi.org/project/videodubber/">PyPI</a> ·
  <a href="https://www.npmjs.com/package/videodubber">npm</a>
</p>
