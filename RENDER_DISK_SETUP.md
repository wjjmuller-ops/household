# Render Disk Setup

This version supports Render persistent disk storage for SQLite.

## Render disk settings

In your Render Web Service:

1. Go to Settings
2. Scroll to Disks
3. Add Disk

Use:

```text
Name: household-data
Mount Path: /data
Size: 1 GB
```

## Database path

The app will automatically use:

```text
/data/household.db
```

when the `/data` folder exists on Render.

Locally it will still use:

```text
household.db
```

You can override the path with an environment variable:

```text
DATABASE_PATH=/data/household.db
```
