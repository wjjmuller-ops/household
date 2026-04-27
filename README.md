# Household Web App v2

## New in this version

- Login screen with username and password
- User roles:
  - Admin: full access and can delete anything
  - User: can delete only what they created
- Default first admin user:
  - Username: `admin`
  - Password: `admin123`
- Admin-only user management
- Full monthly calendar on the home page
- Selectable calendar dates
- Delete buttons for events, comments, shopping items, tasks, and users
- Existing SQLite database support with automatic upgrade from v1

## Run locally

```bash
pip install -r requirements.txt
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

## Important

For a fresh test, delete `household.db` if it already exists.

Default login:

```text
Username: admin
Password: admin123
```

After login, go to Users and create your household users with either `admin` or `user` role.

## Later Render start command

```text
gunicorn app:app
```


## v3 Notifications Added

This version adds a Notifications page and browser popup notifications.

Included:
- Enable browser notifications
- Test notification button
- Event reminders for events starting within 30 minutes
- Overdue to-do reminders
- Assigned task reminders data endpoint
- Notification checks run every 60 seconds while the app is open

Note:
This is the first notification version. It works while the web app is open in the browser.
The next version can add PWA/service-worker background notifications.


## v3.1 Notification Test Fix

If the test notification does not show:
- Use `http://127.0.0.1:5000` locally.
- Do not use your computer's LAN IP address unless HTTPS is enabled.
- Check browser site permissions.
- Check Windows Focus Assist / Do Not Disturb.


## v4 Feature Batch Added

Added before PWA work:
- Edit events
- Event descriptions / notes
- Edit shopping items
- Shopping categories
- Edit to-do tasks
- To-do status: Pending, In Progress, Done
- Household notice board on dashboard
- Admin can edit/delete everything
- Normal users can edit/delete only what they created


## v5 Big Upgrade

Added:
- Search and filters for events, shopping, and to-do list
- Dashboard cards for today, overdue tasks, and this week
- Stronger dashboard panels
- Recurring tasks: None, Daily, Weekly, Monthly
- Auto-create next recurring task when marked Done
- Mobile quick-add buttons
- Better mobile calendar layout
- Shopping filters by category/status
- To-do filters by status/responsible user/priority


## v5.1 Compact Layout Polish

- Tighter dashboard spacing
- Shorter calendar cells
- Smaller cards and buttons
- Better desktop proportions
- Collapsed notice form
- Compact list items
- Improved one-screen fit


## v5.2 Dashboard Fixed

- Rebuilt dashboard.html cleanly
- Removed sidebar sections: Overdue Tasks, This Week, Shopping, To-do
- Kept Notice Board and Selected Date only
- Fixed orphan Jinja `{% else %}` error


## v6 PWA Version

Added:
- `manifest.json`
- Service worker
- App icons
- Offline page
- Install App button
- Service-worker notification display
- Cache support for app shell

Important:
- Install and notifications work best on HTTPS.
- Local testing works on `http://127.0.0.1:5000`.
- Phone install from another device requires HTTPS, so deploy to Render or another HTTPS host.
- This version uses app-open reminder checks. Full closed-app push notifications require a push server.
