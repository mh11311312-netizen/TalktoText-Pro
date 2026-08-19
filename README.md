# 🎙️ TalkToText Pro — AI-Powered Meeting Notes Rewriter

TalkToText Pro is a web application that turns meeting **audio** into clean,
structured **meeting notes** using Generative AI. Upload (or record) a meeting,
and the app transcribes it, translates it to English if needed, cleans the text,
and uses OpenAI to produce a summary, key points, decisions, action items, and
sentiment — plus several standout features.

---

## ✨ Features

**Core (required by the project spec)**
- Audio upload (`.mp3`, `.wav`, `.m4a`, `.mp4`) **and** live in-browser recording
- Source-language selection (with auto-detect)
- Speech-to-text (OpenAI Whisper)
- Automatic translation to English
- Text & token optimization (removes filler words, chunks long transcripts)
- AI meeting notes: Summary, Key Points, Decisions, Action Items, Sentiment
- Clean, structured, responsive UI with a **live progress tracker**
- Download as **PDF** and **Word**, plus follow-up **email** draft
- Data storage (MongoDB, with automatic local-file fallback)
- **View History** of past meetings
- **Login system** (register / login, hashed passwords)

**Standout features (make this project unique)**
1. 💬 **Chat with your Meeting** — ask questions and get answers from the transcript
2. 📋 **Smart Action-Item Tracker** — task, owner, deadline, priority + checkboxes
3. ✉️ **Auto Follow-up Email** — one-click AI-drafted email
4. 📊 **Analytics Dashboard** — sentiment, keyword tags, stat cards, chart
5. ⏱️ **Topic Chapters** with timestamps
6. 🌐 **Multi-language Notes** — regenerate notes in Urdu, Arabic, Spanish, etc.
7. 🔍 **Global Search** across all your past meetings
8. 🌙 **Light / Dark mode**

---

## 🧰 Tech Stack
- **Backend:** Python + Flask
- **Frontend:** HTML5, CSS3, vanilla JavaScript, Chart.js
- **Database:** MongoDB (via `pymongo`) — falls back to a local JSON file
- **AI:** OpenAI Whisper (`whisper-1`) + GPT (`gpt-4o-mini`)
- **Exports:** `fpdf2` (PDF), `python-docx` (Word)

---

## 🚀 Setup & Run (step by step)

### 1. Prerequisites
- Install **Python 3.10 or newer** from https://python.org
- An **OpenAI API key** from https://platform.openai.com/api-keys
- (Optional) A free **MongoDB Atlas** account — the app also works without it.

### 2. Install the dependencies
Open a terminal inside the project folder and run:
```bash
pip install -r requirements.txt
```

### 3. Add your secret keys
Copy the example env file and rename the copy to `.env`:
```bash
# Windows:
copy .env.example .env
# Mac / Linux:
cp .env.example .env
```
Open `.env` and paste your real OpenAI key:
```
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxx
```
If you have a MongoDB Atlas connection string, paste it into `MONGO_URI`.
If you leave `MONGO_URI` empty, the app automatically stores data in a local
`data_store.json` file — so it still runs.

### 4. Run the app
```bash
python app.py
```
Open your browser at: **http://127.0.0.1:5000**

### 5. Use it
1. Register an account, then log in.
2. On **New Meeting**, upload an audio file (or click Record now).
3. Choose the spoken language and the notes output language.
4. Click **Generate Meeting Notes** and watch the progress bar.
5. View your notes, chat with the meeting, download PDF/Word, and more.

---

## 🧪 How to Test
- Use any short meeting recording, or record yourself speaking for ~1 minute
  saying a few decisions and tasks (e.g. *"We decided to launch on Friday.
  Ali will prepare the slides by Wednesday."*).
- After processing, check that the summary, decisions, and action items appear.
- Try the chat: ask *"What are my action items?"*

---

## 📁 Project Structure
```
talktotext-pro/
├── app.py            # Flask server + routes + background processing
├── ai_engine.py      # All OpenAI logic (transcribe, translate, notes, chat)
├── database.py       # MongoDB + local JSON fallback
├── auth.py           # register / login / sessions
├── exports.py        # PDF + Word export
├── requirements.txt  # dependencies
├── .env.example      # template for your secret keys
├── templates/        # HTML pages
└── static/           # style.css + script.js
```

---

## 📝 Assumptions
- MongoDB is optional; a local JSON file is used automatically if it is absent.
- Background jobs are stored in memory, which suits a single-user class project.
- Speaker identification (diarization) is not enabled by default because the
  Whisper API does not provide it. It can be added later using `pyannote.audio`
  or AssemblyAI if required.
- AI-generated images (if any are used in the report) must be credited, as per
  the project guidelines. No code was copied from AI tools — it is written to be
  understood and modified.

---

*Built for the Generative AI Odyssey project — "TalkToText Pro".*
