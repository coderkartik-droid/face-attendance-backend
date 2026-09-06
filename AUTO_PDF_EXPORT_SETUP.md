# Automatic Daily PDF Export Setup Guide

This guide explains how to set up automatic daily PDF export for the Face Attendance System.

## Overview

The automatic daily PDF export feature generates attendance reports for the previous day and saves them locally in the `media/Attendance Reports` folder with the format `Attendance_Report_YYYY-MM-DD.pdf`.

## Prerequisites

1. The Django backend must be running and accessible
2. The system setting must be enabled (either via Django Admin or the Flutter app)
3. The management command `auto_generate_daily_pdf` must be executable

## Enable the Feature

### Option 1: Via Django Admin
1. Access the Django Admin panel (`http://your-server:8000/admin/`)
2. Navigate to "Reports" -> "System Settings"
3. Check the "Enable Automatic Daily PDF Export" checkbox
4. Save the settings

### Option 2: Via Flutter App
1. Open the Reports screen in the Flutter app
2. Toggle the "Automatic Daily PDF Export" switch to enable
3. The setting will be saved automatically

## Schedule the Management Command

### Linux/macOS (Cron)

1. Open crontab:
   ```bash
   crontab -e
   ```

2. Add the following line to run the command at 12:00 AM (midnight) every day:
   ```bash
   0 0 * * * cd /path/to/your/backend && python manage.py auto_generate_daily_pdf >> /var/log/face_attendance_auto_pdf.log 2>&1
   ```

3. Save and exit the crontab editor

4. Verify the cron job:
   ```bash
   crontab -l
   ```

### Windows (Task Scheduler)

1. Open Task Scheduler:
   - Press `Win + R`, type `taskschd.msc`, and press Enter

2. Create a new task:
   - Click "Create Task" in the right panel
   - Name: "Face Attendance Auto PDF Export"
   - Description: "Automatically generate daily PDF attendance reports"

3. Set the trigger:
   - Go to the "Triggers" tab
   - Click "New"
   - Select "Daily"
   - Set start time to 12:00 AM
   - Click OK

4. Set the action:
   - Go to the "Actions" tab
   - Click "New"
   - Select "Start a program"
   - Program/script: `python.exe` (full path to Python executable)
   - Add arguments: `manage.py auto_generate_daily_pdf`
   - Start in: `C:\Users\hari1\FACE_ATTENDANCE\backend` (your backend directory)
   - Click OK

5. Configure other settings (optional):
   - In the "Conditions" tab, you can set conditions like "Start only if network connection is available"
   - In the "Settings" tab, you can configure retry behavior

6. Click OK to create the task

7. Test the task:
   - Right-click the task and select "Run"
   - Check the log file for output

### Docker Environment

If you're running the backend in Docker, you can use a cron container or add the command to your existing container's crontab:

1. Create a cron file (`cronjobs`):
   ```bash
   0 0 * * * cd /app && python manage.py auto_generate_daily_pdf >> /var/log/auto_pdf.log 2>&1
   ```

2. Update your Dockerfile to include cron:
   ```dockerfile
   RUN apt-get update && apt-get install -y cron
   COPY cronjobs /etc/cron.d/auto-pdf-export
   RUN chmod 0644 /etc/cron.d/auto-pdf-export
   RUN crontab /etc/cron.d/auto-pdf-export
   RUN touch /var/log/auto_pdf.log
   CMD cron && tail -f /var/log/auto_pdf.log
   ```

## Manual Testing

You can test the command manually without waiting for the scheduled time:

```bash
cd /path/to/your/backend
python manage.py auto_generate_daily_pdf
```

Expected output:
- If enabled: "Successfully generated PDF report: Attendance_Report_YYYY-MM-DD.pdf (X records for YYYY-MM-DD)"
- If disabled: "Automatic daily PDF export is DISABLED. Exiting."
- If already generated: "PDF for YYYY-MM-DD already exists (last_exported_report_date: YYYY-MM-DD). Skipping."

## Verify PDF Generation

1. Check the `media/Attendance Reports` folder
2. Look for files with the format `Attendance_Report_YYYY-MM-DD.pdf`
3. Open the PDF to verify it contains attendance data for the correct date
4. Verify that only active users are included (deleted users should not appear)

## Troubleshooting

### Command not found
- Ensure you're in the correct backend directory
- Verify Python is installed and accessible in your PATH
- Check that `manage.py` exists in the current directory

### PDF not generated
- Check that the feature is enabled in System Settings
- Verify there are attendance records for the previous day
- Check the log file for error messages
- Ensure the `media/Attendance Reports` directory has write permissions

### Wrong time zone
- The command uses Django's `TIME_ZONE` setting (default: Asia/Kolkata)
- Adjust the cron/task schedule based on your time zone requirements
- The PDF is generated for the "previous day" based on the server's local time

### Permission errors
- Ensure the user running the command has write permissions to the `media/Attendance Reports` directory
- On Linux/macOS, you may need to use `sudo` or adjust directory permissions

## File Naming Convention

The generated PDFs follow this naming pattern:
```
Attendance_Report_YYYY-MM-DD.pdf
```

Example: `Attendance_Report_2026-09-05.pdf`

## Database Tracking

The system tracks the last exported date in the `SystemSetting` model:
- `last_exported_report_date`: Stores the date of the last successfully generated report
- This prevents duplicate generation for the same date

## Safety Features

1. **Duplicate Prevention**: The system checks both the database (`last_exported_report_date`) and file system (existing PDF) to prevent duplicates
2. **Active Users Only**: Only active users (not deleted/deactivated) are included in the PDF
3. **No Data Deletion**: Attendance history is never deleted after PDF generation
4. **Error Handling**: The command logs errors and continues without crashing

## Disable the Feature

To disable automatic PDF export:
1. Uncheck the setting in Django Admin or toggle it off in the Flutter app
2. The scheduled command will continue to run but will skip PDF generation
3. You can also remove the cron job or disable the scheduled task

## Log Files

- Linux/macOS: `/var/log/face_attendance_auto_pdf.log` (or as configured in cron)
- Windows: Check Task Scheduler history or add logging to the command
- Django logs: Also available in Django's logging system under the `apps` logger

## Monitoring

Set up monitoring to ensure the scheduled task runs successfully:
- Check log files regularly
- Monitor the `media/Attendance Reports` directory for new files
- Set up alerts if the task fails to run
- Verify the `last_exported_report_date` is updated daily