# TPCODL Dashboard — Cloud Setup Guide
## Render.com + GitHub Pages (fully free, no local PC needed)

---

## What you will have after this setup

```
Cron-job.org (every 2 min)
       │  HTTP GET /run
       ▼
Render.com worker  ──Selenium──►  TPCODL portal (downloads XLS)
       │  processes data
       │  git push
       ▼
GitHub repo (gh-pages branch)
       │  GitHub Pages serves automatically
       ▼
https://yourname.github.io/tpcodl-dashboard/   ← live dashboard URL
```

---

## STEP 1 — Create GitHub repository

1. Go to https://github.com → click **New repository**
2. Name it: `tpcodl-dashboard`
3. Set visibility: **Public** (required for free GitHub Pages)
4. Click **Create repository**
5. Create a branch named `gh-pages`:
   - In the repo, click **Branch: main** dropdown
   - Type `gh-pages` → click **Create branch: gh-pages**
6. Enable GitHub Pages:
   - Go to repo **Settings → Pages**
   - Source: **Deploy from a branch**
   - Branch: **gh-pages** / folder: **/ (root)**
   - Click **Save**
7. Your dashboard URL will be: `https://YOUR_GITHUB_USERNAME.github.io/tpcodl-dashboard/`

---

## STEP 2 — Create a GitHub Personal Access Token (PAT)

The script needs this to push dashboard updates to your repo.

1. Go to https://github.com/settings/tokens
2. Click **Generate new token → Fine-grained token**
3. Set name: `tpcodl-render-bot`
4. Expiration: **No expiration** (or 1 year)
5. Repository access: **Only select repositories** → choose `tpcodl-dashboard`
6. Permissions → **Contents**: Read and write
7. Click **Generate token**
8. **COPY THE TOKEN NOW** — you cannot see it again

---

## STEP 3 — Prepare your code

1. Upload these files to your GitHub repo's **main branch**:
   ```
   tpcodl-dashboard/
   ├── Dockerfile
   ├── requirements.txt
   ├── main.py              ← with generate_dashboard() pasted in
   └── render.yaml
   ```

2. **Important**: Open `main.py` and find the line:
   ```
   # >>> INSERT generate_dashboard() HERE <<<
   ```
   Paste the complete `generate_dashboard()` function from your local
   `shift_report_automation.py` there. It is identical — no changes needed.

3. Commit and push to the **main** branch.

---

## STEP 4 — Deploy on Render.com

1. Go to https://render.com → Sign up (free, use GitHub login)
2. Click **New → Web Service**
3. Connect your GitHub account → select `tpcodl-dashboard` repo
4. Render will detect `render.yaml` automatically
5. Go to **Environment** tab and add these variables:

   | Key | Value |
   |-----|-------|
   | `TPCODL_USER` | `dipti.ranjan` |
   | `TPCODL_PASS` | `Apr@202678` |
   | `GITHUB_TOKEN` | *(paste your PAT from Step 2)* |
   | `GITHUB_REPO` | `YOUR_GITHUB_USERNAME/tpcodl-dashboard` |
   | `GITHUB_BRANCH` | `gh-pages` |
   | `PUBLIC_URL` | `https://YOUR_GITHUB_USERNAME.github.io/tpcodl-dashboard/` |

6. Click **Create Web Service**
7. Render will build the Docker image (~5 minutes first time)
8. When you see **Live** status, your worker is running

---

## STEP 5 — Set up Cron-job.org (triggers every 2 minutes)

1. Go to https://cron-job.org → Sign up (free)
2. Click **Create cronjob**
3. Fill in:
   - **URL**: `https://YOUR_RENDER_APP_NAME.onrender.com/run`
     *(find this URL in Render dashboard → your service → top of page)*
   - **Schedule**: Every 2 minutes
     - Select **Custom** → set: `*/2 * * * *`
   - **Request method**: GET
4. Click **Create**

That's it. Cron-job.org will ping your Render worker every 2 minutes,
which triggers a fresh data download and pushes the updated dashboard to GitHub Pages.

---

## STEP 6 — Verify everything works

1. Open your Render service URL + `/health`:
   ```
   https://YOUR_RENDER_APP_NAME.onrender.com/health
   ```
   You should see JSON like:
   ```json
   {
     "status": "ok",
     "last_run": "2024-04-26 08:32:00",
     "job": "success",
     "dashboard": "https://yourname.github.io/tpcodl-dashboard/"
   }
   ```

2. Open your GitHub Pages URL:
   ```
   https://YOUR_GITHUB_USERNAME.github.io/tpcodl-dashboard/
   ```
   The dashboard should be live and auto-refreshing every 2 minutes.

3. Check Render logs (**Logs** tab in your Render service) — you should see
   login, download, and publish messages every 2 minutes.

---

## Free tier limits

| Service | Free limit | Impact |
|---------|-----------|--------|
| Render | 750 hrs/month web service | Enough for 24/7 if you only have 1 service |
| Render | Sleeps after 15 min inactivity | Cron-job.org keeps it awake by pinging every 2 min |
| GitHub Pages | 1 GB storage, 100 GB bandwidth/month | Dashboard is ~500 KB — no issue |
| Cron-job.org | Unlimited jobs on free tier | Fine for every-2-min schedule |

---

## Troubleshooting

**Dashboard not updating:**
- Check Render logs for errors
- Check cron-job.org → job history → look for non-200 responses
- Visit `/health` endpoint to see last run status

**Login failing on Render:**
- The TPCODL portal may be blocking server IPs
- Try changing Render region to `Oregon` or `Frankfurt`
- Check if captcha is harder on server — review logs

**GitHub push failing:**
- Verify your PAT has Contents: Read+Write permission
- Check the GITHUB_REPO value is exactly `username/tpcodl-dashboard`
- Make sure the `gh-pages` branch exists

**Build failing on Render:**
- Check Dockerfile — Chrome install sometimes needs updated apt keys
- Render build logs will show the exact error line

---

## Upgrade path (if free tier isn't enough)

- **Render Starter $7/mo** — removes sleep, faster builds
- **DigitalOcean Droplet $4/mo** — full Linux VPS, run script exactly as local
- **GitHub Actions** — free 2000 min/month, but 6 min job limit may be tight
