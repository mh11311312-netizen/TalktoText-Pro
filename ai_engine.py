"""
Handles the AI side of things: transcription, translation, cleaning up the
text, and asking the model to write up the notes. I kept everything that
touches OpenAI/AssemblyAI in this one module so the Flask code stays readable.
"""

import os
import re
import json
import time
import requests
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

_api_key = os.getenv("OPENAI_API_KEY", "")
client = OpenAI(api_key=_api_key) if _api_key else None

# Optional. When it's set we use AssemblyAI for the speaker labels; when it's
# not, we just fall back to Whisper and skip the "who spoke" part.
ASSEMBLYAI_KEY = os.getenv("ASSEMBLYAI_API_KEY", "").strip()


def _require_client():
    if client is None:
        raise RuntimeError("OPENAI_API_KEY is not set. Add it to your .env file.")


def _ask_gpt_json(system_prompt, user_prompt):
    # Same as _ask_gpt_text but forces the reply to be valid JSON.
    _require_client()
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": system_prompt},
                  {"role": "user", "content": user_prompt}],
        response_format={"type": "json_object"},
        temperature=0.3,
    )
    try:
        return json.loads(response.choices[0].message.content)
    except json.JSONDecodeError:
        # Shouldn't happen with json_object mode, but don't blow up if it does.
        return {}


def _ask_gpt_text(system_prompt, user_prompt, temperature=0.4):
    _require_client()
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": system_prompt},
                  {"role": "user", "content": user_prompt}],
        temperature=temperature,
    )
    return response.choices[0].message.content.strip()


def transcribe_audio(file_path, language="auto"):
    # Plain Whisper transcription. verbose_json gives us the per-segment
    # timestamps which we need later for the chapters.
    _require_client()
    kwargs = {"model": "whisper-1", "response_format": "verbose_json",
              "timestamp_granularities": ["segment"]}
    if language and language != "auto":
        kwargs["language"] = language

    with open(file_path, "rb") as audio_file:
        result = client.audio.transcriptions.create(file=audio_file, **kwargs)

    segments = []
    for seg in getattr(result, "segments", []) or []:
        # The SDK sometimes returns objects and sometimes plain dicts.
        start = getattr(seg, "start", None)
        text = getattr(seg, "text", None)
        if start is None and isinstance(seg, dict):
            start, text = seg.get("start"), seg.get("text")
        segments.append({"start": float(start or 0), "text": (text or "").strip()})

    return {
        "text": (getattr(result, "text", "") or "").strip(),
        "segments": segments,
        "language": getattr(result, "language", "unknown"),
        "utterances": [],
        "talk_time": {},
        "has_speakers": False,
    }


def transcribe_with_speakers(file_path):
    # AssemblyAI does the diarization for us. It's a 3-step dance: upload the
    # file, kick off a transcript job, then poll until it's done.
    headers = {"authorization": ASSEMBLYAI_KEY}

    with open(file_path, "rb") as f:
        up = requests.post("https://api.assemblyai.com/v2/upload",
                           headers=headers, data=f)
    up.raise_for_status()
    audio_url = up.json()["upload_url"]

    req = requests.post(
        "https://api.assemblyai.com/v2/transcript",
        headers=headers,
        json={"audio_url": audio_url, "speaker_labels": True},
    )
    req.raise_for_status()
    transcript_id = req.json()["id"]

    poll_url = f"https://api.assemblyai.com/v2/transcript/{transcript_id}"
    for _ in range(120):                      # give it ~4 min max
        data = requests.get(poll_url, headers=headers).json()
        if data["status"] == "completed":
            break
        if data["status"] == "error":
            raise RuntimeError("AssemblyAI error: " + data.get("error", "unknown"))
        time.sleep(2)
    else:
        raise RuntimeError("AssemblyAI timed out.")

    # Roll the utterances up into a per-speaker talk-time total.
    utterances, talk_time, segments = [], {}, []
    for u in data.get("utterances", []) or []:
        speaker = "Speaker " + str(u.get("speaker", "?"))
        start_s = (u.get("start", 0) or 0) / 1000.0
        dur_s = ((u.get("end", 0) or 0) - (u.get("start", 0) or 0)) / 1000.0
        utterances.append({"speaker": speaker, "start": start_s,
                           "text": (u.get("text") or "").strip()})
        segments.append({"start": start_s, "text": (u.get("text") or "").strip()})
        talk_time[speaker] = round(talk_time.get(speaker, 0) + dur_s, 1)

    return {
        "text": (data.get("text") or "").strip(),
        "segments": segments,
        "language": data.get("language_code", "en"),
        "utterances": utterances,
        "talk_time": talk_time,
        "has_speakers": bool(utterances),
    }


def smart_transcribe(file_path, language="auto"):
    # Use AssemblyAI if we have a key, otherwise Whisper. If AssemblyAI throws
    # for any reason we quietly fall back so the upload still works.
    if ASSEMBLYAI_KEY:
        try:
            return transcribe_with_speakers(file_path)
        except Exception as exc:
            print(f"[ai_engine] AssemblyAI failed ({exc}); using Whisper instead.")
    return transcribe_audio(file_path, language)


def detect_and_translate(text, source_language="auto"):
    # If it's already English we skip the API call entirely.
    if not text.strip():
        return text, False
    if source_language == "en":
        return text, False
    system = ("You are a professional translator. If the text is already in "
              "English, return it exactly as-is. Otherwise translate it into "
              "clear, natural English. Return ONLY the text.")
    translated = _ask_gpt_text(system, text, temperature=0.2)
    return translated, translated.strip() != text.strip()


# Filler words we strip out before sending the transcript to the model.
_FILLERS = ["um", "umm", "uh", "uhh", "erm", "hmm", "like", "you know",
            "i mean", "sort of", "kind of", "basically", "actually", "literally"]


def optimize_text(text):
    cleaned = text
    for filler in _FILLERS:
        cleaned = re.sub(rf"\b{re.escape(filler)}\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned)          # collapse whitespace
    cleaned = re.sub(r"\s+([.,!?])", r"\1", cleaned)  # no space before punctuation
    return cleaned.strip()


def _chunk_text(text, max_chars=12000):
    # Break a long transcript into word-safe chunks so we stay under the
    # model's context limit.
    words, chunks, current = text.split(), [], ""
    for word in words:
        if len(current) + len(word) + 1 > max_chars:
            chunks.append(current)
            current = ""
        current += word + " "
    if current.strip():
        chunks.append(current.strip())
    return chunks or [text]


def generate_notes(text, output_language="English"):
    # For long meetings, summarise each chunk first and feed the shorter
    # combined version to the final notes prompt.
    chunks = _chunk_text(text)
    if len(chunks) > 1:
        partials = []
        for i, chunk in enumerate(chunks, start=1):
            partials.append(_ask_gpt_text(
                "Summarize this part of a meeting transcript in a short paragraph, "
                "keeping all decisions, tasks, names and dates.",
                f"Part {i} of {len(chunks)}:\n{chunk}", temperature=0.2))
        text = "\n\n".join(partials)

    system = (
        "You are an expert meeting-notes assistant. Read the transcript and "
        f"produce clear, professional meeting notes written in {output_language}. "
        "Return a JSON object with EXACTLY these keys: "
        "tldr (a single short sentence — the whole meeting in one line), "
        "summary (string), key_points (array of strings), "
        "decisions (array of strings), "
        "action_items (array of objects: task, owner, deadline, priority), "
        "sentiment (object: label and explanation), "
        "keywords (array of 5-10 short topic strings), "
        "glossary (array of objects: term and definition — for any acronyms or "
        "technical jargon mentioned; empty array if none), "
        "attendees (array of participant names mentioned; empty array if none). "
        "For action_items: owner is the responsible person (or 'Unassigned'), "
        "deadline is any date (or 'Not specified'), priority is High/Medium/Low. "
        "sentiment.label is one of Positive, Neutral, Negative."
    )
    notes = _ask_gpt_json(system, f"Meeting transcript:\n{text}")

    # Fill in anything the model left out so the template never hits a missing key.
    notes.setdefault("tldr", "")
    notes.setdefault("summary", "")
    notes.setdefault("key_points", [])
    notes.setdefault("decisions", [])
    notes.setdefault("action_items", [])
    notes.setdefault("sentiment", {"label": "Neutral", "explanation": ""})
    notes.setdefault("keywords", [])
    notes.setdefault("glossary", [])
    notes.setdefault("attendees", [])
    return notes


def generate_title(text):
    # Called when the user leaves the title box empty.
    if not text.strip():
        return "Untitled Meeting"
    title = _ask_gpt_text(
        "Give a short, specific 3-6 word title for this meeting based on its "
        "content. Return ONLY the title, no quotes, no punctuation at the end.",
        text[:4000], temperature=0.3)
    return (title or "Untitled Meeting").strip().strip('"')[:60]


def build_chapters(segments, max_chapters=6):
    # Split the timestamped segments into a handful of groups and let the model
    # name each one. Not perfect, but good enough to show the flow of the call.
    if not segments:
        return []
    total = len(segments)
    group_size = max(1, total // max_chapters)
    chapters = []
    for i in range(0, total, group_size):
        group = segments[i:i + group_size]
        start_seconds = group[0]["start"]
        joined = " ".join(s["text"] for s in group)[:1500]
        title = _ask_gpt_text(
            "Give a very short 3-6 word title for this part of a meeting. "
            "Return ONLY the title, no quotes.", joined, temperature=0.3)
        m, s = int(start_seconds // 60), int(start_seconds % 60)
        chapters.append({"time": f"{m:02d}:{s:02d}", "title": title})
        if len(chapters) >= max_chapters:
            break
    return chapters


def sentiment_timeline(text):
    # Ask for a mood score per section so the results page can draw a line of
    # how the tone moved through the meeting. Score is -5..+5.
    if not text.strip():
        return []
    system = (
        "You analyze the emotional tone of a meeting over time. Split the "
        "transcript into up to 8 equal chronological parts. For each part return "
        "a sentiment score from -5 (very negative) to +5 (very positive). "
        "Return JSON: {\"timeline\": [{\"part\": \"Part 1\", \"score\": 0, "
        "\"label\": \"Neutral\"}, ...]}."
    )
    data = _ask_gpt_json(system, text[:12000])
    return data.get("timeline", []) if isinstance(data, dict) else []


def chat_with_meeting(transcript, question, history=None):
    # Q&A limited to a single meeting's transcript.
    _require_client()
    messages = [{"role": "system", "content":
                 ("You answer questions about a specific meeting. Use ONLY the "
                  "transcript below. If the answer is not there, say you could "
                  "not find it in the meeting.\n\nTRANSCRIPT:\n" + transcript[:15000])}]
    if history:
        messages.extend(history[-6:])           # keep a bit of context
    messages.append({"role": "user", "content": question})
    response = client.chat.completions.create(model=MODEL, messages=messages,
                                              temperature=0.3)
    return response.choices[0].message.content.strip()


def ask_across_meetings(meetings, question):
    # Same idea as chat_with_meeting, but the context is a short digest of every
    # meeting the user has, so they can ask things like "what did we decide on X".
    _require_client()
    blocks = []
    for m in meetings[:40]:                     # cap so the prompt stays sane
        notes = m.get("notes", {})
        blocks.append(
            f"MEETING: {m.get('title','Untitled')} ({m.get('created_at','')[:10]})\n"
            f"Summary: {notes.get('summary','')}\n"
            f"Decisions: {'; '.join(notes.get('decisions', []))}\n"
            f"Action items: " +
            "; ".join(a.get("task", "") for a in notes.get("action_items", []))
        )
    context = "\n\n".join(blocks) or "No meetings yet."

    system = ("You are an assistant with access to the user's past meetings "
              "below. Answer their question using this information. Mention which "
              "meeting the answer came from when useful.\n\n" + context[:15000])
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": question}],
        temperature=0.3)
    return response.choices[0].message.content.strip()


def draft_followup_email(notes):
    action_lines = "\n".join(
        f"- {a.get('task','')} (Owner: {a.get('owner','Unassigned')}, "
        f"Due: {a.get('deadline','Not specified')})"
        for a in notes.get("action_items", []))
    context = (f"Summary: {notes.get('summary','')}\n\n"
               f"Decisions: {'; '.join(notes.get('decisions', []))}\n\n"
               f"Action items:\n{action_lines}")
    system = ("You are an executive assistant. Write a clear, friendly, "
              "professional follow-up email after a meeting. Include a subject "
              "line, short intro, key decisions, and a bulleted list of action "
              "items with owners and deadlines. Keep it concise.")
    return _ask_gpt_text(system, context, temperature=0.5)


def text_to_speech(text, out_path):
    # OpenAI TTS -> mp3 on disk. Capped at 4k chars (the API limit).
    _require_client()
    resp = client.audio.speech.create(
        model="tts-1", voice="alloy", input=text[:4000] or "No summary available."
    )
    with open(out_path, "wb") as f:
        f.write(resp.content)
    return out_path
