# Shared household server

The PC hosts SQLite and shared accounts. Phones use the HTTPS server; the database stays on this PC. Python 3.11+ and the pinned dependency in requirements.txt are required.

## Start

1. Install once: `python -m venv Server/.venv`, then `Server/.venv/Scripts/python -m pip install -r Server/requirements.txt`.
2. Double-click **Start Fitzgerald Finance.cmd**, then open **http://localhost:8088**.
3. First-time households choose **Set up household** and their own administrator username/password (12+ characters). Existing households keep their logins/data. There is no shared default password.
4. Use **Account administration -> Add household member** for a spouse. Both accounts share the same financial records.

The database is `Database/finance.sqlite3`, excluded from Git. Financial JSON import replaces household records after confirmation but preserves shared accounts/passwords. Independent device edits merge; conflicting changes remain recoverable on the second device with download/reload controls. Failed saves never silently overwrite another device's changes. Unsaved edits remain in browser storage until resolved.

## Shared ngrok access

The Local Server Control Panel lives at `C:/Users/danie/Documents/Local Server Control Panel`. It routes one ngrok domain through loopback port 9000. InvestAI keeps its existing root API and token; Finance uses `/finance/`. Both backends stay on loopback (InvestAI 8765, Finance 8088). No router forwarding is needed. The PC must stay awake and online.

Open the Finance HTTPS address on each phone, or use **Settings -> Server connectivity -> Configure server** (also on sign-in). Paste the ngrok domain with `/finance/`, choose **Test connection**, then **Save & connect**. The app checks Finance's identity first. Only the device stores this address; household backups do not include connection preferences. If the server is unavailable, the app does not silently switch to local data.

The gateway validates the original origin, scopes Finance cookies to `/finance/`, and adds Secure on public HTTPS. Keep `secureCookie` false for direct localhost HTTP. Management controls and database files are not exposed by the gateway.

## Device-local biometric sign-in

Sign in with a password, then enable biometrics in Settings and confirm that password. Enable separately on each device and account. Fingerprint/face templates stay with the device OS and never enter the household database.

Browser sign-in uses verified WebAuthn challenges: private keys stay with the platform authenticator, while the server stores public credential information. Browsers may offer device PIN verification. The updated Android source encrypts a random sign-in credential with an authentication-per-use Android Keystore key; only encrypted data remains in device preferences, and Android backup is disabled. The server retains a hash, expiring after 90 days. Password changes revoke device credentials. Password sign-in remains available.

Existing installed APKs need a future rebuild for the native connection settings and encrypted vault. No APK is produced for this update. Hosted HTTPS browsers can use WebAuthn now.

## Startup, backups, recovery

`Server/Enable-Startup.ps1` starts Finance when Windows signs in; `Server/Stop-Server.ps1` stops only its recorded process. The central panel starts missing enabled services and leaves healthy existing processes alone. Closing the panel leaves services running.

SQLite backup snapshots are saved at startup and before writes, retaining the latest 14 backup days under `Database/backups`. These contain credentials/session data and must stay private. Also download financial JSON backups from Settings to another drive. To restore SQLite: stop Finance, preserve the current database plus WAL/SHM files in a recovery folder, copy the selected snapshot to `Database/finance.sqlite3`, then restart. JSON restore preserves shared logins.

## Verification

```
Server/.venv/Scripts/python -m unittest discover -s tests -p 'test_*.py'
node tests/device-client.test.cjs
node tests/shared-client.test.cjs
node tests/bills.test.cjs
```

The static index remains a standalone local edition; shared mode activates only through Server/main.py. Private API responses are never cached. The legacy local-edition account notes in the root README do not describe shared-server authentication.
