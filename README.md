# Face Recognition Attendance (Flask + OpenCV + MongoDB)

## Features

- Browser-based registration and attendance (no native popups)
- LBPH training endpoint
- Attendance stored in MongoDB
- Admin login and dashboard with CSV download

## Setup

1. Place `haarcascade_frontalface_default.xml` in project root.
2. Copy `.env.sample` → `.env`, update `MONGO_URI`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `FLASK_SECRET`.
3. Install:
