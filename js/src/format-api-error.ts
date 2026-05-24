export function formatApiError(body: unknown): string {
  if (!body || typeof body !== "object") {
    return String(body);
  }

  const record = body as Record<string, unknown>;
  const lines: string[] = [];
  const error = record.error ?? record.alert;
  if (error) {
    lines.push(`error: ${String(error)}`);
  }

  if (record.received !== undefined) {
    lines.push(`received: ${String(record.received)}`);
  }

  const details = Array.isArray(record.details) ? record.details : [];
  if (details.length) {
    if (lines.length) {
      lines.push("");
    }
    for (const detail of details) {
      lines.push(`  - ${String(detail)}`);
    }
  }

  const acceptedLangs = Array.isArray(record.accepted_target_languages)
    ? record.accepted_target_languages
    : [];
  if (acceptedLangs.length) {
    if (lines.length) {
      lines.push("");
    }
    lines.push(`accepted target languages (${acceptedLangs.length}):`);
    lines.push("");
    for (const lang of acceptedLangs) {
      lines.push(`  - ${String(lang)}`);
    }
  }

  const acceptedVoices = Array.isArray(record.accepted_voices)
    ? record.accepted_voices
    : [];
  if (acceptedVoices.length) {
    const targetLanguage = record.target_language ?? "target language";
    if (lines.length) {
      lines.push("");
    }
    lines.push(
      `accepted voices for ${String(targetLanguage)} (${acceptedVoices.length}):`,
    );

    const byGender: Record<string, string[]> = { MALE: [], FEMALE: [] };
    const other: string[] = [];
    for (const voice of acceptedVoices) {
      if (voice && typeof voice === "object") {
        const voiceRecord = voice as Record<string, unknown>;
        const name = String(voiceRecord.name ?? "");
        const gender = String(voiceRecord.gender ?? "").toUpperCase();
        if (gender === "MALE" || gender === "FEMALE") {
          byGender[gender].push(name);
        } else {
          other.push(name);
        }
      } else {
        other.push(String(voice));
      }
    }

    for (const [genderKey, title] of [
      ["MALE", "male voices"],
      ["FEMALE", "female voices"],
    ] as const) {
      const names = byGender[genderKey];
      if (names.length) {
        lines.push("");
        lines.push(`${title}:`);
        for (const name of names) {
          lines.push(`  - ${name}`);
        }
      }
    }

    if (other.length) {
      lines.push("");
      lines.push("other voices:");
      for (const name of other) {
        lines.push(`  - ${name}`);
      }
    }
  }

  if (lines.length === 1 && error) {
    const extra = Object.fromEntries(
      Object.entries(record).filter(([key]) => key !== "error" && key !== "alert"),
    );
    if (Object.keys(extra).length) {
      lines.push("");
      lines.push(JSON.stringify(extra, null, 2));
    }
  }

  return lines.join("\n");
}
