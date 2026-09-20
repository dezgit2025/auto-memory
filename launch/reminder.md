# Follow-up reminder

Due October 4, 2026, 10 a.m. America/New_York.
Local cron checks daily at 10 a.m. Mac local time; a due-date check and local marker make notification effectively one-time. If asleep/off, it tries at the next daily run while awake and logged in. Cron does not wake the Mac; changing timezone changes firing time. Focus/notification settings can hide notifications.

Runtime stays outside Git in Application Support. Inspect crontab -l for auto-memory-launch-followup-2026-10-04. Remove only that entry with crontab -e to uninstall. No posting, submission, or model execution. Installation status is in the [journal](progress-launch-plan.md).
