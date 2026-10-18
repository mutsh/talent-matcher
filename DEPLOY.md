# Deployment (free, HTTPS included)

Both options serve the app over HTTPS with a certificate the platform issues and renews, so you never handle certificates yourself.

| | A: Streamlit Community Cloud (simplest) | B: Azure Container Apps (Docker, EU region) |
|---|---|---|
| URL | `https://<name>.streamlit.app` | `https://talent-matcher.<...>.azurecontainerapps.io` |
| Cost | Free | Monthly free grant (about 100 active hours at 0.5 vCPU / 1 GiB); $0 when scaled to zero |
| When idle | Sleeps after about 12 h | Scales to zero after a few minutes; 20–40 s to wake |
| Uses | `requirements.txt` | `Dockerfile`, the CI image build, `deploy/azure/deploy.sh` |

## 0. Put the project on GitHub
```powershell
git init
git add .
git commit -m "Talent matcher"
git branch -M main
git remote add origin https://github.com/<your-username>/talent-matcher.git
git push -u origin main
```
On every push, GitHub Actions (`.github/workflows/ci.yml`) runs the tests and a dependency vulnerability scan. On `main`, it also builds the Docker image. `.gitignore` keeps `.streamlit/secrets.toml` and `.venv` out of git; never commit a key.

## Option A: Streamlit Community Cloud
1. Go to **share.streamlit.io**, sign in with GitHub, then **Create app → Deploy a public app from GitHub**.
2. Repository: `<your-username>/talent-matcher`, branch `main`, main file `app.py`.
3. Under **Advanced settings**, choose Python **3.12** and paste this into **Secrets**:
   ```toml
   GEMINI_API_KEY = "your-key"
   ```
4. Click **Deploy**. Every later `git push` redeploys automatically. To change the key, use **⋮ → Settings → Secrets**.

## Option B: Azure Container Apps
1. **Account:** sign up at azure.microsoft.com/free, then set up **Cost Management → Budgets** at $5/month with an email alert.
2. **Image:** push to `main` and wait for the green CI run. It publishes `ghcr.io/<your-username>/talent-matcher`. On GitHub, open **Packages → talent-matcher → Package settings → Change visibility → Public**; the image contains no secrets.
3. **Deploy:** in portal.azure.com, open Cloud Shell (**>_**, Bash) and run:
   ```bash
   curl -sLO https://raw.githubusercontent.com/<your-username>/talent-matcher/main/deploy/azure/deploy.sh
   export GITHUB_USER=<your-username>
   export GEMINI_API_KEY=<your-key>
   bash deploy.sh
   ```
   It prints the live URL after 3–5 minutes.
4. **Update:** `az containerapp update -n talent-matcher -g talent-matcher-rg --image ghcr.io/<your-username>/talent-matcher:sha-xxxxxxx` (the tag is shown in the CI run summary).
5. **Remove everything:** `az group delete -n talent-matcher-rg --yes`.

| Problem | Fix |
|---|---|
| Image can't be pulled | Make the package public (step 2), or `export GHCR_TOKEN=<token with read:packages>` before the script |
| CV upload fails with 403 | `az containerapp update -n talent-matcher -g talent-matcher-rg --set-env-vars STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=false` |
| Slow first load | Normal after scale-to-zero. Before a live demo, temporarily use `--min-replicas 1` |

Why one replica: Streamlit keeps each session in server memory. A product would move the engine behind a stateless API that scales out.

## What is secured
| Layer | In place |
|---|---|
| Transport | HTTPS, managed by the platform |
| Secrets | Platform secret store, never in git |
| App | XSRF protection, error details hidden, 5 MB upload cap, telemetry off (`.streamlit/config.toml`) |
| API key | Max 10 extractions per browser session, rewordings cached; set a spending limit on the key as well |
| Container | Slim image, non-root user, health check |
| Supply chain | CI tests and `pip-audit` on every push; Dependabot weekly updates |
| Data | Synthetic only. Real CVs need SSO (e.g. Entra ID), EU hosting with a data processing agreement, encryption and audit logs |
