# Lunchbox Arcade

A small multiplayer browser arcade. The backend uses Python, Flask and Flask-SocketIO. No Node.js or local code editor is required.

## Games

- **Reaction Race:** click after the screen turns green. The lowest reaction time wins.
- **Knockout:** move with WASD or the arrow keys and push players off a shrinking circular platform. Mobile users can use the on-screen controls.

Both games support 2–8 players in a private room. The host chooses the game and starts the round.

## Updating the existing GitHub repository

If you already deployed an earlier Lunchbox Arcade version, replace these four files using GitHub in your browser:

1. `app.py` (repository root)
2. `templates/index.html` (inside `templates`)
3. `static/client.js` (inside `static`)
4. `static/styles.css` (inside `static`)

For each file, open the matching folder in your GitHub repository, choose **Add file → Upload files**, and upload the replacement file from this ZIP. Commit the changes. If GitHub asks you to confirm replacing an existing file, confirm it. Render should deploy the commit automatically if auto-deploy is enabled; otherwise use **Manual Deploy → Deploy latest commit**.

Keep `requirements.txt` and `render.yaml` from the existing project; they do not need to change for this update.

## Render settings

- Runtime: Python
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn --worker-class gthread --threads 100 --bind 0.0.0.0:$PORT app:app`

## Notes

- Rooms are stored in server memory and disappear when the service restarts.
- This starter is intended for a small private group on one running server instance.
- Free Render services may spin down while idle.
