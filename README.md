# Lunchbox Arcade — Python edition

A starter multiplayer browser arcade. The backend is Python (Flask + Flask-SocketIO). No Node.js and no VS Code required.

## Easiest way to work on it: GitHub in your browser

1. Download and extract the ZIP.
2. Sign in to GitHub in your browser and create a new repository, for example `lunchbox-arcade`.
3. On the repository page, use **Add file → Upload files**.
4. Upload the project files and folders, preserving this layout:
   - `app.py`
   - `requirements.txt`
   - `render.yaml`
   - `templates/index.html`
   - `static/client.js`
   - `static/styles.css`
5. Commit the files.
6. In Render, create a new Web Service and connect the repository. Render can also use `render.yaml` to set up the service.
7. If configuring manually:
   - Runtime: Python
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn --worker-class gthread --threads 100 --bind 0.0.0.0:$PORT app:app`
8. Deploy and open the generated `onrender.com` URL.

## No local editor required

You can make changes using GitHub's browser-based file editor or upload replacement files, then commit. Render automatically redeploys after commits when connected to the repository.

## Optional local test

If Python is installed and you want to test locally, use a terminal in this folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Then open http://localhost:10000. This is optional; you can deploy from the browser without using VS Code.

## Features

- Python server and Flask-SocketIO live multiplayer
- Create/join private rooms with five-character codes
- 2–8 players per room
- Host-controlled Reaction Race with round results
- Responsive homepage with additional game ideas
- `/health` endpoint

## Limitations of this first version

- Rooms live in server memory and are cleared on a server restart.
- No accounts or permanent leaderboards yet.
- Render's free web services may spin down while inactive.
- The first version uses one process and is intended for a small private hobby project.
