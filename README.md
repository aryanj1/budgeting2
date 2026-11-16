# BudgetFlow — private family budgeting dashboard

A dark Streamlit dashboard backed by Supabase for tracking how much of a ₹3,40,000 credit allocation has been used. It starts with **₹20,000 already used** and **₹3,20,000 remaining**. All future amounts update from actual transactions.

## What you get

- **Three live cards:** Total credit, credit used, credit remaining.
- **Eight-week bar chart:** Total amounts logged per Monday–Sunday week.
- **Three-column ledger:** Date, Used for, Amount used. Search, date filters, CSV export.
- **Owner mode:** Add, edit, delete transactions; change total credit or opening used amount.
- **Viewer mode:** The same live dashboard with no edit controls.
- **Protected cloud database:** Streamlit Secrets contains the elevated Supabase key. Supabase RLS plus revoked public-role grants block public API access.
- **Real Indian currency formatting**, dark theme, no fake transactions.

### Important: the ₹20,000 already used

Because you haven't supplied a dated breakdown for the existing ₹20,000, the database stores it as **opening_used** rather than inventing transaction rows. The opening amount is included in `credit used` and deducted from `credit remaining`, but **excluded** from weekly bars and the dated transaction table. If you later add an old transaction of ₹3,000, also reduce `opening_used` from ₹20,000 to ₹17,000 so you don't count it twice. The **Owner controls → Credit settings** form allows this.

---

## 1. Supabase: set up the database

1. Open **https://supabase.com/dashboard** and create a new project. Choose a project name (such as `budgetflow-family`) and strong project/database password.
2. In the project, open **SQL Editor → New query**.
3. Paste the ENTIRE contents of [`supabase_setup.sql`](supabase_setup.sql).
4. Click **Run**. This creates `budget_settings` and `usage_entries` and inserts these initial values:
   - `total_credit = 340000`
   - `opening_used = 20000`
   - `usage_entries` is empty (because the previous ₹20,000 is not itemized).
5. Open **Project Settings → API Keys** (or use the project's **Connect** panel). Copy:
   - The **Project URL** (`https://xxxxx.supabase.co`)
   - A **Secret API key**, starting with `sb_secret_...` (server-side only). Generate one if needed. **Do not use** the publishable `sb_publishable_...` key here.
6. Leave Supabase running. You do not need to manually add RLS policies, tables, or user accounts; the SQL does the required setup.

**Why use a Secret key?** It can bypass RLS, so it must stay private in the server's Secrets settings. Viewer vs. owner permissions are enforced by the Streamlit Python app, not by sharing the Supabase secret with users. Do not paste the secret key in GitHub or frontend code.

## 2. GitHub: upload code

Create a **private** GitHub repository named `budgetflow` (do **not** initialize it with a README if using the commands below). Extract the ZIP into a `budgetflow` folder.

Ensure the folder contains:

```text
budgetflow/
├── app.py
├── budget_logic.py
├── styles.css
├── supabase_setup.sql
├── requirements.txt
├── README.md
├── .gitignore
├── .streamlit/
│   ├── config.toml
│   └── secrets.toml.example
└── tests/
    └── test_budget_logic.py
```

From Terminal on your Mac, run (replace `YOUR_GITHUB_USERNAME`):

```bash
cd /path/to/budgetflow
git init
git add .
git commit -m "Initial private budget dashboard"
git branch -M main
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/budgetflow.git
git push -u origin main
```

When prompted, authenticate with GitHub through your configured credential helper or a personal access token (not your normal GitHub password). You may alternatively use GitHub Desktop to publish the folder into a private repository.

**Never commit** `.streamlit/secrets.toml`. `.gitignore` explicitly excludes it. You *can* upload `secrets.toml.example` because it contains dummy placeholders.

## 3. Streamlit Community Cloud: deploy

1. Open **https://share.streamlit.io** and sign in with your GitHub account.
2. Click **Create app → Yup, I have an app**.
3. Select repository `YOUR_GITHUB_USERNAME/budgetflow`, branch `main`, and entrypoint file **`app.py`**.
4. In **Advanced settings** (or the Secrets field), paste these **four** lines, filling them with your real values:

```toml
SUPABASE_URL = "https://YOUR-PROJECT-ID.supabase.co"
SUPABASE_SECRET_KEY = "sb_secret_YOUR_REAL_SECRET_KEY"
OWNER_PASSWORD = "MAKE_THIS_A_LONG_UNIQUE_OWNER_PASSWORD"
VIEWER_PASSWORD = "A_DIFFERENT_LONG_READ_ONLY_PASSWORD"
```

5. Choose a URL such as `budgetflow-family.streamlit.app` if available. Select a recent supported Python version (e.g. 3.12) and **Deploy**.
6. Test owner login: enter `OWNER_PASSWORD` (not the Supabase key). You should see all cards, plus **＋ Log new usage** and **Owner controls**.
7. Open the app in an incognito window and log in with `VIEWER_PASSWORD`. It should show the dashboard and CSV export, **without** the add/edit/delete controls.

Changes you push to GitHub are automatically reflected in the hosted app. Data is stored in Supabase, not in GitHub or the Streamlit app process, so it persists across reruns/redeployments.

### Share with your father safely

For family financial details, **keep the app private** in Streamlit Cloud's sharing settings. Add your father's email as an approved **viewer**. Send him the Streamlit URL and only the `VIEWER_PASSWORD`. He may need to authenticate to Streamlit Cloud first. **Never** share your `OWNER_PASSWORD` or `SUPABASE_SECRET_KEY`.

Having a private GitHub repository does not automatically grant your father permission to view the Streamlit app. Add him as a viewer in the app's Cloud sharing settings.

## 4. How to use the dashboard

### Add usage

Owner login → **＋ Log new usage** → Date used, Used for, Amount used → **Save usage**.

Example: `16 Nov 2026 | Groceries | ₹1,500`. Credit used becomes ₹21,500 and remaining becomes ₹3,18,500. The graph adds ₹1,500 to the week beginning 16 Nov 2026.

### Correct a mistake

Owner login → **Owner controls** → expand **Edit / delete transactions or change the budget** → **Edit or delete an entry**. Select a record, edit it, and save; or confirm permanent deletion.

### Change total credit / backfill the prior ₹20,000

Owner login → **Owner controls** → **Credit settings**. `Total credit` and `Opening amount already used` are editable. For historical backfills, reduce opening usage by the same total you add as dated transactions.

### Export a ledger

Select a search/date filter in Usage history, then click **Export CSV**. This file contains exactly three columns: Date, Used for, Amount used (INR).

## 5. Run locally (optional)

```bash
cd /path/to/budgetflow
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Edit .streamlit/secrets.toml with the SAME four values as Cloud Secrets.
streamlit run app.py
```

Then open the URL printed by Streamlit (usually `http://localhost:8501`).

Run unit tests:

```bash
python3 -m unittest discover -s tests -v
```

## Security and limitations

- A long, unique **owner** password is essential: this is password-based access to server-side write controls, not identity-based Supabase Auth. For family use, restrict the entire Streamlit app to you and your father through Cloud's private sharing settings as well.
- RLS is enabled with no public policies; access through a publishable key cannot read your ledger. The server Secret key has elevated access and **must never leave Streamlit Secrets**.
- The login form includes a basic 10-failed-attempts-per-session cutoff; it is **not a comprehensive rate limiter**. Streamlit private sharing provides a stronger perimeter.
- Weekly bars and transaction history only include dated `usage_entries`, not undated opening usage.
- Dates are shown in India Standard Time, and weeks are Monday–Sunday.
- Entries reflect **amounts used/taken from the family credit**; this version does not separately track cash received vs. a later expenditure. If those are distinct in your life, you would want two separate ledgers before extending this app.
- No automated data backups are included. You can export the dated transactions via CSV; consider database backups if the ledger becomes important.

## Official references

- [Streamlit deployment](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)
- [Streamlit Secrets](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management)
- [Streamlit app sharing](https://docs.streamlit.io/deploy/streamlit-community-cloud/share-your-app)
- [Supabase API keys](https://supabase.com/docs/guides/getting-started/api-keys)
