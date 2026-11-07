# Household database

`finance.sqlite3` is created automatically by `Server/main.py`. It contains household data, account password hashes, and server sessions. Do not share or commit it. Automatic daily backups are placed in `backups/` (last 14 retained). Use SQLite's backup API or the app's JSON backup when the server is running; do not copy only the live database file while its WAL is active.
