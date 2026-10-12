# Scheduled backups

StudyTracker uses SQLite's online backup API to create a consistent snapshot while the application is running.

Open **Settings > Scheduled backup** to enable automatic backups. Available intervals are 6 hours, 12 hours, daily, and weekly. The default is daily. The default destination is a `backups` directory next to the configured SQLite database. The default retention is 14 generations.

Only files matching `study_tracker_backup_*.sqlite3` in the configured destination are eligible for cleanup. Older matching files are removed only after a new backup succeeds; unrelated files are left untouched.

The dialog's **Back up now** action uses the current directory and retention inputs without saving the other settings. Backup file names include a timestamp. Restore only after closing StudyTracker, and keep a separate copy of the current database before replacing it.