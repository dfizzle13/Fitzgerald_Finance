# Fitzgerald Finance

A responsive, installable-style household budgeting app prototype for manually tracking purchases, budget lines, income, and the net unassigned slush balance.

## Run locally

Open `index.html` through a local web server. For example, run `python -m http.server 8000` in this directory and open `http://localhost:8000`. HTTPS or localhost is required for WebAuthn device-authenticator enrollment. The repository also includes a web app manifest, SVG icon, and service worker for an installable/offline app shell when hosted over HTTPS.

## First-run account

- Username: `admin`
- Password: `password`

Change this password before recording real household finances. New registrations receive the `user` role. Only an administrator can change another account's role, and the active administrator cannot change their own role. Account records and all financial data are local to the current browser profile; clearing browser storage removes them.

## Included features

- Weekly, monthly, annual/yearly budget lines that roll up into WTD, MTD, and YTD equivalent budgets.
- Preloaded household categories for housing, utilities, food, transportation, health, family, pets, personal spending, gifts, giving, Christmas, travel, savings, debt, work, and miscellaneous spending.
- Manually dated purchases and income entries, edit/delete flows, searchable ledgers, CSV exports, and JSON backup/restore.
- Automatic over-budget flagging and a coverage ledger that records the portion exceeding each line's cadence limit. Unbudgeted purchases are flagged until assigned to a budget line.
- Five visual themes, local accounts, admin role management, and optional WebAuthn platform-authenticator sign-in with forced disable after three unsuccessful assertions.
- A small offline app shell for supported browsers.

## Budget and slush accounting

A line item's amount is entered for its selected cadence. Weekly lines appear in weekly, monthly, and yearly budgets; monthly lines appear in monthly and yearly budgets; annual lines appear only in yearly budgets. Amounts roll up to longer horizons and are never divided into shorter ones. Zero-dollar lines remain visible in their eligible views. Actual spending follows the date on each transaction. The displayed slush balance is the running net of all income less all recorded outflows; tracked over-budget coverage identifies the portion of outflows that crossed a budget limit. Coverage is reported separately so those dollars are not deducted from the same net balance twice.

## Prototype security limitations

This is a local-first prototype, not a production account system. Password hashes and financial data are stored in browser local storage; client-only role controls are not a substitute for server-side authorization. Before hosting for real family use, add a backend database, strong password hashing and rate limits, secure sessions, HTTPS, access control enforced by the server, and a migration plan. WebAuthn requests device user verification, but a browser cannot guarantee whether a platform authenticator used a fingerprint/face or device PIN. For that reason biometric sign-in authenticates directly rather than retrieving or autofilling a saved plaintext password. After three unsuccessful assertions, the local biometric preference is disabled and password sign-in is required before re-enabling it.

## Deploy with GitHub Pages

The workflow in `.github/workflows/pages.yml` publishes the static app when pushed to `main`. In the repository settings, set **Pages → Build and deployment → Source** to **GitHub Actions** if it is not already selected. WebAuthn requires HTTPS on the deployed origin. Storage is isolated by browser and device; accounts do not synchronize between devices.

## Calendar bills and monthly budgets

Each recurring bill automatically receives a monthly budget line (existing linked lines are retained). Use **Set amount** beside a bill in the calendar’s payment list to enter that month’s amount. Unset months start at $0, including yearly bills in their next due year. The same amount funds the budget line and is recorded when you mark the bill paid. A positive amount is required before recording payment; setting it does not itself record spending. Paid months retain their amounts.

Existing recurring amounts are migrated into the active budget month, with recorded bill payments retained for their historical months. Archived budget snapshots remain unchanged. View them using **Archived budgets** at the bottom of the Budget tab; Summary always shows the active plan.

Run the source regression checks with `node tests/bills.test.cjs`. A commit containing `[skip apk]` skips the automatic Android build; the APK workflow can still be run manually.
