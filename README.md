# Fitzgerald Finance

A responsive, installable-style shared household budgeting app for manually tracking purchases, budget lines, income, and the net unassigned slush balance.

## Shared household hosting

The shared PC server, database, account setup, data import, and phone-access instructions are in [Server/README.md](Server/README.md). Start with **Start Fitzgerald Finance.cmd**, then open **http://localhost:8088**. Both household logins share one budget. Disconnected copies are connection/transfer screens only.

## Open the shared app

Start **Start Fitzgerald Finance.cmd**, then open **http://localhost:8088** on the PC. Phones connect to the same server through the Finance ngrok address. Static copies and APKs without a connection show a connection screen; they cannot create a separate account or budget. Account usernames, roles, password verifiers and financial records live in the PC database. Settings includes **Sign out**.

The first server setup creates an administrator chosen by the household; there is no default shared password. An administrator on any connected device can add members, assign roles, reset passwords, and import older device accounts. Password resets invalidate that account's other sessions and biometric credentials.

## Included features

- Weekly, monthly, annual/yearly budget lines that roll up into WTD, MTD, and YTD equivalent budgets.
- Preloaded household categories for housing, utilities, food, transportation, health, family, pets, personal spending, gifts, giving, Christmas, travel, savings, debt, work, and miscellaneous spending.
- Manually dated purchases and income entries, edit/delete flows, searchable ledgers, CSV exports, and JSON backup/restore.
- Automatic over-budget flagging and a coverage ledger that records the portion exceeding each line's cadence limit. Unbudgeted purchases are flagged until assigned to a budget line.
- Five visual themes, shared household accounts, administrator controls, and optional device biometric sign-in.
- A small offline app shell for supported browsers.

## Budget and slush accounting

A line item's amount is entered for its selected cadence. Weekly lines appear in weekly, monthly, and yearly budgets; monthly lines appear in monthly and yearly budgets; annual lines appear only in yearly budgets. Amounts roll up to longer horizons and are never divided into shorter ones. Zero-dollar lines remain visible in their eligible views. Actual spending follows the date on each transaction. The displayed slush balance is the yearly running net of prior-month income assigned to each spending month less recorded YTD outflows; tracked over-budget coverage identifies the portion of outflows that crossed a budget limit. Coverage is reported separately so those dollars are not deducted from the same net balance twice.

## Server-only storage and device transfers

The app fetches household records from the shared server and keeps working state only in memory. It does not write financial records or unsaved drafts to local storage, IndexedDB, or the offline cache. If saving fails, keep the window open and retry; closing it can discard unsaved in-memory edits. Connection preferences, username convenience metadata, session cookies and device biometric credentials can stay on the device. The offline cache contains only the static app shell. **Create server backup** writes a private snapshot on the PC. Explicit CSV reports are optional user-requested exports, not a data source.

To move older phone-only records: install the latest APK, choose **Transfer existing device accounts and data** on the connection screen (or **Settings -> Transfer old device data**), copy the private transfer code, connect, sign in with an existing server administrator, and use **Admin -> Import device data** on that phone. Confirm the server administrator password. Usernames already on the server are skipped. Imported passwords are preserved using scrypt-wrapped legacy verifiers, upgraded to the normal server verifier on successful password authentication. Passwords are never displayed to administrators.

The transfer can merge missing financial records; server versions win when IDs conflict. Original financial snapshots are archived privately under `Database/backups/device-transfers` for review. Android removes the old device account/financial storage only after the server confirms the same transfer. Until then the old data is preserved solely for transfer and never opened as an active budget. Transfer codes are sensitive; do not post them or commit them to Git.

## Source validation and APKs

The validation workflow checks budgeting, shared synchronization, account authorization and biometric authentication, plus Android compilation. The APK workflow produces a signed package when app sources change on main; `[skip apk]` skips packaging when requested.

## Calendar bills and monthly budgets

Each recurring bill automatically receives a monthly budget line (existing linked lines are retained). Use **Set amount** beside a bill in the calendar’s payment list to enter that month’s amount. Unset months start at $0, including yearly bills in their next due year. The same amount funds the budget line and is recorded when you mark the bill paid. A positive amount is required before recording payment; setting it does not itself record spending. Paid months retain their amounts.

Existing recurring amounts are migrated into the active budget month, with recorded bill payments retained for their historical months. Archived budget snapshots remain unchanged. View them using **Archived budgets** at the bottom of the Budget tab; Summary always shows the active plan.

Run the source regression checks with `node tests/bills.test.cjs`. A commit containing `[skip apk]` skips the automatic Android build; the APK workflow can still be run manually.

Calendar bill exception: a bill due in the current Sunday–Saturday week also appears in Weekly with its full entered amount, including bills due later in that week. Monthly uses the same full amount for that month. Yearly sums entered monthly amounts from January through the current month; unset months, future months, and other years do not contribute. These are amounts loaded into the budget, whether paid yet or not. Regular budget lines retain the normal horizon rollup rules.

The Summary focus panel has a **Week / Month / Year** toggle. It shows only lines labelled weekly, monthly, or annual respectively, comparing spending for that period with the line’s own saved amount. No cadence rollups are used in this panel; calendar bills appear only in Month. The heading follows the selected period. In the Yearly budget view, regular weekly and monthly lines total the periods that have started this year, using each period’s saved budget history. Future weeks and months are excluded. A line does not contribute before its first saved effective date. Annual lines show the annual allocation entered so far, and calendar lines continue to sum their entered monthly amounts YTD. Spending uses recorded transactions dated this year through today.

Cash funding uses the prior month’s income: Summary’s **MTD Net Cash** subtracts current-month spending through today from the previous full month’s recorded income. The Slush tab always shows **YTD slush balance**, accumulating income from the prior December through last month, less January-through-today spending. Current-month income is reserved for next month. Deficits reduce the total; coverage is not subtracted again. This yearly tally resets in January, funded by December income, and recalculates from recorded entries when they change.

Marking a calendar bill paid records the transaction on the local date the button is clicked. Its scheduled due date is retained separately, including in the transaction notes. Duplicate prevention follows the scheduled bill month, so paying early or late does not create duplicate payments. Existing transactions retain their recorded dates because older records do not contain the original payment date; they can be corrected using Edit in Transactions.

Ledger analysis offers **This Year** (January 1–December 31, including future-dated entries) and **All time**. Its totals, coverage and rows use that selection, with a January–December chart for This Year. Summary and Slush continue to use through-today spending calculations.

## Shared connectivity and device authentication

The Local Server Control Panel at `C:/Users/danie/Documents/Local Server Control Panel` routes the existing ngrok domain: InvestAI retains its root API/token, while Finance uses `/finance/`. **Server connectivity** on Settings and sign-in tests and saves that address per device. Shared-server biometric sign-in now uses device-held credentials; fingerprint/face templates remain with the OS. See [Server/README.md](Server/README.md). The current APK includes native shared-server support.

## Budget recurrence and category suggestions

New budget lines have Recurring / One time selection. Recurring remains the default for existing lines. A one-time line has a budget date and is allocated once, without renewing in later weeks, months, or years. Its selected weekly/monthly/annual view still controls which horizons it appears in. Historical recurring allocations remain in yearly totals when a line changes to one time; the one-time spending allowance does not reset each month.

Line names suggest a matching category. The category remains editable, and a manual choice is preserved while editing the name. Group is read-only and follows the selected category. Calendar payment cards keep full names and notes above their amount/status and action rows.

## Android system bars

The Android wrapper now reserves the reported status-bar, navigation-bar, display-cutout and keyboard insets around the WebView. It consumes those insets so the web page does not count them again. The live page suppresses CSS safe areas only when the wrapper advertises this capability; older installed wrappers retain CSS safe-area protection. Native wrapper changes require one app update; no APK is built without an explicit request.
