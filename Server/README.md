# Shared household server

This is the shared PC-hosted edition. The server uses Python 3.11+ and SQLite, with no extra Python packages. The database stays on this PC; phones talk to the server rather than opening the database file.

## Start and set up

1. Double-click **Start Fitzgerald Finance.cmd** in the project folder, or run `powershell -ExecutionPolicy Bypass -File .\Server\Start-Server.ps1`.
2. Open **http://localhost:8088** on this PC and click **Set up household**. Choose your own administrator username and a password of at least 12 characters. There is no shared-server default password.
3. Open **Account administration → Add household member** to create your spouse's login. Both logins use the same financial records.
4. On the old local app/device, choose **Settings → Download account backup**. In the new server-hosted app, choose **Settings → Restore account backup**. Review the replacement confirmation: this imports the shared household data for both users. Keep the original backup until verified. Accounts/passwords are not imported from financial backups.

The database is `Database/finance.sqlite3`. Source code pushes never upload it. The app has a save-status banner and polls for other-device changes every three seconds when no edit dialog is open. Independent changes merge. If both devices edit the same field, the second change stays on the device with download/reload controls; it never silently overwrites the first edit. Unsaved changes are retained in that browser until saved or explicitly discarded. Reconnect and use Retry save after a network interruption.

## Phone access at home and away (recommended)

1. Install Tailscale on this PC and both phones, and add the devices/users to your private Tailscale network. Authorize only household members.
2. On this PC, while signed into Tailscale, run `tailscale serve --bg http://127.0.0.1:8088` in an administrator terminal and approve HTTPS if prompted.
3. Or, after signing in to Tailscale, run `Server/Enable-Tailscale.ps1` to configure private Serve, enable secure cookies, and restart the finance server.
4. Open the HTTPS address printed by Tailscale on both phones, while Tailscale is connected. Sign in with each household account. Add the web page to the phone's home screen if desired. No new APK is needed.
5. If you configured Serve manually, after verifying HTTPS, set `secureCookie` to `true` in `Server/settings.json` and restart the server with Stop-Server.ps1 then Start-Server.ps1. Use the HTTPS address from then on.

Tailscale sign-in and device invitations must be completed by you. Tailscale is not installed by the server. This app is intended for private household hosting, not anonymous public internet exposure. Tailscale Serve keeps the server bound to localhost; it does not require router port forwarding. Do not publish the database or the Server directory.

For home-Wi-Fi-only access, set `host` to `0.0.0.0` in settings.json and restart. Allow the Python server on Windows Firewall **Private networks only**, then use `http://YOUR-PC-LAN-IP:8088` from a phone on the same Wi-Fi. HTTP on a LAN is not encrypted; private HTTPS via Tailscale is the preferred setup. Do not expose this port on the public router.

## Keeping it available

The PC must stay awake and connected. `Server/Enable-Startup.ps1` registers a per-user Windows task (or a per-user Startup shortcut if task registration is unavailable) to start the server when you sign in. `Server/Stop-Server.ps1` stops only the recorded server process. If the Startup shortcut was used, delete **Fitzgerald Finance Server.lnk** from your Windows Startup folder. To remove the scheduled task, run `Unregister-ScheduledTask -TaskName 'Fitzgerald Finance Server' -Confirm:$false`.

Shared-server accounts currently use password sign-in. Device-local biometric sign-in remains available only in the standalone local edition. Existing installed APKs still use their local data; use the server's browser URL for shared access.

## Backup and recovery

The server uses SQLite's backup API before saves and at startup. It keeps a dated snapshot for each of the most recent 14 backup days under `Database/backups`; the current day's snapshot is refreshed before each save. These files include account credentials/session data and must remain private. Also download periodic financial JSON backups from Settings, preferably to another drive. To restore a database snapshot, stop the server, preserve the current database and any WAL/SHM files together in a separate recovery folder, copy the selected snapshot to `Database/finance.sqlite3`, and restart. JSON restore replaces financial records but preserves shared logins.

## Verification

```
python -m unittest discover -s tests -p test_server.py
node tests/shared-client.test.cjs
node tests/bills.test.cjs
```

The static `index.html` can still be used as the original local-only app. Shared mode activates only when served by `Server/main.py`. Private API responses are never cached by the service worker, and a hosted app does not switch to a local account if the server is offline.
