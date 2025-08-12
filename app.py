# app.py
import os
import io
import cv2
import base64
import numpy as np
import pandas as pd
from datetime import datetime
from flask import (
    Flask, render_template, request, jsonify, redirect, url_for, session, flash, send_file
)
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

# ---------------- Config ----------------
app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["MONGO_URI"] = os.getenv("MONGO_URI", "mongodb://localhost:27017/face_attendance")
app.secret_key = os.getenv("FLASK_SECRET", "dev-secret-key")
mongo = PyMongo(app)

# Files / dirs
BASE_DIR = os.getcwd()
DATASET_DIR = os.path.join(BASE_DIR, "dataset")
TRAINER_DIR = os.path.join(BASE_DIR, "trainer")
HAAR_PATH = os.path.join(BASE_DIR, "haarcascade_frontalface_default.xml")
TRAINER_FILE = os.path.join(TRAINER_DIR, "trainer.yml")

os.makedirs(DATASET_DIR, exist_ok=True)
os.makedirs(TRAINER_DIR, exist_ok=True)

# Ensure Haar cascade exists
if not os.path.exists(HAAR_PATH):
    raise FileNotFoundError("haarcascade_frontalface_default.xml not found in project root.")

# Ensure admin exists in DB (username/password from env or defaults)
def ensure_admin():
    username = os.getenv("ADMIN_USERNAME", "admin")
    password = os.getenv("ADMIN_PASSWORD", "admin123")
    if mongo.db.admins.find_one({"username": username}) is None:
        mongo.db.admins.insert_one({
            "username": username,
            "password": generate_password_hash(password)
        })
        print(f"[INIT] Created admin user '{username}' (change ADMIN_PASSWORD in env)")

ensure_admin()

# Load cascade
face_cascade = cv2.CascadeClassifier(HAAR_PATH)

# Global recognizer (loaded if trainer exists)
recognizer = None
def load_recognizer():
    global recognizer
    if os.path.exists(TRAINER_FILE):
        try:
            recognizer = cv2.face.LBPHFaceRecognizer_create()
            recognizer.read(TRAINER_FILE)
            print("[INFO] Loaded trainer.yml")
            return True
        except Exception as e:
            print("[WARN] Could not load trainer.yml:", e)
            recognizer = None
            return False
    recognizer = None
    return False

load_recognizer()

# ---------------- Helpers: training & dataset ----------------
def get_images_and_labels(dataset_dir=DATASET_DIR):
    face_samples = []
    ids = []
    for folder in os.listdir(dataset_dir):
        folder_path = os.path.join(dataset_dir, folder)
        if not os.path.isdir(folder_path) or "_" not in folder:
            continue
        id_part = folder.split("_", 1)[0]
        try:
            user_id = int(id_part)
        except ValueError:
            continue
        for file in os.listdir(folder_path):
            path = os.path.join(folder_path, file)
            try:
                pil = Image.open(path).convert("L")
                img_np = np.array(pil, "uint8")
            except Exception:
                continue
            faces = face_cascade.detectMultiScale(img_np)
            for (x, y, w, h) in faces:
                face_samples.append(img_np[y:y+h, x:x+w])
                ids.append(user_id)
    return face_samples, ids

def train_model():
    faces, ids = get_images_and_labels()
    if not faces or not ids:
        return False, "No training images found."
    recognizer_local = cv2.face.LBPHFaceRecognizer_create()
    recognizer_local.train(faces, np.array(ids))
    recognizer_local.save(TRAINER_FILE)
    load_recognizer()
    return True, f"Trained on {len(set(ids))} users."

def mark_attendance_db(user_id: int, name: str):
    date_str = datetime.now().strftime("%Y-%m-%d")
    time_str = datetime.now().strftime("%H:%M:%S")
    existing = mongo.db.attendance.find_one({"user_id": int(user_id), "date": date_str})
    if not existing:
        mongo.db.attendance.insert_one({
            "user_id": int(user_id),
            "name": name,
            "date": date_str,
            "time": time_str,
            "created_at": datetime.utcnow()
        })
        return True
    return False

# ---------------- Pages ----------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/register")
def register_page():
    return render_template("register.html")

@app.route("/attendance")
def attendance_page():
    return render_template("attendance.html")

# ---------------- Admin ----------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        admin = mongo.db.admins.find_one({"username": username})
        if admin and check_password_hash(admin["password"], password):
            session["admin_user"] = username
            return redirect(url_for("admin_dashboard"))
        flash("Invalid username or password", "danger")
        return redirect(url_for("admin_login"))
    return render_template("login.html")

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_user", None)
    return redirect(url_for("admin_login"))

@app.route("/admin")
def admin_dashboard():
    if not session.get("admin_user"):
        return redirect(url_for("admin_login"))
    date_filter = request.args.get("date")
    query = {}
    if date_filter:
        query["date"] = date_filter
    records = list(mongo.db.attendance.find(query, {"_id": 0}).sort([("date", -1), ("time", 1)]))
    users = list(mongo.db.users.find({}, {"_id": 0}).sort("user_id", 1))
    return render_template("admin_dashboard.html", records=records, users=users)

@app.route("/admin/download")
def admin_download():
    if not session.get("admin_user"):
        return redirect(url_for("admin_login"))
    date_filter = request.args.get("date")
    query = {}
    if date_filter:
        query["date"] = date_filter
    recs = list(mongo.db.attendance.find(query, {"_id": 0}))
    if not recs:
        flash("No records found for selected date.", "info")
        return redirect(url_for("admin_dashboard"))
    df = pd.DataFrame(recs)
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    filename = f"attendance_{date_filter or datetime.now().strftime('%Y-%m-%d')}.csv"
    return send_file(buf, as_attachment=True, download_name=filename, mimetype="text/csv")

# ---------------- API: Registration & Training ----------------
@app.route("/api/save_image", methods=["POST"])
def api_save_image():
    user_id = request.form.get("user_id", "").strip()
    user_name = request.form.get("user_name", "").strip().replace(" ", "_")
    image_data = request.form.get("image", "")
    if not user_id or not user_name or not image_data:
        return jsonify({"status": "error", "message": "Missing fields"}), 400
    try:
        user_id_int = int(user_id)
    except ValueError:
        return jsonify({"status": "error", "message": "user_id must be numeric"}), 400
    # decode image
    try:
        header, b64 = image_data.split(",", 1)
        img_bytes = base64.b64decode(b64)
        np_arr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("decode failed")
    except Exception:
        return jsonify({"status": "error", "message": "Invalid image data"}), 400
    folder = os.path.join(DATASET_DIR, f"{user_id_int}_{user_name}")
    os.makedirs(folder, exist_ok=True)
    count = len([n for n in os.listdir(folder) if n.lower().endswith((".jpg", ".png"))]) + 1
    file_path = os.path.join(folder, f"{count}.jpg")
    cv2.imwrite(file_path, img)
    # save user if not exists
    if mongo.db.users.find_one({"user_id": user_id_int}) is None:
        mongo.db.users.insert_one({"user_id": user_id_int, "name": user_name})
    return jsonify({"status": "success", "message": f"Saved image #{count}", "count": count})

@app.route("/api/train", methods=["POST"])
def api_train():
    ok, msg = train_model()
    if ok:
        return jsonify({"status": "success", "message": msg})
    return jsonify({"status": "error", "message": msg}), 400

# ---------------- API: Recognition (Attendance) ----------------
@app.route("/api/process_frame", methods=["POST"])
def api_process_frame():
    image_data = request.form.get("image", "")
    if not image_data:
        return jsonify({"status": "error", "message": "No image data"}), 400
    if recognizer is None:
        return jsonify({"status": "error", "message": "Model not trained"}), 400
    # decode
    try:
        header, b64 = image_data.split(",", 1)
        img_bytes = base64.b64decode(b64)
        np_arr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("decode failed")
    except Exception:
        return jsonify({"status": "error", "message": "Invalid image"}), 400
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5)
    if len(faces) == 0:
        return jsonify({"status": "no_face", "message": "No face detected"})
    faces = sorted(faces, key=lambda r: r[2]*r[3], reverse=True)
    (x, y, w, h) = faces[0]
    try:
        id_pred, conf = recognizer.predict(gray[y:y+h, x:x+w])
    except Exception:
        return jsonify({"status": "error", "message": "Recognition failed"})
    THRESHOLD = 50.0
    if conf < THRESHOLD:
        user_doc = mongo.db.users.find_one({"user_id": int(id_pred)})
        if user_doc:
            marked = mark_attendance_db(int(id_pred), user_doc.get("name"))
            return jsonify({
                "status": "recognized",
                "user_id": int(id_pred),
                "name": user_doc.get("name"),
                "confidence": float(conf),
                "marked": bool(marked)
            })
    return jsonify({"status": "unknown", "confidence": float(conf)})

# ---------------- API: Reports & helpers ----------------
@app.route("/api/attendance_today")
def api_attendance_today():
    date_str = datetime.now().strftime("%Y-%m-%d")
    recs = list(mongo.db.attendance.find({"date": date_str}, {"_id": 0}).sort("time", 1))
    return jsonify(recs)

@app.route("/api/users")
def api_users():
    recs = list(mongo.db.users.find({}, {"_id": 0}).sort("user_id", 1))
    return jsonify(recs)


# ---------------- Run ----------------
if __name__ == "__main__":
    app.run(debug=True)
