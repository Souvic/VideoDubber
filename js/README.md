# videodubber (npm)

Official JavaScript/TypeScript client for the [VideoDubber.ai](https://videodubber.ai) video translation API.

```bash
npm install videodubber
```

Full documentation: [videodubber_client.md](../videodubber_client.md) · [Developer portal](https://videodubber.ai/developers/)

## Quick example

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

## Development

```bash
npm install
npm run build
```

Version is synced from the repo root [`VERSION`](../VERSION) file on build.
