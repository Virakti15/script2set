# Script2Set manual deployment

This setup keeps the static browser application on Netlify and runs the private Flask API on Render. Text AI keys stay on Render. Projects and optional uploaded reference images are stored in SQLite on a mounted persistent disk. No image-generation API or image key is required. Nothing has been deployed by this handoff.

## 1. Put the project on GitHub

Run these commands from the `script2set` directory. If the directory already belongs to a Git repository, skip `git init` and use that repository's normal branch workflow.

```bash
git init
git add .
git commit -m "Prepare Script2Set for manual deployment"
git branch -M main
git remote add origin https://github.com/YOUR-ACCOUNT/YOUR-REPOSITORY.git
git push -u origin main
```

Confirm that `.env`, `data/`, `frontend-dist/`, SQLite files, and provider keys do not appear in the GitHub repository. `.env.example` contains names and safe defaults only.

## 2. Deploy the Flask backend on Render

1. In Render, choose **New > Blueprint** and connect the GitHub repository.
2. The simplest path is to push this `script2set` directory as the repository root. For a larger repository, select the Blueprint file path and add the service's `rootDir` in `render.yaml` to point to the directory containing `app.py`.
3. Review the `script2set-api` service. The Blueprint uses Python 3.12, installs `requirements.txt`, runs `python app.py`, checks `/health`, and mounts a 1 GB disk at `/var/data/script2set`.
4. Keep a single Render instance while using the SQLite disk. A mounted Render disk attaches to one service instance.
5. Enter the secret environment values described below and create the service.

The included Waitress server reads Render's `PORT`, binds to `0.0.0.0`, and does not depend on a Windows path. `DATA_DIR=/var/data/script2set` keeps saved projects and image bytes on the mounted disk. Render files outside that path are temporary.

You can also create a Web Service manually with:

- Runtime: `Python 3`
- Root directory: the directory containing `app.py`
- Build command: `pip install -r requirements.txt`
- Start command: `python app.py`
- Health check: `/health`
- Persistent disk mount: `/var/data/script2set`
- Disk size: 1 GB or more

## 3. Configure backend environment variables

Set these in Render. Never add their real values to Netlify or GitHub.

| Variable | Required | Value |
| --- | --- | --- |
| `APP_ENV` | Yes | `production` |
| `HOST` | Yes | `0.0.0.0` |
| `DATA_DIR` | Yes | `/var/data/script2set` |
| `SECRET_KEY` | Yes | A long random value; the Blueprint can generate it |
| `APP_ACCESS_PASSWORD` | Yes | A private workspace password |
| `FRONTEND_ORIGINS` | Yes | Exact Netlify origin, such as `https://your-site.netlify.app`; comma-separate additional exact HTTPS origins |
| `AI_PROVIDER` | Yes | `openai` for hosted AI; `demo` is the labelled offline rules mode |
| `OPENAI_API_KEY` | For hosted AI | Backend API key |
| `OPENAI_MODEL` | For hosted AI | A text model available to the API project that can return JSON objects |
| `OPENAI_BASE_URL` | Optional | Defaults to `https://api.openai.com/v1`; use only an HTTPS provider base URL |
| `AI_TIMEOUT` | Optional | Text provider timeout in seconds; default `90` |
| `IMAGE_PROVIDER` | Default supplied | Keep `none`; manual uploads and placeholders work without an image key |

`AI_PROVIDER=ollama` remains available for local development. The backend rejects Ollama in production so a deployed service never silently depends on localhost.

After Render reports the service healthy, open:

```text
https://YOUR-RENDER-SERVICE.onrender.com/health
```

Expected fields include `"status":"ok"`, `"environment":"production"`, and the configured text provider name. This endpoint does not reveal secrets.

## 4. Deploy the frontend on Netlify

1. In Netlify, choose **Add new project > Import an existing project** and connect the same GitHub repository.
2. Set the base directory to the directory containing `netlify.toml` if this is a monorepo.
3. Keep the build command and publish directory from `netlify.toml`: `node scripts/build_frontend.mjs` and `frontend-dist`.
4. Add a Netlify build environment variable named `PUBLIC_API_BASE_URL`. Set it to the Render origin, for example `https://your-api.onrender.com`. It is public configuration, not a secret.
5. Deploy the site.

The build validates that `PUBLIC_API_BASE_URL` is an HTTPS origin without credentials, paths, query strings, or localhost. It copies the existing frontend, writes the public API origin to `static/config.js`, adds the `/print` rewrite, and emits security headers whose `connect-src` allows only the configured backend.

After Netlify assigns the final site URL, return to Render and set `FRONTEND_ORIGINS` to that exact origin. Do not use `*`. Redeploy or restart the Render service after changing environment variables.

## 5. Post-deployment checks

Use a private test project and perform these checks in order:

1. Open the Netlify URL and sign in with `APP_ACCESS_PASSWORD`.
2. Confirm the footer reports the cloud workspace and the provider label reports the configured cloud AI provider.
3. Open the Render `/health` URL and confirm HTTP 200.
4. Paste a short script with two scenes. Generate a shot plan and confirm the interface does not label the result as an offline preview.
5. Review and approve the plan. Confirm the production breakdown retains screenplay order and the 19 production columns.
6. Export Excel. Resolve any blocking source, dialogue, numbering, framing, or required-field errors. Review the assumption warnings before confirming the download.
7. Compare every scene and dialogue line with the original script. Check the three-row metadata block, colored scene bands and all 19 columns. Unknown production details require human confirmation. VISUALS may be empty.
8. Optionally upload a JPEG, PNG, or WebP reference in Storyboard and approve it. A grouped range uses one representative frame. Approved current images appear in Excel VISUALS and PPT; no image generation is required.
9. Change that shot. Confirm the older frame remains visible as outdated and no longer counts as approved.
10. Choose **Save to server**, reload the site, choose **Restore**, and confirm the project and approved frame return.
11. Download Excel and verify the `SHOT` column stores ranges as text. Download CSV and open Print view.
12. Export both Storyboard PPT layouts. Confirm approved current images appear on their shots and missing, unapproved, or outdated images use placeholders.

If generation fails, inspect the Render logs for the status class only. The application deliberately hides provider response bodies and keys from browser errors. HTTP 503 commonly indicates missing credentials, exhausted credits, or an unreachable provider; HTTP 504 indicates the configured provider timeout.

The offline regression suite needs no API credentials: `python -m pytest -q`. Install `requirements-dev.txt` first. Run `python tests/verify_accuracy_exports.py` with the project directory on `PYTHONPATH` to regenerate the three review samples. These samples use explicitly labelled offline rules; they do not establish live cloud model quality. Complete steps 4–7 using your actual cloud model before using the application on a production shoot.

## 6. Backups and updates

Download project JSON copies for production backups. Render snapshots the persistent disk, but the single-workspace SQLite store is intended for one service instance. For multi-user access or horizontal scaling, move projects and image assets to managed database/object storage before adding instances.

For updates, push the tested commit to GitHub. Render and Netlify can rebuild from that branch. Keep the same `SECRET_KEY`; changing it invalidates active login and plan-approval signatures, so users will need to sign in and approve plans again.

Configuration references: [Netlify file-based builds](https://docs.netlify.com/build/configure-builds/file-based-configuration/), [Render Blueprint specification](https://render.com/docs/blueprint-spec), and [Render persistent disks](https://render.com/docs/disks).
