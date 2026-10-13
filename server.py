#!/usr/bin/env python3
"""
Projects Tracker (Python + SQLite + Vanilla JS / React-style UI)
- Backend: Python http.server with REST API endpoints & Role-Based Auth (Manager & User)
- Database: SQLite with users and projects relational tables
- Zero external dependencies: 100% Python standard library
"""

import sys
import math
import http.server
import socketserver
import json
import sqlite3
import os
import urllib.parse
import hashlib
import secrets
from html import escape as html_escape

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PORT = int(os.environ.get("PORT", 5050))
DB_FILE = os.path.join(os.path.dirname(__file__), "database.db")
socketserver.TCPServer.allow_reuse_address = True

# In-memory session store: token -> user dict
SESSIONS = {}

def hash_password(password: str) -> str:
    salt = "projects_tracker_salt_v1"
    return hashlib.sha256(f"{salt}_{password}".encode("utf-8")).hexdigest()

# -------------------------------------------------------------
# SQL Database Setup & Migration (SQLite)
# -------------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # 1. Create Users Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT CHECK(role IN ('manager', 'user')) NOT NULL DEFAULT 'user',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 2. Seed default Manager if users table is empty
    cursor.execute("SELECT COUNT(*) FROM users;")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT INTO users (username, email, password_hash, full_name, role)
        VALUES (?, ?, ?, ?, ?)
        """, (
            "aadityaa",
            "aadityaarwork@gmail.com",
            hash_password("123456"),
            "Aadityaa R",
            "manager"
        ))
        conn.commit()

    # 3. Create Projects Table (empty by default)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        description TEXT,
        technology TEXT NOT NULL,
        status TEXT DEFAULT 'In Progress',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    conn.commit()
    conn.close()

init_db()

# -------------------------------------------------------------
# Auth Helper
# -------------------------------------------------------------
def get_auth_user(headers):
    auth_header = headers.get("Authorization", "")
    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    if not token:
        cookie_header = headers.get("Cookie", "")
        for part in cookie_header.split(";"):
            part = part.strip()
            if part.startswith("auth_token="):
                token = part.split("=", 1)[1]
                break
    if token and token in SESSIONS:
        return token, SESSIONS[token]
    return None, None

# -------------------------------------------------------------
# HTTP Request Handler
# -------------------------------------------------------------
class RequestHandler(http.server.BaseHTTPRequestHandler):
    def _send_json(self, status_code, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path

            if path == "/" or path == "/index.html":
                self.serve_app()
            elif path == "/api/auth/me":
                _, user = get_auth_user(self.headers)
                if not user:
                    self._send_json(401, {"error": "Not authenticated"})
                else:
                    self._send_json(200, {"user": user})
            elif path == "/api/users":
                _, user = get_auth_user(self.headers)
                if not user:
                    self._send_json(401, {"error": "Authentication required"})
                    return
                conn = sqlite3.connect(DB_FILE)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT id, username, email, full_name, role FROM users ORDER BY full_name ASC")
                users_list = [dict(r) for r in cursor.fetchall()]
                conn.close()
                self._send_json(200, users_list)
            elif path == "/api/projects":
                _, user = get_auth_user(self.headers)
                if not user:
                    self._send_json(401, {"error": "Authentication required"})
                    return

                conn = sqlite3.connect(DB_FILE)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                params = urllib.parse.parse_qs(parsed.query)
                q = params.get("q", [""])[0].strip()
                tech = params.get("tech", [""])[0].strip()
                user_filter = params.get("user_id", [""])[0].strip()

                if user["role"] == "manager":
                    # Manager can view all user data, sorted by name!
                    sql = """
                    SELECT p.*, u.full_name as owner_name, u.role as owner_role
                    FROM projects p
                    LEFT JOIN users u ON p.user_id = u.id
                    WHERE 1=1
                    """
                    args = []
                    if q:
                        sql += " AND (p.name LIKE ? OR p.description LIKE ? OR u.full_name LIKE ?)"
                        pattern = f"%{q}%"
                        args.extend([pattern, pattern, pattern])
                    if tech and tech != "All":
                        sql += " AND p.technology = ?"
                        args.append(tech)
                    if user_filter and user_filter != "All":
                        sql += " AND p.user_id = ?"
                        args.append(int(user_filter))
                    # Managers view all user data sorted by name
                    sql += " ORDER BY u.full_name ASC, p.id DESC"
                    cursor.execute(sql, args)
                else:
                    # Regular user can only view their own data
                    sql = """
                    SELECT p.*, u.full_name as owner_name, u.role as owner_role
                    FROM projects p
                    LEFT JOIN users u ON p.user_id = u.id
                    WHERE p.user_id = ?
                    """
                    args = [user["id"]]
                    if q:
                        sql += " AND (p.name LIKE ? OR p.description LIKE ?)"
                        pattern = f"%{q}%"
                        args.extend([pattern, pattern])
                    if tech and tech != "All":
                        sql += " AND p.technology = ?"
                        args.append(tech)
                    sql += " ORDER BY p.id DESC"
                    cursor.execute(sql, args)

                rows = [dict(row) for row in cursor.fetchall()]
                conn.close()
                self._send_json(200, rows)

            elif path == "/api/stats":
                _, user = get_auth_user(self.headers)
                if not user:
                    self._send_json(401, {"error": "Authentication required"})
                    return

                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()

                if user["role"] == "manager":
                    cursor.execute("SELECT COUNT(*) FROM projects")
                    total = cursor.fetchone()[0]
                    cursor.execute("SELECT status, COUNT(*) as cnt FROM projects GROUP BY status ORDER BY cnt DESC")
                    status_counts = dict(cursor.fetchall())
                    cursor.execute("SELECT technology, COUNT(*) as cnt FROM projects GROUP BY technology ORDER BY cnt DESC")
                    tech_counts = dict(cursor.fetchall())
                    cursor.execute("""
                    SELECT u.full_name, COUNT(p.id) as cnt
                    FROM users u
                    LEFT JOIN projects p ON p.user_id = u.id
                    GROUP BY u.id
                    ORDER BY cnt DESC
                    """)
                    user_counts = dict(cursor.fetchall())
                    conn.close()
                    self._send_json(200, {
                        "total": total,
                        "by_status": status_counts,
                        "by_tech": tech_counts,
                        "by_user": user_counts
                    })
                else:
                    cursor.execute("SELECT COUNT(*) FROM projects WHERE user_id = ?", (user["id"],))
                    total = cursor.fetchone()[0]
                    cursor.execute("SELECT status, COUNT(*) as cnt FROM projects WHERE user_id = ? GROUP BY status ORDER BY cnt DESC", (user["id"],))
                    status_counts = dict(cursor.fetchall())
                    cursor.execute("SELECT technology, COUNT(*) as cnt FROM projects WHERE user_id = ? GROUP BY technology ORDER BY cnt DESC", (user["id"],))
                    tech_counts = dict(cursor.fetchall())
                    conn.close()
                    self._send_json(200, {
                        "total": total,
                        "by_status": status_counts,
                        "by_tech": tech_counts
                    })
            else:
                self.send_error(404, "Not Found")
        except Exception as e:
            print(f"Server error on GET {self.path}: {e}")
            try:
                self.send_error(500, f"Server Error: {e}")
            except Exception:
                pass

    def do_POST(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path

            if path == "/api/auth/login":
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length).decode("utf-8")
                data = json.loads(body)

                login_identifier = data.get("username", "").strip()
                password = data.get("password", "").strip()

                conn = sqlite3.connect(DB_FILE)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                # Accept login by either email or username
                cursor.execute("""
                SELECT id, username, email, full_name, role, password_hash
                FROM users
                WHERE username = ? OR email = ?
                """, (login_identifier, login_identifier))
                row = cursor.fetchone()
                conn.close()

                if row and row["password_hash"] == hash_password(password):
                    token = secrets.token_hex(24)
                    user_info = {
                        "id": row["id"],
                        "username": row["username"],
                        "email": row["email"],
                        "full_name": row["full_name"],
                        "role": row["role"]
                    }
                    SESSIONS[token] = user_info
                    self._send_json(200, {"token": token, "user": user_info})
                else:
                    self._send_json(401, {"error": "Invalid email/username or password"})
                return

            elif path == "/api/auth/logout":
                token, _ = get_auth_user(self.headers)
                if not token:
                    content_length = int(self.headers.get("Content-Length", 0))
                    if content_length > 0:
                        body = self.rfile.read(content_length).decode("utf-8")
                        try:
                            token = json.loads(body).get("token")
                        except Exception:
                            pass
                if token and token in SESSIONS:
                    del SESSIONS[token]
                self._send_json(200, {"success": True, "message": "Logged out successfully"})
                return

            elif path == "/api/projects":
                _, user = get_auth_user(self.headers)
                if not user:
                    self._send_json(401, {"error": "Authentication required"})
                    return

                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length).decode("utf-8")
                data = json.loads(body)

                name = data.get("name", "").strip()
                desc = data.get("description", "").strip()
                tech = data.get("technology", "Python").strip()

                if not name:
                    self._send_json(400, {"error": "Project name is required"})
                    return

                # Target user assignment: managers can assign to any user; regular users are forced to themselves
                if user["role"] == "manager":
                    assigned_uid = int(data.get("user_id") or user["id"])
                else:
                    assigned_uid = user["id"]

                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()

                # Find lowest sequential ID starting from 1 (reuse deleted IDs)
                cursor.execute("SELECT id FROM projects ORDER BY id ASC")
                existing_ids = {row[0] for row in cursor.fetchall()}
                next_id = 1
                while next_id in existing_ids:
                    next_id += 1

                cursor.execute("""
                INSERT INTO projects (id, user_id, name, description, technology, status)
                VALUES (?, ?, ?, ?, ?, 'In Progress')
                """, (next_id, assigned_uid, name, desc, tech))
                cursor.execute("UPDATE sqlite_sequence SET seq = (SELECT COALESCE(MAX(id), 0) FROM projects) WHERE name = 'projects'")
                
                # Fetch assignee name
                cursor.execute("SELECT full_name, role FROM users WHERE id = ?", (assigned_uid,))
                user_row = cursor.fetchone()
                owner_name = user_row[0] if user_row else "Unknown"
                owner_role = user_row[1] if user_row else "user"

                conn.commit()
                conn.close()

                self._send_json(201, {
                    "id": next_id,
                    "user_id": assigned_uid,
                    "owner_name": owner_name,
                    "owner_role": owner_role,
                    "name": name,
                    "description": desc,
                    "technology": tech,
                    "status": "In Progress",
                    "message": "Project created successfully"
                })
                return

            else:
                self.send_error(404, "Not Found")
        except Exception as e:
            print(f"Server error on POST {self.path}: {e}")
            try:
                self.send_error(500, f"Server Error: {e}")
            except Exception:
                pass

    def do_PUT(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path

            if path.startswith("/api/projects/"):
                _, user = get_auth_user(self.headers)
                if not user:
                    self._send_json(401, {"error": "Authentication required"})
                    return

                project_id = int(path.split("/")[-1])
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()

                # Check project existence and ownership
                cursor.execute("SELECT user_id FROM projects WHERE id = ?", (project_id,))
                p_row = cursor.fetchone()
                if not p_row:
                    conn.close()
                    self._send_json(404, {"error": "Project not found"})
                    return

                current_owner_id = p_row[0]
                # Regular user cannot edit another user's project
                if user["role"] == "user" and current_owner_id != user["id"]:
                    conn.close()
                    self._send_json(403, {"error": "Forbidden: You can only edit your own projects"})
                    return

                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length).decode("utf-8")
                data = json.loads(body)

                name = data.get("name", "").strip()
                desc = data.get("description", "").strip()
                tech = data.get("technology", "Python").strip()
                status = data.get("status", "In Progress").strip()

                if not name:
                    conn.close()
                    self._send_json(400, {"error": "Project name is required"})
                    return

                # If manager, can reassign user
                if user["role"] == "manager" and "user_id" in data:
                    new_owner_id = int(data["user_id"])
                else:
                    new_owner_id = current_owner_id

                cursor.execute("""
                UPDATE projects
                SET name = ?, description = ?, technology = ?, status = ?, user_id = ?
                WHERE id = ?
                """, (name, desc, tech, status, new_owner_id, project_id))

                cursor.execute("SELECT full_name, role FROM users WHERE id = ?", (new_owner_id,))
                user_row = cursor.fetchone()
                owner_name = user_row[0] if user_row else "Unknown"
                owner_role = user_row[1] if user_row else "user"

                conn.commit()
                conn.close()

                self._send_json(200, {
                    "id": project_id,
                    "user_id": new_owner_id,
                    "owner_name": owner_name,
                    "owner_role": owner_role,
                    "name": name,
                    "description": desc,
                    "technology": tech,
                    "status": status,
                    "message": "Project updated successfully"
                })
            else:
                self.send_error(404, "Not Found")
        except ValueError:
            self._send_json(400, {"error": "Invalid project ID"})
        except Exception as e:
            self._send_json(500, {"error": str(e)})

    def do_DELETE(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path

            if path.startswith("/api/projects/"):
                _, user = get_auth_user(self.headers)
                if not user:
                    self._send_json(401, {"error": "Authentication required"})
                    return

                project_id = int(path.split("/")[-1])
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()

                # Check project existence and ownership
                cursor.execute("SELECT user_id FROM projects WHERE id = ?", (project_id,))
                p_row = cursor.fetchone()
                if not p_row:
                    conn.close()
                    self._send_json(404, {"error": "Project not found"})
                    return

                current_owner_id = p_row[0]
                if user["role"] == "user" and current_owner_id != user["id"]:
                    conn.close()
                    self._send_json(403, {"error": "Forbidden: You can only delete your own projects"})
                    return

                cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
                cursor.execute("UPDATE sqlite_sequence SET seq = (SELECT COALESCE(MAX(id), 0) FROM projects) WHERE name = 'projects'")
                conn.commit()
                conn.close()
                self._send_json(200, {"message": f"Project {project_id} deleted successfully"})
            else:
                self.send_error(404, "Not Found")
        except ValueError:
            self._send_json(400, {"error": "Invalid project ID"})
        except Exception as e:
            self._send_json(500, {"error": str(e)})

    def serve_app(self):
        html_content = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Projects Tracker</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    body { background: #120e24; color: #f5f3ff; min-height: 100vh; padding: 2rem 1rem; }
    .container { max-width: 960px; margin: 0 auto; }
    
    /* Header Styles */
    header {
      margin-bottom: 2rem;
      border-bottom: 1px solid #2e264f;
      padding-bottom: 1.5rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 1rem;
    }
    h1 { font-size: 1.85rem; font-weight: 700; color: #c084fc; letter-spacing: -0.02em; }
    .header-user-status {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      font-size: 0.85rem;
      color: #c4b5fd;
      margin-top: 0.25rem;
    }
    .user-profile-bar {
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }
    .user-pill {
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      background: #1c1735;
      border: 1px solid #3b3263;
      padding: 0.4rem 0.85rem;
      border-radius: 9999px;
      font-size: 0.85rem;
    }
    .role-badge {
      font-size: 0.7rem;
      font-weight: 800;
      padding: 0.15rem 0.5rem;
      border-radius: 0.25rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    .role-badge.manager {
      background: linear-gradient(135deg, #9333ea, #7c3aed);
      color: #ffffff;
      box-shadow: 0 0 10px rgba(147, 51, 234, 0.4);
    }
    .role-badge.user {
      background: linear-gradient(135deg, #0284c7, #0369a1);
      color: #ffffff;
    }
    .btn-logout {
      background: rgba(239, 68, 68, 0.15);
      border: 1px solid rgba(239, 68, 68, 0.35);
      color: #fca5a5;
      padding: 0.4rem 0.9rem;
      border-radius: 0.5rem;
      font-size: 0.85rem;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s;
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
    }
    .btn-logout:hover {
      background: #ef4444;
      color: #ffffff;
      border-color: #ef4444;
      box-shadow: 0 0 12px rgba(239, 68, 68, 0.3);
    }

    /* Auth Screen Styles */
    #auth-screen {
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 75vh;
      padding: 1rem;
    }
    .auth-card {
      background: #1c1735;
      border: 1px solid #3b3263;
      border-radius: 1rem;
      padding: 2.25rem;
      width: 100%;
      max-width: 440px;
      box-shadow: 0 12px 40px rgba(0, 0, 0, 0.5);
      position: relative;
    }
    .auth-header {
      text-align: center;
      margin-bottom: 1.75rem;
    }
    .auth-icon-badge {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 56px;
      height: 56px;
      border-radius: 50%;
      background: rgba(168, 85, 247, 0.15);
      border: 1px solid #7c3aed;
      font-size: 1.75rem;
      margin-bottom: 0.75rem;
    }
    .auth-header h2 {
      font-size: 1.5rem;
      color: #f5f3ff;
      font-weight: 700;
    }
    .auth-header p {
      font-size: 0.85rem;
      color: #a79fc2;
      margin-top: 0.35rem;
    }
    .auth-alert {
      background: rgba(239, 68, 68, 0.15);
      border: 1px solid #ef4444;
      color: #fca5a5;
      padding: 0.75rem 1rem;
      border-radius: 0.5rem;
      font-size: 0.85rem;
      margin-bottom: 1.25rem;
      display: none;
    }

    /* Main View Option Tabs (Projects vs Projects Distribution) */
    .main-view-switcher {
      display: flex;
      gap: 0.75rem;
      margin-bottom: 1.5rem;
      background: #1c1735;
      padding: 0.4rem;
      border-radius: 0.75rem;
      border: 1px solid #2e264f;
      box-shadow: 0 4px 18px rgba(0, 0, 0, 0.3);
    }
    .main-view-btn {
      flex: 1;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 0.65rem;
      padding: 0.75rem 1rem;
      background: transparent;
      border: none;
      border-radius: 0.5rem;
      color: #a79fc2;
      font-size: 0.95rem;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s ease;
    }
    .main-view-btn:hover {
      background: #241c42;
      color: #f5f3ff;
    }
    .main-view-btn.active {
      background: #7c3aed;
      color: #ffffff;
      box-shadow: 0 2px 10px rgba(124, 58, 237, 0.4);
    }
    .main-view-badge {
      background: #2e264f;
      color: #c084fc;
      font-size: 0.78rem;
      padding: 0.15rem 0.55rem;
      border-radius: 9999px;
      font-weight: 700;
      transition: all 0.2s;
    }
    .main-view-btn.active .main-view-badge {
      background: rgba(255, 255, 255, 0.25);
      color: #ffffff;
    }
    .view-panel {
      animation: fadeInView 0.25s ease-out;
    }
    @keyframes fadeInView {
      from { opacity: 0; transform: translateY(6px); }
      to { opacity: 1; transform: translateY(0); }
    }

    /* Cards & Form Elements */
    .card {
      background: #1c1735;
      border: 1px solid #2e264f;
      border-radius: 0.75rem;
      padding: 1.5rem;
      margin-bottom: 2rem;
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
    }
    .tab-btn {
      padding: 0.6rem 1rem;
      background: #141029;
      border: 1px solid #3b3263;
      border-radius: 0.5rem;
      color: #a79fc2;
      font-weight: 600;
      font-size: 0.9rem;
      cursor: pointer;
      transition: all 0.2s;
    }
    .tab-btn:hover { background: #241c42; color: #f5f3ff; }
    .tab-btn.active {
      background: #7c3aed;
      color: #ffffff;
      border-color: #a855f7;
      box-shadow: 0 2px 8px rgba(124, 58, 237, 0.35);
    }
    .form-group { margin-bottom: 1rem; }
    label { display: block; font-size: 0.85rem; font-weight: 600; margin-bottom: 0.35rem; color: #c4b5fd; }
    input, select, textarea {
      width: 100%;
      padding: 0.65rem 0.85rem;
      background: #120e24;
      border: 1px solid #3b3263;
      border-radius: 0.5rem;
      color: #f5f3ff;
      font-size: 0.95rem;
      outline: none;
      transition: border-color 0.2s;
    }
    input:focus, select:focus, textarea:focus { border-color: #c084fc; box-shadow: 0 0 0 2px rgba(192, 132, 252, 0.2); }
    .btn-primary {
      background: #7c3aed;
      color: #ffffff;
      border: none;
      padding: 0.65rem 1.25rem;
      border-radius: 0.5rem;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s;
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
    }
    .btn-primary:hover { background: #6d28d9; transform: translateY(-1px); }
    .btn-danger {
      background: rgba(239, 68, 68, 0.15);
      border: 1px solid rgba(239, 68, 68, 0.4);
      color: #fca5a5;
      padding: 0.35rem 0.7rem;
      border-radius: 0.35rem;
      font-size: 0.8rem;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s;
    }
    .btn-danger:hover { background: #ef4444; color: #ffffff; border-color: #ef4444; }

    /* Table & Controls */
    .table-container { overflow-x: auto; margin-top: 1rem; border-radius: 0.5rem; border: 1px solid #2e264f; }
    table { width: 100%; border-collapse: collapse; text-align: left; }
    th, td { padding: 0.85rem 1rem; border-bottom: 1px solid #2e264f; font-size: 0.9rem; }
    th { background: #16122d; color: #c4b5fd; font-weight: 600; }
    tr:hover { background: #201a3d; }
    .badge {
      display: inline-block;
      padding: 0.2rem 0.6rem;
      border-radius: 9999px;
      font-size: 0.75rem;
      font-weight: 600;
    }
    .badge-python { background: #581c87; color: #d8b4fe; border: 1px solid #7e22ce; }
    .badge-sql { background: #78350f; color: #fde68a; border: 1px solid #b45309; }
    .badge-react { background: #164e63; color: #a5f3fc; border: 1px solid #0891b2; }
    .badge-fullstack { background: #831843; color: #fbcfe8; border: 1px solid #be185d; }
    .badge-user-owner {
      background: #241c42;
      color: #e9d5ff;
      border: 1px solid #4c3a7a;
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
    }
    .badge-user-owner.manager-owner {
      border-color: #9333ea;
      color: #d8b4fe;
    }
    .status-badge {
      display: inline-block;
      padding: 0.15rem 0.5rem;
      border-radius: 0.25rem;
      font-size: 0.75rem;
      font-weight: 600;
      background: #141029;
      color: #94a3b8;
      border: 1px solid #3b3263;
    }

    /* Controls Bar: Search, Tech Sort Dropdown & Manager User Filter */
    .controls-bar {
      display: flex;
      gap: 0.75rem;
      margin-bottom: 1rem;
      align-items: center;
      flex-wrap: wrap;
    }
    .search-box-wrapper {
      position: relative;
      flex: 1;
      min-width: 220px;
    }
    .search-input {
      padding-left: 2.2rem;
      padding-right: 2rem;
    }
    .search-icon {
      position: absolute;
      left: 0.75rem;
      top: 50%;
      transform: translateY(-50%);
      color: #a79fc2;
      pointer-events: none;
    }
    .clear-search-btn {
      position: absolute;
      right: 0.65rem;
      top: 50%;
      transform: translateY(-50%);
      background: transparent;
      border: none;
      color: #a79fc2;
      cursor: pointer;
      font-size: 0.9rem;
      display: none;
    }

    /* Dropdown Menus */
    .dropdown-container {
      position: relative;
    }
    .btn-dropdown {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      background: #141029;
      border: 1px solid #3b3263;
      padding: 0.65rem 0.95rem;
      border-radius: 0.5rem;
      color: #f5f3ff;
      font-size: 0.9rem;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s;
    }
    .btn-dropdown:hover {
      background: #241c42;
      border-color: #a855f7;
    }
    .dropdown-menu {
      position: absolute;
      top: calc(100% + 0.35rem);
      right: 0;
      background: #1c1735;
      border: 1px solid #3b3263;
      border-radius: 0.5rem;
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
      min-width: 180px;
      z-index: 50;
      display: none;
      padding: 0.35rem;
    }
    .dropdown-menu.show { display: block; }
    .dropdown-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      width: 100%;
      padding: 0.5rem 0.75rem;
      background: transparent;
      border: none;
      border-radius: 0.35rem;
      color: #a79fc2;
      font-size: 0.85rem;
      cursor: pointer;
      transition: all 0.15s;
      text-align: left;
    }
    .dropdown-item:hover { background: #282147; color: #f5f3ff; }
    .dropdown-item.active { background: #7c3aed; color: #ffffff; }

    /* Pie Chart / Analytics Styles */
    .chart-layout {
      display: flex;
      align-items: center;
      justify-content: space-around;
      gap: 1.5rem;
      flex-wrap: wrap;
      padding: 0.5rem 0;
    }
    .chart-tab-btn {
      padding: 0.4rem 0.85rem;
      border-radius: 0.35rem;
      font-size: 0.8rem;
      font-weight: 600;
      border: 1px solid #3b3263;
      background: #120e24;
      color: #a79fc2;
      cursor: pointer;
      transition: all 0.2s;
    }
    .chart-tab-btn:hover { background: #1c1735; color: #f5f3ff; border-color: #c084fc; }
    .chart-tab-btn.active {
      background: #7c3aed;
      color: white;
      border-color: #a855f7;
      box-shadow: 0 0 8px rgba(168, 85, 247, 0.3);
    }
    .chart-legend-container {
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
      min-width: 250px;
      max-width: 320px;
    }
    .legend-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0.55rem 0.8rem;
      background: #120e24;
      border: 1px solid #2e264f;
      border-radius: 0.5rem;
      cursor: pointer;
      transition: all 0.2s;
    }
    .legend-item:hover { background: #241c42; border-color: #a855f7; transform: translateX(3px); }
    .legend-left { display: flex; align-items: center; gap: 0.65rem; }
    .legend-rank { font-size: 0.72rem; font-weight: 700; color: #c084fc; background: #282147; padding: 0.15rem 0.45rem; border-radius: 0.25rem; min-width: 24px; text-align: center; }
    .legend-color-dot { width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }
    .legend-label { font-weight: 600; font-size: 0.88rem; color: #e9d5ff; }
    .legend-right { display: flex; align-items: center; gap: 0.65rem; }
    .legend-value { font-weight: 700; font-size: 0.92rem; color: #f5f3ff; }
    .legend-percent { font-size: 0.78rem; color: #a79fc2; background: #0c0919; padding: 0.15rem 0.45rem; border-radius: 0.3rem; min-width: 44px; text-align: right; }
    .pie-slice { transition: opacity 0.2s, transform 0.2s; cursor: pointer; }
    .pie-slice:hover { opacity: 0.85; filter: drop-shadow(0 0 6px rgba(192, 132, 252, 0.5)); }
  </style>
</head>
<body>
  <div class="container">
    
    <!-- AUTHENTICATION SCREEN (LOGIN) -->
    <div id="auth-screen">
      <div class="auth-card">
        <div class="auth-header">
          <div class="auth-icon-badge">🔐</div>
          <h2>Projects Tracker</h2>
          <p>Sign in to access your projects workspace</p>
        </div>

        <div id="auth-error-msg" class="auth-alert"></div>

        <form id="login-form">
          <div class="form-group">
            <label for="login-username">Email or Username</label>
            <input type="text" id="login-username" placeholder="aadityaarwork@gmail.com" required autocomplete="username">
          </div>
          <div class="form-group">
            <label for="login-password">Password</label>
            <input type="password" id="login-password" placeholder="••••••••" required autocomplete="current-password">
          </div>
          <button type="submit" id="btn-login-submit" class="btn-primary" style="width: 100%; justify-content: center; padding: 0.75rem; margin-top: 0.5rem;">
            🚀 Sign In
          </button>
        </form>
      </div>
    </div>

    <!-- MAIN APP SCREEN (WHEN LOGGED IN) -->
    <div id="app-screen" style="display: none;">
      <header>
        <div>
          <h1>Projects Tracker</h1>
          <div class="header-user-status" id="header-user-status">
            <!-- Dynamic role description -->
          </div>
        </div>
        <div class="user-profile-bar">
          <div class="user-pill">
            <span id="user-avatar-icon">👤</span>
            <span id="user-full-name-display" style="font-weight: 600;">User</span>
            <span id="user-role-badge" class="role-badge">Role</span>
          </div>
          <button type="button" id="btn-logout" class="btn-logout" title="Sign out of account">
            🚪 Log Out
          </button>
        </div>
      </header>

      <!-- Main View Switcher: Projects vs Projects Distribution -->
      <div class="main-view-switcher" role="tablist">
        <button
          type="button"
          id="btn-view-records"
          class="main-view-btn active"
          role="tab"
          aria-selected="true"
          aria-controls="panel-live-records"
        >
          <span>📋 Projects</span>
          <span class="main-view-badge" id="tab-records-count">0</span>
        </button>
        <button
          type="button"
          id="btn-view-distribution"
          class="main-view-btn"
          role="tab"
          aria-selected="false"
          aria-controls="panel-projects-distribution"
        >
          <span>📊 Projects Distribution</span>
        </button>
      </div>

      <!-- View Panel 1: Projects (Live Database Records) -->
      <div id="panel-live-records" class="view-panel" style="display: block;">
        
        <!-- Management Card: Add / Edit -->
        <div class="card">
          <div style="display: flex; gap: 0.5rem; margin-bottom: 1.25rem; border-bottom: 1px solid #2e264f; padding-bottom: 0.75rem;">
            <button type="button" id="tab-add" class="tab-btn active" style="flex: 1;">
              ➕ Add New Project
            </button>
            <button type="button" id="tab-edit" class="tab-btn" style="flex: 1;">
              ✏️ Edit Existing Project
            </button>
          </div>

          <!-- Add Project Form -->
          <form id="project-form">
            <!-- Assignee Selector (Shown for Managers) -->
            <div class="form-group" id="form-group-add-user" style="display: none;">
              <label for="proj-user-add">👤 Assign To User</label>
              <select id="proj-user-add"></select>
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
              <div class="form-group">
                <label for="proj-name">Project Name *</label>
                <input type="text" id="proj-name" placeholder="e.g. Authentication Service" required>
              </div>
              <div class="form-group">
                <label for="proj-tech">Technology</label>
                <select id="proj-tech">
                  <option value="Python">Python</option>
                  <option value="SQL">SQL</option>
                  <option value="React">React</option>
                  <option value="Fullstack">Fullstack</option>
                </select>
              </div>
            </div>
            <div class="form-group">
              <label for="proj-desc">Description</label>
              <textarea id="proj-desc" rows="2" placeholder="Brief project summary..."></textarea>
            </div>
            <button type="submit" id="btn-submit" class="btn-primary">
              💾 Save to SQLite Database
            </button>
          </form>

          <!-- Edit Project Form -->
          <form id="edit-form" style="display: none;">
            <div class="form-group">
              <label for="edit-select">Select Project to Modify</label>
              <select id="edit-select">
                <option value="">No projects available</option>
              </select>
            </div>
            <!-- Assignee Selector for Edit (Shown for Managers) -->
            <div class="form-group" id="form-group-edit-user" style="display: none;">
              <label for="edit-user">👤 Assigned User</label>
              <select id="edit-user"></select>
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
              <div class="form-group">
                <label for="edit-name">Project Name *</label>
                <input type="text" id="edit-name" required>
              </div>
              <div class="form-group">
                <label for="edit-tech">Technology</label>
                <select id="edit-tech">
                  <option value="Python">Python</option>
                  <option value="SQL">SQL</option>
                  <option value="React">React</option>
                  <option value="Fullstack">Fullstack</option>
                </select>
              </div>
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
              <div class="form-group">
                <label for="edit-status">Status</label>
                <select id="edit-status">
                  <option value="In Progress">In Progress</option>
                  <option value="Completed">Completed</option>
                  <option value="On Hold">On Hold</option>
                  <option value="Planned">Planned</option>
                </select>
              </div>
              <div class="form-group">
                <label for="edit-desc">Description</label>
                <textarea id="edit-desc" rows="2"></textarea>
              </div>
            </div>
            <button type="submit" id="btn-update" class="btn-primary" style="background: #9333ea;">
              ✏️ Update Record in SQLite
            </button>
          </form>
        </div>

        <!-- Projects Table Section -->
        <div class="card">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; flex-wrap: wrap; gap: 0.75rem;">
            <h2 id="projects-table-title">Projects (SQL SELECT)</h2>
            <span style="font-size: 0.85rem; color: #a79fc2;" id="record-counter">Showing 0 records</span>
          </div>

          <!-- Controls: Search + Tech Sort Dropdown + Manager User Filter -->
          <div class="controls-bar">
            <!-- Search Input -->
            <div class="search-box-wrapper">
              <span class="search-icon">🔍</span>
              <input type="text" id="search-input" class="search-input" placeholder="Search by name, description, or user...">
              <button type="button" id="clear-search-btn" class="clear-search-btn">✕</button>
            </div>

            <!-- Technology Filter Dropdown -->
            <div class="dropdown-container">
              <button type="button" id="btn-sort-toggle" class="btn-dropdown">
                <span id="sort-dropdown-label">🏷️ Tech: All</span>
                <span style="font-size: 0.7rem;">▼</span>
              </button>
              <div id="sort-dropdown-menu" class="dropdown-menu">
                <!-- Dynamically filled -->
              </div>
            </div>

            <!-- Manager-Only User Filter Dropdown -->
            <div class="dropdown-container" id="user-filter-wrapper" style="display: none;">
              <button type="button" id="btn-user-filter-toggle" class="btn-dropdown" style="border-color: #7c3aed;">
                <span id="user-filter-label">👥 User: All</span>
                <span style="font-size: 0.7rem;">▼</span>
              </button>
              <div id="user-filter-dropdown-menu" class="dropdown-menu">
                <!-- Dynamically filled -->
              </div>
            </div>
          </div>

          <!-- Table -->
          <div class="table-container">
            <table>
              <thead>
                <tr>
                  <th style="width: 55px;">ID</th>
                  <th>Project Name</th>
                  <th>Description</th>
                  <th>Technology</th>
                  <th>Status</th>
                  <th id="th-owner-column" style="display: none;">Assigned User</th>
                  <th style="width: 80px;">Action</th>
                </tr>
              </thead>
              <tbody id="projects-tbody">
                <tr><td colspan="7" style="text-align: center; color: #a79fc2; padding: 2rem;">No projects found in database.</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- View Panel 2: Projects Distribution (Pie Chart) -->
      <div id="panel-projects-distribution" class="view-panel" style="display: none;">
        <div class="card">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.25rem; flex-wrap: wrap; gap: 0.75rem;">
            <div>
              <h2 id="chart-card-title">Projects Distribution</h2>
              <p style="font-size: 0.85rem; color: #a79fc2; margin-top: 0.2rem;" id="chart-card-subtitle">
                Interactive distribution of database records sorted by count
              </p>
            </div>
            <!-- Category Tabs -->
            <div style="display: flex; gap: 0.4rem; background: #120e24; padding: 0.25rem; border-radius: 0.5rem; border: 1px solid #2e264f;">
              <button type="button" class="chart-tab-btn active" data-chart-group="technology" id="tab-chart-tech">
                Technology
              </button>
              <button type="button" class="chart-tab-btn" data-chart-group="status" id="tab-chart-status">
                Status
              </button>
              <button type="button" class="chart-tab-btn" data-chart-group="user" id="tab-chart-user" style="display: none;">
                By User
              </button>
            </div>
          </div>

          <div class="chart-layout">
            <div style="position: relative; width: 260px; height: 260px; display: flex; align-items: center; justify-content: center;">
              <svg id="pie-chart-svg" width="260" height="260" viewBox="0 0 260 260">
                <!-- SVG Slices rendered here -->
              </svg>
            </div>
            <div id="pie-chart-legend" class="chart-legend-container">
              <!-- Legend items rendered here -->
            </div>
          </div>

          <div style="margin-top: 1.5rem; border-top: 1px solid #2e264f; padding-top: 1rem; display: flex; justify-content: flex-end;">
            <button type="button" id="btn-chart-goto-records" class="btn-primary" style="font-size: 0.85rem;">
              📋 View in Projects Table →
            </button>
          </div>
        </div>
      </div>

    </div>
  </div>

  <script>
    // State Variables
    let currentUser = null;
    let authToken = localStorage.getItem('projects_tracker_token') || null;
    let allProjects = [];
    let allUsers = [];
    let selectedTech = 'All';
    let selectedUserFilter = 'All';
    let searchQuery = '';
    let currentChartGroup = 'technology';

    // Palette for charts and badges
    const palette = {
      'Python': '#8b5cf6',
      'SQL': '#f59e0b',
      'React': '#06b6d4',
      'Fullstack': '#ec4899',
      'Completed': '#10b981',
      'In Progress': '#f59e0b',
      'On Hold': '#ef4444',
      'Planned': '#8b5cf6',
      'Aadityaa R': '#a855f7'
    };
    const fallbackColors = ['#8b5cf6', '#f59e0b', '#06b6d4', '#ec4899', '#10b981', '#3b82f6', '#a855f7', '#14b8a6'];

    // DOM Elements
    const authScreen = document.getElementById('auth-screen');
    const appScreen = document.getElementById('app-screen');
    const loginForm = document.getElementById('login-form');
    const loginUsername = document.getElementById('login-username');
    const loginPassword = document.getElementById('login-password');
    const authErrorMsg = document.getElementById('auth-error-msg');
    const btnLogout = document.getElementById('btn-logout');

    const headerUserStatus = document.getElementById('header-user-status');
    const userAvatarIcon = document.getElementById('user-avatar-icon');
    const userFullNameDisplay = document.getElementById('user-full-name-display');
    const userRoleBadge = document.getElementById('user-role-badge');

    const btnViewRecords = document.getElementById('btn-view-records');
    const btnViewDistribution = document.getElementById('btn-view-distribution');
    const tabRecordsCount = document.getElementById('tab-records-count');
    const panelLiveRecords = document.getElementById('panel-live-records');
    const panelProjectsDistribution = document.getElementById('panel-projects-distribution');

    const tabAdd = document.getElementById('tab-add');
    const tabEdit = document.getElementById('tab-edit');
    const projectForm = document.getElementById('project-form');
    const editForm = document.getElementById('edit-form');
    const editSelect = document.getElementById('edit-select');
    const editName = document.getElementById('edit-name');
    const editDesc = document.getElementById('edit-desc');
    const editTech = document.getElementById('edit-tech');
    const editStatus = document.getElementById('edit-status');
    const formGroupAddUser = document.getElementById('form-group-add-user');
    const formGroupEditUser = document.getElementById('form-group-edit-user');
    const projUserAdd = document.getElementById('proj-user-add');
    const editUser = document.getElementById('edit-user');

    const projectsTableTitle = document.getElementById('projects-table-title');
    const thOwnerColumn = document.getElementById('th-owner-column');
    const recordCounter = document.getElementById('record-counter');
    const searchInput = document.getElementById('search-input');
    const clearSearchBtn = document.getElementById('clear-search-btn');
    const btnSortToggle = document.getElementById('btn-sort-toggle');
    const sortDropdownMenu = document.getElementById('sort-dropdown-menu');
    const sortDropdownLabel = document.getElementById('sort-dropdown-label');
    const userFilterWrapper = document.getElementById('user-filter-wrapper');
    const btnUserFilterToggle = document.getElementById('btn-user-filter-toggle');
    const userFilterDropdownMenu = document.getElementById('user-filter-dropdown-menu');
    const userFilterLabel = document.getElementById('user-filter-label');
    const projectsTbody = document.getElementById('projects-tbody');

    const tabChartTech = document.getElementById('tab-chart-tech');
    const tabChartStatus = document.getElementById('tab-chart-status');
    const tabChartUser = document.getElementById('tab-chart-user');
    const pieChartSvg = document.getElementById('pie-chart-svg');
    const pieChartLegend = document.getElementById('pie-chart-legend');

    // -------------------------------------------------------------
    // Authentication Functions
    // -------------------------------------------------------------
    async function login(username, password) {
      authErrorMsg.style.display = 'none';
      try {
        const res = await fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, password })
        });
        const data = await res.json();
        if (!res.ok) {
          throw new Error(data.error || 'Login failed');
        }
        authToken = data.token;
        currentUser = data.user;
        localStorage.setItem('projects_tracker_token', authToken);
        showApp();
      } catch (err) {
        authErrorMsg.textContent = '⚠️ ' + err.message;
        authErrorMsg.style.display = 'block';
      }
    }

    async function logout() {
      try {
        if (authToken) {
          await fetch('/api/auth/logout', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': 'Bearer ' + authToken
            }
          });
        }
      } catch (e) {
        console.error('Logout error:', e);
      } finally {
        authToken = null;
        currentUser = null;
        localStorage.removeItem('projects_tracker_token');
        showAuth();
      }
    }

    async function checkExistingAuth() {
      if (!authToken) {
        showAuth();
        return;
      }
      try {
        const res = await fetch('/api/auth/me', {
          headers: { 'Authorization': 'Bearer ' + authToken }
        });
        if (res.ok) {
          const data = await res.json();
          currentUser = data.user;
          showApp();
        } else {
          authToken = null;
          localStorage.removeItem('projects_tracker_token');
          showAuth();
        }
      } catch (err) {
        showAuth();
      }
    }

    function showAuth() {
      authScreen.style.display = 'flex';
      appScreen.style.display = 'none';
      loginUsername.value = '';
      loginPassword.value = '';
      authErrorMsg.style.display = 'none';
    }

    function showApp() {
      authScreen.style.display = 'none';
      appScreen.style.display = 'block';

      // Update Header with User Info & Role
      userFullNameDisplay.textContent = currentUser.full_name;
      if (currentUser.role === 'manager') {
        userAvatarIcon.textContent = '👑';
        userRoleBadge.textContent = 'Manager';
        userRoleBadge.className = 'role-badge manager';
        headerUserStatus.innerHTML = `<span>👑</span> <span>Logged in as <strong>${currentUser.full_name}</strong> (Manager) • Viewing all user records sorted by name</span>`;
        projectsTableTitle.textContent = 'Projects (All Users — Sorted by Name)';
        thOwnerColumn.style.display = 'table-cell';
        userFilterWrapper.style.display = 'block';
        tabChartUser.style.display = 'inline-block';
        formGroupAddUser.style.display = 'block';
        formGroupEditUser.style.display = 'block';
      } else {
        userAvatarIcon.textContent = '👤';
        userRoleBadge.textContent = 'User';
        userRoleBadge.className = 'role-badge user';
        headerUserStatus.innerHTML = `<span>👤</span> <span>Logged in as <strong>${currentUser.full_name}</strong> (User) • Personal Workspace</span>`;
        projectsTableTitle.textContent = 'My Projects (SQL SELECT)';
        thOwnerColumn.style.display = 'none';
        userFilterWrapper.style.display = 'none';
        tabChartUser.style.display = 'none';
        formGroupAddUser.style.display = 'none';
        formGroupEditUser.style.display = 'none';
      }

      // Reset filters & views
      selectedTech = 'All';
      selectedUserFilter = 'All';
      searchQuery = '';
      searchInput.value = '';
      clearSearchBtn.style.display = 'none';
      switchMainView('records');

      // Fetch users and projects
      fetchUsers();
      fetchProjects();
    }

    loginForm.addEventListener('submit', (e) => {
      e.preventDefault();
      login(loginUsername.value.trim(), loginPassword.value);
    });

    btnLogout.addEventListener('click', logout);

    // -------------------------------------------------------------
    // Data Fetching & Sync
    // -------------------------------------------------------------
    async function fetchUsers() {
      if (!authToken) return;
      try {
        const res = await fetch('/api/users', {
          headers: { 'Authorization': 'Bearer ' + authToken }
        });
        if (res.ok) {
          allUsers = await res.json();
          populateUserSelectors();
          renderUserFilterMenu();
        }
      } catch (err) {
        console.error('Error fetching users:', err);
      }
    }

    function populateUserSelectors() {
      // Add form selector
      projUserAdd.innerHTML = allUsers.map(u => 
        `<option value="${u.id}" ${u.id === currentUser.id ? 'selected' : ''}>${u.full_name} (${u.role})</option>`
      ).join('');

      // Edit form selector
      editUser.innerHTML = allUsers.map(u => 
        `<option value="${u.id}">${u.full_name} (${u.role})</option>`
      ).join('');
    }

    async function fetchProjects() {
      if (!authToken) return;
      try {
        let url = `/api/projects?q=${encodeURIComponent(searchQuery)}&tech=${encodeURIComponent(selectedTech)}`;
        if (currentUser.role === 'manager' && selectedUserFilter !== 'All') {
          url += `&user_id=${encodeURIComponent(selectedUserFilter)}`;
        }
        const res = await fetch(url, {
          headers: { 'Authorization': 'Bearer ' + authToken }
        });
        if (res.status === 401) {
          logout();
          return;
        }
        allProjects = await res.json();
        
        renderTable();
        renderSortMenu();
        renderUserFilterMenu();
        renderPieChart();
        populateEditSelect();
        if (tabRecordsCount) tabRecordsCount.textContent = allProjects.length;
      } catch (err) {
        console.error('Error fetching projects:', err);
        projectsTbody.innerHTML = '<tr><td colspan="7" style="text-align:center; color:#ef4444; padding:2rem;">Error connecting to server.</td></tr>';
      }
    }

    // -------------------------------------------------------------
    // Main View Navigation (Projects vs Distribution)
    // -------------------------------------------------------------
    function switchMainView(viewName) {
      if (viewName === 'records') {
        panelLiveRecords.style.display = 'block';
        panelProjectsDistribution.style.display = 'none';
        btnViewRecords.classList.add('active');
        btnViewRecords.setAttribute('aria-selected', 'true');
        btnViewDistribution.classList.remove('active');
        btnViewDistribution.setAttribute('aria-selected', 'false');
      } else if (viewName === 'distribution') {
        panelLiveRecords.style.display = 'none';
        panelProjectsDistribution.style.display = 'block';
        btnViewDistribution.classList.add('active');
        btnViewDistribution.setAttribute('aria-selected', 'true');
        btnViewRecords.classList.remove('active');
        btnViewRecords.setAttribute('aria-selected', 'false');
        renderPieChart();
      }
    }

    btnViewRecords.addEventListener('click', () => switchMainView('records'));
    btnViewDistribution.addEventListener('click', () => switchMainView('distribution'));
    document.getElementById('btn-chart-goto-records').addEventListener('click', () => switchMainView('records'));

    // -------------------------------------------------------------
    // Add / Edit Project Sub-Tabs
    // -------------------------------------------------------------
    tabAdd.addEventListener('click', () => {
      tabAdd.classList.add('active');
      tabEdit.classList.remove('active');
      projectForm.style.display = 'block';
      editForm.style.display = 'none';
    });

    tabEdit.addEventListener('click', () => {
      tabEdit.classList.add('active');
      tabAdd.classList.remove('active');
      editForm.style.display = 'block';
      projectForm.style.display = 'none';
      populateEditSelect(editSelect.value);
    });

    // -------------------------------------------------------------
    // Table Rendering
    // -------------------------------------------------------------
    function escapeHtml(str) {
      if (!str) return '';
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    }

    function renderTable() {
      let filtered = [...allProjects];

      if (searchQuery) {
        const lower = searchQuery.toLowerCase();
        filtered = filtered.filter(p => 
          (p.name && p.name.toLowerCase().includes(lower)) ||
          (p.description && p.description.toLowerCase().includes(lower)) ||
          (p.owner_name && p.owner_name.toLowerCase().includes(lower)) ||
          (p.technology && p.technology.toLowerCase().includes(lower))
        );
      }

      if (selectedTech !== 'All') {
        filtered = filtered.filter(p => p.technology === selectedTech);
      }

      if (currentUser && currentUser.role === 'manager' && selectedUserFilter !== 'All') {
        filtered = filtered.filter(p => String(p.user_id) === String(selectedUserFilter));
      }

      // Sort: If manager, sorted by owner_name ASC then ID DESC. If user, sorted by ID DESC.
      if (currentUser && currentUser.role === 'manager') {
        filtered.sort((a, b) => {
          const nameA = (a.owner_name || '').toLowerCase();
          const nameB = (b.owner_name || '').toLowerCase();
          if (nameA < nameB) return -1;
          if (nameA > nameB) return 1;
          return Number(b.id) - Number(a.id);
        });
      } else {
        filtered.sort((a, b) => Number(b.id) - Number(a.id));
      }

      recordCounter.textContent = `Showing ${filtered.length} of ${allProjects.length} records`;

      if (filtered.length === 0) {
        const colSpan = (currentUser && currentUser.role === 'manager') ? 7 : 6;
        projectsTbody.innerHTML = `<tr><td colspan="${colSpan}" style="text-align: center; color: #a79fc2; padding: 2rem;">No matching projects found.</td></tr>`;
        return;
      }

      const rows = filtered.map(p => {
        const badgeClass = 'badge-' + (p.technology || 'python').toLowerCase();
        const flashClass = p._isNew ? 'new-row-flash' : '';
        const isManager = currentUser && currentUser.role === 'manager';
        
        let ownerTd = '';
        if (isManager) {
          const ownerBadgeClass = (p.owner_role === 'manager') ? 'badge-user-owner manager-owner' : 'badge-user-owner';
          const icon = (p.owner_role === 'manager') ? '👑' : '👤';
          ownerTd = `<td><span class="${ownerBadgeClass}">${icon} ${escapeHtml(p.owner_name || 'User ' + p.user_id)}</span></td>`;
        }

        return `
          <tr class="${flashClass}">
            <td>#${p.id}</td>
            <td style="font-weight: 600;">${escapeHtml(p.name)}</td>
            <td style="color: #a79fc2;">${escapeHtml(p.description)}</td>
            <td><span class="badge ${badgeClass}">${escapeHtml(p.technology)}</span></td>
            <td><span class="status-badge">${escapeHtml(p.status || 'In Progress')}</span></td>
            ${ownerTd}
            <td><button type="button" class="btn-danger" onclick="deleteProject(${p.id})">Delete</button></td>
          </tr>
        `;
      });

      projectsTbody.innerHTML = rows.join('');
    }

    // -------------------------------------------------------------
    // Controls: Search, Sort Dropdown & User Filter
    // -------------------------------------------------------------
    function renderSortMenu() {
      const techList = ['All', 'Python', 'SQL', 'React', 'Fullstack'];
      sortDropdownLabel.textContent = `🏷️ Tech: ${selectedTech}`;

      sortDropdownMenu.innerHTML = techList.map(t => {
        const count = (t === 'All') ? allProjects.length : allProjects.filter(p => p.technology === t).length;
        const active = (t === selectedTech) ? 'active' : '';
        const check = (t === selectedTech) ? '✓ ' : '';
        return `
          <button type="button" class="dropdown-item ${active}" onclick="selectTechFilter('${t}')">
            <span>${check}${t}</span>
            <span style="font-size: 0.75rem; background: #282147; padding: 0.1rem 0.4rem; border-radius: 0.25rem;">${count}</span>
          </button>
        `;
      }).join('');
    }

    window.selectTechFilter = function(t) {
      selectedTech = t;
      sortDropdownMenu.classList.remove('show');
      renderSortMenu();
      renderTable();
      renderPieChart();
    };

    btnSortToggle.addEventListener('click', (e) => {
      e.stopPropagation();
      sortDropdownMenu.classList.toggle('show');
      userFilterDropdownMenu.classList.remove('show');
    });

    function renderUserFilterMenu() {
      if (!currentUser || currentUser.role !== 'manager') return;
      
      let currentLabel = 'All';
      if (selectedUserFilter !== 'All') {
        const u = allUsers.find(x => String(x.id) === String(selectedUserFilter));
        currentLabel = u ? u.full_name : selectedUserFilter;
      }
      userFilterLabel.textContent = `👥 User: ${currentLabel}`;

      const options = [
        { id: 'All', name: 'All Users', count: allProjects.length },
        ...allUsers.map(u => ({
          id: String(u.id),
          name: u.full_name,
          count: allProjects.filter(p => String(p.user_id) === String(u.id)).length
        }))
      ];

      userFilterDropdownMenu.innerHTML = options.map(opt => {
        const active = (opt.id === selectedUserFilter) ? 'active' : '';
        const check = (opt.id === selectedUserFilter) ? '✓ ' : '';
        return `
          <button type="button" class="dropdown-item ${active}" onclick="selectUserFilter('${opt.id}')">
            <span>${check}${opt.name}</span>
            <span style="font-size: 0.75rem; background: #282147; padding: 0.1rem 0.4rem; border-radius: 0.25rem;">${opt.count}</span>
          </button>
        `;
      }).join('');
    }

    window.selectUserFilter = function(uid) {
      selectedUserFilter = uid;
      userFilterDropdownMenu.classList.remove('show');
      renderUserFilterMenu();
      renderTable();
      renderPieChart();
    };

    btnUserFilterToggle.addEventListener('click', (e) => {
      e.stopPropagation();
      userFilterDropdownMenu.classList.toggle('show');
      sortDropdownMenu.classList.remove('show');
    });

    document.addEventListener('click', () => {
      sortDropdownMenu.classList.remove('show');
      userFilterDropdownMenu.classList.remove('show');
    });

    // Search controls
    searchInput.addEventListener('input', () => {
      searchQuery = searchInput.value.trim();
      clearSearchBtn.style.display = searchQuery ? 'block' : 'none';
      renderTable();
    });

    clearSearchBtn.addEventListener('click', () => {
      searchQuery = '';
      searchInput.value = '';
      clearSearchBtn.style.display = 'none';
      renderTable();
      searchInput.focus();
    });

    // -------------------------------------------------------------
    // Edit Form Selector & Population
    // -------------------------------------------------------------
    function populateEditSelect(selectedId) {
      if (allProjects.length === 0) {
        editSelect.innerHTML = '<option value="">No projects available</option>';
        editName.value = '';
        editDesc.value = '';
        return;
      }

      editSelect.innerHTML = allProjects.map(p => {
        const ownerTag = (currentUser && currentUser.role === 'manager' && p.owner_name) ? ` [${p.owner_name}]` : '';
        return `<option value="${p.id}">#${p.id} - ${escapeHtml(p.name)} (${p.technology})${ownerTag}</option>`;
      }).join('');

      if (selectedId && allProjects.some(p => String(p.id) === String(selectedId))) {
        editSelect.value = selectedId;
      } else {
        editSelect.value = allProjects[0].id;
      }
      onEditSelectChange();
    }

    function onEditSelectChange() {
      const target = allProjects.find(p => String(p.id) === String(editSelect.value));
      if (target) {
        editName.value = target.name || '';
        editDesc.value = target.description || '';
        editTech.value = target.technology || 'Python';
        editStatus.value = target.status || 'In Progress';
        if (editUser && target.user_id) {
          editUser.value = target.user_id;
        }
      }
    }

    editSelect.addEventListener('change', onEditSelectChange);

    // -------------------------------------------------------------
    // CRUD Submissions with Instant Real-Time UI Updates
    // -------------------------------------------------------------
    projectForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const name = document.getElementById('proj-name').value.trim();
      const desc = document.getElementById('proj-desc').value.trim();
      const tech = document.getElementById('proj-tech').value;
      const assignedUid = (currentUser.role === 'manager' && projUserAdd) ? parseInt(projUserAdd.value) : currentUser.id;

      if (!name) return;

      const ownerObj = allUsers.find(u => u.id === assignedUid) || currentUser;

      const existingIds = new Set(allProjects.map(p => Number(p.id)));
      let nextId = 1;
      while (existingIds.has(nextId)) nextId++;

      const optimisticRecord = {
        id: nextId,
        user_id: assignedUid,
        owner_name: ownerObj.full_name,
        owner_role: ownerObj.role,
        name: name,
        description: desc,
        technology: tech,
        status: 'In Progress',
        _isNew: true
      };

      document.getElementById('proj-name').value = '';
      document.getElementById('proj-desc').value = '';

      allProjects.push(optimisticRecord);
      if (tabRecordsCount) tabRecordsCount.textContent = allProjects.length;
      renderTable();
      renderSortMenu();
      renderUserFilterMenu();
      renderPieChart();
      populateEditSelect(optimisticRecord.id);

      try {
        const res = await fetch('/api/projects', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + authToken
          },
          body: JSON.stringify({ name, description: desc, technology: tech, user_id: assignedUid })
        });
        if (!res.ok) throw new Error('Server returned ' + res.status);
        const data = await res.json();
        optimisticRecord.id = data.id;
        renderTable();
        renderPieChart();
      } catch (err) {
        allProjects = allProjects.filter(p => p !== optimisticRecord);
        if (tabRecordsCount) tabRecordsCount.textContent = allProjects.length;
        renderTable();
        renderPieChart();
        alert('Error saving project: ' + err.message);
      }
    });

    editForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const id = editSelect.value;
      if (!id) return;

      const name = editName.value.trim();
      const desc = editDesc.value.trim();
      const tech = editTech.value;
      const status = editStatus.value;
      const assignedUid = (currentUser.role === 'manager' && editUser) ? parseInt(editUser.value) : undefined;

      const target = allProjects.find(p => String(p.id) === String(id));
      if (!target) return;

      const prevCopy = { ...target };
      target.name = name;
      target.description = desc;
      target.technology = tech;
      target.status = status;
      if (assignedUid) {
        target.user_id = assignedUid;
        const u = allUsers.find(x => x.id === assignedUid);
        if (u) {
          target.owner_name = u.full_name;
          target.owner_role = u.role;
        }
      }
      target._isNew = true;

      renderTable();
      renderSortMenu();
      renderUserFilterMenu();
      renderPieChart();

      const btnUpdate = document.getElementById('btn-update');
      btnUpdate.textContent = '💾 Saved!';
      btnUpdate.style.background = '#059669';
      setTimeout(() => {
        btnUpdate.textContent = '✏️ Update Record in SQLite';
        btnUpdate.style.background = '#9333ea';
      }, 1200);

      try {
        const res = await fetch('/api/projects/' + id, {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + authToken
          },
          body: JSON.stringify({ name, description: desc, technology: tech, status, user_id: assignedUid })
        });
        if (!res.ok) throw new Error('Server returned ' + res.status);
      } catch (err) {
        Object.assign(target, prevCopy);
        renderTable();
        renderPieChart();
        alert('Error updating project: ' + err.message);
      }
    });

    window.deleteProject = async function(id) {
      if (!confirm(`Are you sure you want to delete Project #${id}?`)) return;

      const prevProjects = [...allProjects];
      allProjects = allProjects.filter(p => String(p.id) !== String(id));
      if (tabRecordsCount) tabRecordsCount.textContent = allProjects.length;

      renderTable();
      renderSortMenu();
      renderUserFilterMenu();
      renderPieChart();
      populateEditSelect();

      try {
        const res = await fetch('/api/projects/' + id, {
          method: 'DELETE',
          headers: { 'Authorization': 'Bearer ' + authToken }
        });
        if (!res.ok) throw new Error('Server returned ' + res.status);
      } catch (err) {
        allProjects = prevProjects;
        if (tabRecordsCount) tabRecordsCount.textContent = allProjects.length;
        renderTable();
        renderPieChart();
        populateEditSelect();
        alert('Error deleting project: ' + err.message);
      }
    };

    // -------------------------------------------------------------
    // Projects Distribution (Pie Chart Rendering)
    // -------------------------------------------------------------
    tabChartTech.addEventListener('click', () => setChartGroup('technology'));
    tabChartStatus.addEventListener('click', () => setChartGroup('status'));
    tabChartUser.addEventListener('click', () => setChartGroup('user'));

    function setChartGroup(group) {
      currentChartGroup = group;
      tabChartTech.classList.toggle('active', group === 'technology');
      tabChartStatus.classList.toggle('active', group === 'status');
      tabChartUser.classList.toggle('active', group === 'user');
      renderPieChart();
    }

    function renderPieChart() {
      const counts = {};
      allProjects.forEach(p => {
        let key = 'Other';
        if (currentChartGroup === 'technology') {
          key = p.technology || 'Other';
        } else if (currentChartGroup === 'status') {
          key = p.status || 'In Progress';
        } else if (currentChartGroup === 'user') {
          key = p.owner_name || `User ${p.user_id}`;
        }
        counts[key] = (counts[key] || 0) + 1;
      });

      const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]);
      const total = allProjects.length;

      if (total === 0) {
        pieChartSvg.innerHTML = '<text x="130" y="130" text-anchor="middle" dominant-baseline="central" fill="#94a3b8" font-size="13">No records found</text>';
        pieChartLegend.innerHTML = '<div style="color: #64748b; font-size: 0.85rem; text-align: center; padding: 1rem;">No data in database</div>';
        return;
      }

      const cx = 130, cy = 130, r = 95;
      let svgHtml = '';
      let legendHtml = '';

      if (sorted.length === 1) {
        const [label, count] = sorted[0];
        const color = palette[label] || fallbackColors[0];
        svgHtml = `
          <circle cx="${cx}" cy="${cy}" r="${r}" fill="${color}" stroke="#1c1735" stroke-width="2" class="pie-slice" data-label="${escapeHtml(label)}"/>
          <text x="${cx}" y="${cy}" text-anchor="middle" dominant-baseline="central" fill="#ffffff" font-size="13" font-weight="700">100%</text>
        `;
        legendHtml = `
          <div class="legend-item" data-label="${escapeHtml(label)}">
            <div class="legend-left">
              <span class="legend-rank">#1</span>
              <span class="legend-color-dot" style="background: ${color};"></span>
              <span class="legend-label">${escapeHtml(label)}</span>
            </div>
            <div class="legend-right">
              <span class="legend-value">${count}</span>
              <span class="legend-percent">100.0%</span>
            </div>
          </div>
        `;
      } else {
        let currentAngle = -Math.PI / 2;
        sorted.forEach(([label, count], index) => {
          const rank = index + 1;
          const color = palette[label] || fallbackColors[(rank - 1) % fallbackColors.length];
          const frac = count / total;
          const angle = frac * 2 * Math.PI;
          const startAngle = currentAngle;
          const endAngle = currentAngle + angle;
          currentAngle = endAngle;

          const x1 = cx + r * Math.cos(startAngle);
          const y1 = cy + r * Math.sin(startAngle);
          const x2 = cx + r * Math.cos(endAngle);
          const y2 = cy + r * Math.sin(endAngle);
          const large = angle > Math.PI ? 1 : 0;
          const pct = (frac * 100).toFixed(1);

          const pathD = `M ${cx} ${cy} L ${x1.toFixed(2)} ${y1.toFixed(2)} A ${r} ${r} 0 ${large} 1 ${x2.toFixed(2)} ${y2.toFixed(2)} Z`;
          svgHtml += `<path d="${pathD}" fill="${color}" stroke="#1c1735" stroke-width="2" class="pie-slice" data-label="${escapeHtml(label)}"/>`;

          if (frac >= 0.12) {
            const midAngle = (startAngle + endAngle) / 2;
            const lx = cx + (r * 0.65) * Math.cos(midAngle);
            const ly = cy + (r * 0.65) * Math.sin(midAngle);
            svgHtml += `<text x="${lx.toFixed(1)}" y="${ly.toFixed(1)}" text-anchor="middle" dominant-baseline="central" fill="#ffffff" font-size="11" font-weight="700" pointer-events="none">${Math.round(frac*100)}%</text>`;
          }

          legendHtml += `
            <div class="legend-item" data-label="${escapeHtml(label)}">
              <div class="legend-left">
                <span class="legend-rank">#${rank}</span>
                <span class="legend-color-dot" style="background: ${color};"></span>
                <span class="legend-label">${escapeHtml(label)}</span>
              </div>
              <div class="legend-right">
                <span class="legend-value">${count}</span>
                <span class="legend-percent">${pct}%</span>
              </div>
            </div>
          `;
        });
      }

      pieChartSvg.innerHTML = svgHtml;
      pieChartLegend.innerHTML = legendHtml;

      const slices = pieChartSvg.querySelectorAll('.pie-slice');
      const legendItems = pieChartLegend.querySelectorAll('.legend-item');

      legendItems.forEach(item => {
        const lbl = item.getAttribute('data-label');
        item.addEventListener('mouseenter', () => {
          slices.forEach(s => {
            if (s.getAttribute('data-label') === lbl) {
              s.style.opacity = '1';
              s.style.transform = 'scale(1.04)';
              s.style.transformOrigin = '130px 130px';
            } else {
              s.style.opacity = '0.35';
            }
          });
        });
        item.addEventListener('mouseleave', () => {
          slices.forEach(s => {
            s.style.opacity = '1';
            s.style.transform = 'none';
          });
        });
      });
    }

    // -------------------------------------------------------------
    // Initial Startup Check
    // -------------------------------------------------------------
    checkExistingAuth();
  </script>
</body>
</html>
"""
        body = html_content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

# Multi-threaded server: handles concurrent requests in parallel
class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True

def run():
    with ThreadedTCPServer(("", PORT), RequestHandler) as httpd:
        print(f"🚀 Python server running at http://127.0.0.1:{PORT}")
        print("💡 Tech Stack: Python (Backend) + SQLite (SQL Relational DB) + Role-Based Auth")
        print("Press Ctrl+C to stop.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")
            httpd.server_close()

if __name__ == "__main__":
    run()
