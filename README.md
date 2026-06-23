# Haus Invictus — guest guide

A self-contained guest guide for Haus Invictus. One source builds two things:

- **`docs/index.html`** — the public web page (single self-contained file). This is what GitHub Pages serves. Private details (door code, Wi-Fi password, address, phone) are automatically hidden here.
- **`private/welcome-guide.pdf`** — a print-ready A5 booklet with the **real** private details. Never published — deliver it to guests privately (Airbnb message / email).

## Publish it (free, public repo)

1. Create a GitHub account, then **New repository** → name it → **Public** → Create.
2. On the repo page, choose **"uploading an existing file"** and drag in everything from this folder. Commit.
3. **Settings → Pages → Build and deployment → Source → "GitHub Actions."**
4. Watch the **Actions** tab for a green check. The site goes live at `https://<your-username>.github.io/<repo>`.

Nothing sensitive is in this repo, so a public repo is safe.

## Update the guide later

Edit any file in `content/` right on GitHub (pencil icon) and commit. The included
workflow rebuilds and redeploys the site automatically in about a minute.

## Where the private values live

Real secrets are **not** in this repo. They sit in `secrets.local.yaml`
(git-ignored) and are merged in only when building locally. Keep a copy of that
file somewhere safe (e.g. a password manager). The public site never contains them.

## Custom domain (when you're ready)

Set `domain:` in `site.yaml` (e.g. `invictus-experience.com`), rebuild, then in
**Settings → Pages** enter the domain and add the DNS records your registrar needs
(four A records to GitHub's IPs, plus a `www` CNAME). Finally tick **Enforce HTTPS**.

## Build locally (optional)

```
pip install -r requirements.txt
python build.py
```

Needs `secrets.local.yaml` present to put the real details into the PDF.
