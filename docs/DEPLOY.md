# Deploy in ~5 minutes

You'll end up with a public GitHub repo and a live dashboard URL you can drop into
your outreach.

## 1. Create the repo

```bash
cd zus-coverage
git init
git add .
git commit -m "Coverage Intelligence Console"
```

Create a new repo on GitHub named **`zus-coverage-intelligence`** (public), then:

```bash
git remote add origin https://github.com/prathikshaurs/zus-coverage-intelligence.git
git branch -M main
git push -u origin main
```

## 2. Turn on Pages

There are two ways; the included GitHub Action is the cleaner one.

**Option A — the included Action (recommended)**
1. On GitHub: **Settings → Pages → Build and deployment → Source: GitHub Actions**.
2. The workflow in `.github/workflows/pages.yml` deploys the `dashboard/` folder on
   every push to `main`. Wait for the green check under the **Actions** tab.
3. Your URL: `https://prathikshaurs.github.io/zus-coverage-intelligence/`

**Option B — classic Pages (no Action)**
GitHub Pages classic can't serve a subfolder as root, so copy the dashboard up first:

```bash
cp dashboard/index.html docs/index.html
cp dashboard/report_data.js docs/report_data.js
git add docs && git commit -m "Pages site" && git push
```

Then **Settings → Pages → Source: Deploy from a branch → main → /docs**.
Your URL: `https://prathikshaurs.github.io/zus-coverage-intelligence/`

## 3. Update the two placeholder links

In `README.md`, replace `USERNAME` in the demo link with `prathikshaurs`.

## 4. (Optional) Vercel instead

Since you already host your portfolio on Vercel: import the repo, set the
**Root Directory** to `dashboard`, framework preset **Other**, no build command.
Deploy. You'll get a `*.vercel.app` URL instantly.

---

### What to send the team

Lead with the live link, not the repo. Something like: a one-line note that you
read the Pipe Dreams posts, built a working coverage-intelligence console around
their data model, and would love feedback on where it's wrong about how coverage
actually breaks. Attach `docs/WRITEUP.md` or paste it. Repo link second, for the
people who want to read the code and tests.
