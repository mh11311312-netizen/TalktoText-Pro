TalkToText Pro
AI-Powered Meeting Notes Rewriter — ReadMe
About
TalkToText Pro is a web application that turns meeting audio into clean, structured meeting notes using Generative AI. Upload or record a meeting and the app transcribes it, translates it to English if needed, cleans the text, and produces a summary, key points, decisions, action items and sentiment — plus extra features like chat, analytics, audio playback and exports.
Folder structure
talktotext-pro/
  app.py            Flask server + routes + background job
  ai_engine.py      transcription, translation, notes, chat, TTS
  database.py       MongoDB with JSON fallback
  auth.py           register / login / sessions
  exports.py        PDF, Word and calendar (.ics) exports
  requirements.txt  Python dependencies
  .env.example      template for your API keys
  templates/        HTML pages
  static/           style.css + script.js
How to run
•Install Python 3.10 or newer.
•In the project folder run: pip install -r requirements.txt
•Copy .env.example to .env and add your OpenAI API key.
•Run: python app.py
•Open http://127.0.0.1:5000 and register an account.
Environment variables (.env)
•OPENAI_API_KEY — required; your OpenAI key.
•MONGO_URI — optional; a MongoDB Atlas connection string. If left blank the app stores data in a local data_store.json file.
•ASSEMBLYAI_API_KEY — optional; enables speaker diarization (the 'who spoke how much' chart).
•SECRET_KEY — any long random string for Flask sessions.
Assumptions
•The user supplies their own OpenAI API key with available credit.
•Audio is reasonably clear; noisy recordings may lower transcription accuracy.
•MongoDB is optional — a local JSON file is used automatically if no connection string is given.
•Speaker diarization is optional and only runs when an AssemblyAI key is present.
•The app is meant to run locally for this submission; background jobs are held in memory (fine for a single user).
•The analytics charts load Chart.js from a CDN, so an internet connection is needed for the charts to appear.
Tools used
Python, Flask, HTML/CSS/JavaScript, MongoDB, OpenAI (Whisper + GPT), and an optional AssemblyAI integration. Diagrams in the report were made with Graphviz. AI tools were used as a development and learning aid; the code is understood and maintained by the author.
