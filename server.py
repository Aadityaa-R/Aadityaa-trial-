#!/usr/bin/env python3
"""
Full-Stack Web Application Server (Python + SQL + React)
- Backend: Python http.server with REST API endpoints
- Database: SQLite (SQL) with relational tables, CRUD, and parameterized queries
- Frontend: Modern React UI interacting with the Python backend
"""

import http.server
import socketserver
import json
import sqlite3
import os
import urllib.parse
from html import escape as html_escape

PORT = int(os.environ.get("PORT", 5050))
DB_FILE = os.path.join(os.path.dirname(__file__), "database.db")
socketserver.TCPServer.allow_reuse_address = True

# -------------------------------------------------------------
# SQL Database Setup (SQLite)
# -------------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Create SQL tables
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        technology TEXT NOT NULL,
        status TEXT DEFAULT 'In Progress',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    # Seed sample records if empty
    cursor.execute("SELECT COUNT(*) FROM projects;")
    if cursor.fetchone()[0] == 0:
        cursor.executemany("""
        INSERT INTO projects (name, description, technology, status)
        VALUES (?, ?, ?, ?)
        """, [
            ("Python REST API", "Lightweight backend server handling HTTP endpoints", "Python", "Completed"),
            ("SQL Relational Database", "SQLite database managing structured data and queries", "SQL", "Completed"),
            ("React Frontend Interface", "Interactive UI component for managing projects", "React", "Completed"),
            ("Fullstack Integration", "End-to-end communication between React and Python backend", "Fullstack", "Completed")
        ])
        conn.commit()
    conn.close()

init_db()

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
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path

            if path == "/" or path == "/index.html":
                self.serve_react_app()
            elif path == "/api/projects":
                conn = sqlite3.connect(DB_FILE)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                # Parse query parameters for SQL search (e.g. ?q=login&tech=Python)
                params = urllib.parse.parse_qs(parsed.query)
                q = params.get("q", [""])[0].strip()
                tech = params.get("tech", [""])[0].strip()

                sql = "SELECT * FROM projects WHERE 1=1"
                args = []
                if q:
                    sql += " AND (name LIKE ? OR description LIKE ?)"
                    pattern = f"%{q}%"
                    args.extend([pattern, pattern])
                if tech and tech != "All":
                    sql += " AND technology = ?"
                    args.append(tech)
                sql += " ORDER BY id DESC"

                cursor.execute(sql, args)
                rows = [dict(row) for row in cursor.fetchall()]
                conn.close()
                self._send_json(200, rows)
            elif path == "/api/stats":
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM projects")
                total = cursor.fetchone()[0]
                cursor.execute("SELECT status, COUNT(*) FROM projects GROUP BY status")
                status_counts = dict(cursor.fetchall())
                conn.close()
                self._send_json(200, {"total": total, "by_status": status_counts})
            else:
                self.send_error(404, "Not Found")
        except Exception as e:
            print(f"Server error on GET {self.path}: {e}")
            try:
                self.send_error(500, f"Server Error: {e}")
            except Exception:
                pass

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/projects":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            data = json.loads(body)

            name = data.get("name", "").strip()
            desc = data.get("description", "").strip()
            tech = data.get("technology", "Python").strip()

            if not name:
                self._send_json(400, {"error": "Project name is required"})
                return

            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()

            # Find the lowest available sequence ID starting from 1 (reuse deleted IDs)
            cursor.execute("SELECT id FROM projects ORDER BY id ASC")
            existing_ids = {row[0] for row in cursor.fetchall()}
            next_id = 1
            while next_id in existing_ids:
                next_id += 1

            cursor.execute("""
            INSERT INTO projects (id, name, description, technology, status)
            VALUES (?, ?, ?, ?, 'In Progress')
            """, (next_id, name, desc, tech))
            # Keep sqlite_sequence updated
            cursor.execute("UPDATE sqlite_sequence SET seq = (SELECT COALESCE(MAX(id), 0) FROM projects) WHERE name = 'projects'")
            conn.commit()
            conn.close()

            self._send_json(201, {"id": next_id, "message": "Project created successfully"})
        elif path == "/api/raw-sql":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            data = json.loads(body)
            query = data.get("query", "").strip()

            # Disallow harmful multi-statements
            if not query.lower().startswith("select"):
                self._send_json(400, {"error": "Only SELECT queries are permitted in SQL Explorer"})
                return

            try:
                conn = sqlite3.connect(DB_FILE)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(query)
                rows = [dict(row) for row in cursor.fetchall()]
                conn.close()
                self._send_json(200, {"rows": rows, "count": len(rows)})
            except Exception as e:
                self._send_json(400, {"error": str(e)})
        else:
            self.send_error(404, "Not Found")

    def do_PUT(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/projects/"):
            try:
                project_id = int(path.split("/")[-1])
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length).decode("utf-8")
                data = json.loads(body)

                name = data.get("name", "").strip()
                desc = data.get("description", "").strip()
                tech = data.get("technology", "Python").strip()
                status = data.get("status", "In Progress").strip()

                if not name:
                    self._send_json(400, {"error": "Project name is required"})
                    return

                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                cursor.execute("""
                UPDATE projects
                SET name = ?, description = ?, technology = ?, status = ?
                WHERE id = ?
                """, (name, desc, tech, status, project_id))
                conn.commit()
                conn.close()

                self._send_json(200, {"id": project_id, "message": "Project updated successfully"})
            except ValueError:
                self._send_json(400, {"error": "Invalid project ID"})
            except Exception as e:
                self._send_json(500, {"error": str(e)})
        else:
            self.send_error(404, "Not Found")

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/projects/"):
            try:
                project_id = int(path.split("/")[-1])
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
                cursor.execute("UPDATE sqlite_sequence SET seq = (SELECT COALESCE(MAX(id), 0) FROM projects) WHERE name = 'projects'")
                conn.commit()
                conn.close()
                self._send_json(200, {"message": f"Project {project_id} deleted"})
            except ValueError:
                self._send_json(400, {"error": "Invalid project ID"})
        else:
            self.send_error(404, "Not Found")

    def serve_react_app(self):
        # Query initial data from SQLite so page renders instantly with all records
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM projects ORDER BY id DESC")
        initial_projects = [dict(row) for row in cursor.fetchall()]
        cursor.execute("SELECT COUNT(*) FROM projects")
        total_count = cursor.fetchone()[0]
        conn.close()

        initial_json = json.dumps(initial_projects)

        # Pre-build table rows HTML so page is fully populated with all records on load
        row_items = []
        for p in initial_projects:
            pid = p["id"]
            pname = html_escape(str(p["name"]))
            pdesc = html_escape(str(p.get("description") or ""))
            ptech = html_escape(str(p["technology"]))
            pstatus = html_escape(str(p["status"]))
            badge_class = "badge-py"
            if p["technology"] == "SQL":
                badge_class = "badge-sql"
            elif p["technology"] == "React":
                badge_class = "badge-react"
            row_items.append(
                f'<tr>'
                f'<td>#{pid}</td>'
                f'<td style="font-weight: 600;">{pname}</td>'
                f'<td style="color: #a79fc2;">{pdesc}</td>'
                f'<td><span class="badge {badge_class}">{ptech}</span></td>'
                f'<td><span class="status-badge">{pstatus}</span></td>'
                f'<td><button type="button" class="btn-danger" data-id="{pid}">Delete</button></td>'
                f'</tr>'
            )
        rows_html = "".join(row_items) if row_items else '<tr><td colspan="6" style="text-align: center; color: #64748b; padding: 2rem;">No records found in database.</td></tr>'

        tech_opts = ['All', 'Python', 'SQL', 'React', 'Fullstack']
        sort_items = []
        for t in tech_opts:
            if t == 'All':
                count = len(initial_projects)
            else:
                count = sum(1 for p in initial_projects if p.get('technology') == t)
            active = "active" if t == "All" else ""
            check = "✓ " if t == "All" else ""
            sort_items.append(
                f'<button type="button" class="sort-option {active}" data-tech="{t}">'
                f'<span>{check}{t}</span>'
                f'<span class="sort-badge">{count}</span>'
                f'</button>'
            )
        sort_options_html = "".join(sort_items)

        edit_items = []
        for p in initial_projects:
            pid = p["id"]
            pname = html_escape(str(p["name"]))
            ptech = html_escape(str(p["technology"]))
            edit_items.append(f'<option value="{pid}">#{pid} - {pname} ({ptech})</option>')
        edit_options_html = "".join(edit_items) if edit_items else '<option value="">No projects available</option>'

        counter_text = f"Showing all {len(initial_projects)} records"

        page_template = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Full-Stack Web App: Python + SQL + React</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    body { background: #120e24; color: #f5f3ff; min-height: 100vh; padding: 2rem 1rem; }
    .container { max-width: 900px; margin: 0 auto; }
    header { margin-bottom: 2rem; border-bottom: 1px solid #2e264f; padding-bottom: 1.5rem; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem; }
    h1 { font-size: 1.8rem; font-weight: 700; color: #c084fc; }
    .badges { display: flex; gap: 0.5rem; }
    .badge { padding: 0.35rem 0.75rem; border-radius: 9999px; font-size: 0.8rem; font-weight: 600; display: inline-block; }
    .badge-py { background: #7c3aed; color: white; }
    .badge-sql { background: #d97706; color: white; }
    .badge-react { background: #9333ea; color: white; }
    .card { background: #1c1735; border-radius: 0.75rem; padding: 1.5rem; margin-bottom: 1.5rem; border: 1px solid #2e264f; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25); }
    .card h2 { font-size: 1.25rem; margin-bottom: 1rem; color: #e9d5ff; }
    .form-group { display: flex; gap: 0.75rem; margin-bottom: 1rem; flex-wrap: wrap; }
    input, select, button { padding: 0.75rem 1rem; border-radius: 0.5rem; border: 1px solid #3b3263; font-size: 0.95rem; }
    input, select { background: #0c0919; color: white; flex: 1; min-width: 200px; }
    input:focus, select:focus { outline: none; border-color: #c084fc; box-shadow: 0 0 0 2px rgba(192, 132, 252, 0.2); }
    button { background: #a855f7; color: white; font-weight: 600; cursor: pointer; border: none; transition: all 0.2s; }
    button:hover { background: #9333ea; }
    .btn-danger { background: #ef4444; color: white; padding: 0.4rem 0.8rem; font-size: 0.85rem; border-radius: 0.35rem; }
    .btn-danger:hover { background: #dc2626; }
    .btn-edit { background: #6b21a8; color: white; padding: 0.4rem 0.8rem; font-size: 0.85rem; border-radius: 0.35rem; margin-right: 0.35rem; border: none; font-weight: 600; cursor: pointer; transition: background 0.2s; }
    .btn-edit:hover { background: #7e22ce; }
    .tab-btn {
      padding: 0.65rem 1.25rem;
      border-radius: 0.5rem;
      font-weight: 600;
      font-size: 0.95rem;
      cursor: pointer;
      border: 1px solid #3b3263;
      background: #120e24;
      color: #a79fc2;
      transition: all 0.2s;
    }
    .tab-btn:hover {
      background: #1c1735;
      color: #f5f3ff;
      border-color: #c084fc;
    }
    .tab-btn.active {
      background: #7c3aed;
      color: white;
      border-color: #a855f7;
      box-shadow: 0 0 12px rgba(168, 85, 247, 0.3);
    }
    .table-container { overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; text-align: left; }
    th, td { padding: 0.85rem; border-bottom: 1px solid #282147; }
    th { color: #a79fc2; font-weight: 600; font-size: 0.85rem; text-transform: uppercase; }
    .status-badge { display: inline-block; padding: 0.25rem 0.6rem; border-radius: 0.35rem; font-size: 0.75rem; font-weight: 600; background: #065f46; color: #6ee7b7; }
    .search-box-wrapper { position: relative; margin-bottom: 0.75rem; }
    .search-input { width: 100%; padding-left: 2.75rem; padding-right: 2.5rem; background: #0c0919; font-size: 0.95rem; }
    .search-icon { position: absolute; left: 1rem; top: 50%; transform: translateY(-50%); color: #7e749c; font-size: 1rem; pointer-events: none; }
    .clear-btn { position: absolute; right: 0.75rem; top: 50%; transform: translateY(-50%); background: transparent; border: none; color: #a79fc2; font-size: 1.1rem; cursor: pointer; padding: 0.25rem; }
    .clear-btn:hover { color: #f5f3ff; background: transparent; }
    .btn-sort {
      background: #1c1735;
      color: #f5f3ff;
      border: 1px solid #3b3263;
      border-radius: 0.5rem;
      padding: 0.75rem 1.25rem;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 0.5rem;
      white-space: nowrap;
      transition: all 0.2s;
    }
    .btn-sort:hover {
      background: #282147;
      border-color: #c084fc;
    }
    .sort-dropdown-menu {
      position: absolute;
      top: calc(100% + 0.5rem);
      right: 0;
      background: #1c1735;
      border: 1px solid #3b3263;
      border-radius: 0.5rem;
      min-width: 200px;
      box-shadow: 0 10px 25px rgba(0, 0, 0, 0.6);
      z-index: 50;
      overflow: hidden;
      padding: 0.25rem 0;
    }
    .sort-option {
      width: 100%;
      text-align: left;
      padding: 0.65rem 1rem;
      background: transparent;
      border: none;
      border-radius: 0;
      color: #e9d5ff;
      font-size: 0.9rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      cursor: pointer;
      transition: background 0.15s;
    }
    .sort-option:hover {
      background: #7e22ce;
      color: white;
    }
    .sort-option.active {
      background: rgba(168, 85, 247, 0.25);
      color: #c084fc;
      font-weight: 700;
    }
    .sort-badge {
      background: #0c0919;
      padding: 0.15rem 0.55rem;
      border-radius: 9999px;
      font-size: 0.75rem;
      color: #c4b5fd;
    }
    .search-meta { display: flex; justify-content: space-between; align-items: center; font-size: 0.85rem; color: #a79fc2; margin-bottom: 0.75rem; }
    .highlight { background: rgba(168, 85, 247, 0.35); color: #e9d5ff; font-weight: 700; border-radius: 0.2rem; padding: 0 0.2rem; }
    .btn-link { background: transparent; color: #c084fc; border: none; padding: 0; font-size: 0.85rem; cursor: pointer; text-decoration: underline; }
    .btn-link:hover { background: transparent; color: #e9d5ff; }
    @keyframes rowHighlight {
      0% { background-color: rgba(168, 85, 247, 0.4); }
      100% { background-color: transparent; }
    }
    .new-row-flash {
      animation: rowHighlight 2.5s ease-out;
    }
    .view-toggle-bar {
      display: inline-flex;
      background: #1c1735;
      padding: 0.3rem;
      border-radius: 0.6rem;
      border: 1px solid #2e264f;
      gap: 0.35rem;
    }
    .view-toggle-btn {
      background: transparent;
      color: #a79fc2;
      border: none;
      padding: 0.55rem 1.1rem;
      border-radius: 0.45rem;
      font-weight: 600;
      font-size: 0.9rem;
      cursor: pointer;
      transition: all 0.25s ease;
      display: flex;
      align-items: center;
      gap: 0.4rem;
    }
    .view-toggle-btn:hover {
      color: #f5f3ff;
      background: rgba(168, 85, 247, 0.15);
    }
    .view-toggle-btn.active {
      background: #7c3aed;
      color: white;
      box-shadow: 0 0 14px rgba(124, 58, 237, 0.45);
    }
    .slider-viewport {
      width: 100%;
      overflow: hidden;
      position: relative;
    }
    .slider-track {
      display: flex;
      width: 200%;
      transition: transform 0.55s cubic-bezier(0.25, 1, 0.5, 1);
      align-items: flex-start;
    }
    .slider-track.show-chart {
      transform: translateX(-50%);
    }
    .slide-pane {
      width: 50%;
      flex-shrink: 0;
      box-sizing: border-box;
    }
    #pane-projects {
      padding-right: 0.5rem;
    }
    #pane-chart {
      padding-left: 0.5rem;
    }
    .pie-slice {
      transition: transform 0.2s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.2s, filter 0.2s;
      cursor: pointer;
      transform-origin: 140px 140px;
    }
    .pie-slice:hover {
      opacity: 0.9;
      transform: scale(1.05);
      filter: drop-shadow(0 0 8px rgba(192, 132, 252, 0.5));
    }
    .category-card {
      background: #120e24;
      border: 1px solid #2e264f;
      border-radius: 0.5rem;
      padding: 0.85rem 1rem;
      cursor: pointer;
      transition: all 0.2s ease;
    }
    .category-card:hover {
      background: #191336;
      border-color: #a855f7;
      transform: translateY(-2px);
      box-shadow: 0 4px 12px rgba(168, 85, 247, 0.2);
    }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div>
        <h1>Full-Stack Web App</h1>
        <p style="color: #94a3b8; font-size: 0.9rem; margin-top: 0.25rem;">
          Python Backend (HTTP REST) + SQL Database (SQLite) + Interactive UI
        </p>
      </div>
      <div style="display: flex; gap: 0.75rem; align-items: center; flex-wrap: wrap;">
        <div class="view-toggle-bar">
          <button type="button" id="btn-view-projects" class="view-toggle-btn active" title="View project records">
            📋 Projects
          </button>
          <button type="button" id="btn-view-chart" class="view-toggle-btn" title="Slide to category pie chart view">
            📊 Category Chart
          </button>
        </div>
      </div>
    </header>

    <div class="slider-viewport">
      <div id="slider-track" class="slider-track">
        <!-- Slide 1: Main Projects View -->
        <div class="slide-pane" id="pane-projects">
          <!-- Project Management Card: 2 Sub-Parts (Add New / Edit Existing) -->
    <div class="card">
      <div style="display: flex; gap: 0.5rem; margin-bottom: 1.25rem; border-bottom: 1px solid #2e264f; padding-bottom: 0.75rem;">
        <button type="button" id="tab-add" class="tab-btn active" style="flex: 1;">
          ➕ Add New Project
        </button>
        <button type="button" id="tab-edit" class="tab-btn" style="flex: 1;">
          ✏️ Edit Existing Project
        </button>
      </div>

      <!-- Sub-Part 1: Add New Project -->
      <div id="panel-add">
        <h2 style="font-size: 1.1rem; margin-bottom: 0.75rem; color: #e9d5ff;">
          Add New Project (SQL INSERT)
        </h2>
        <form id="project-form" onsubmit="return false;">
          <div class="form-group">
            <input
              type="text"
              id="proj-name"
              placeholder="Project Name (e.g. Authentication Module)"
              required
            />
            <input
              type="text"
              id="proj-desc"
              placeholder="Description (e.g. Secure user login system)"
            />
            <select id="proj-tech">
              <option value="Python">Python</option>
              <option value="SQL">SQL</option>
              <option value="React">React</option>
              <option value="Fullstack">Fullstack</option>
            </select>
            <button type="submit" id="btn-submit">+ Insert into SQL</button>
          </div>
        </form>
      </div>

      <!-- Sub-Part 2: Edit Existing Project -->
      <div id="panel-edit" style="display: none;">
        <h2 style="font-size: 1.1rem; margin-bottom: 0.75rem; color: #e9d5ff;">
          Edit Existing Project (SQL UPDATE)
        </h2>
        <form id="edit-form" onsubmit="return false;">
          <div style="margin-bottom: 0.75rem;">
            <label style="font-size: 0.85rem; color: #a79fc2; display: block; margin-bottom: 0.35rem; font-weight: 600;">
              Choose Project to Edit:
            </label>
            <select id="edit-select" style="width: 100%; margin-bottom: 0.75rem;">
__INITIAL_EDIT_OPTIONS__
            </select>
          </div>
          <div class="form-group">
            <input
              type="text"
              id="edit-name"
              placeholder="Project Name"
              required
            />
            <input
              type="text"
              id="edit-desc"
              placeholder="Description"
            />
            <select id="edit-tech">
              <option value="Python">Python</option>
              <option value="SQL">SQL</option>
              <option value="React">React</option>
              <option value="Fullstack">Fullstack</option>
            </select>
            <select id="edit-status">
              <option value="In Progress">In Progress</option>
              <option value="Completed">Completed</option>
              <option value="On Hold">On Hold</option>
              <option value="Planned">Planned</option>
            </select>
            <button type="submit" id="btn-update" style="background: #9333ea;">
              💾 Save Changes
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- Live Database Records with Search -->
    <div class="card">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; flex-wrap: wrap; gap: 0.5rem;">
        <h2>Live Database Records (SQL SELECT)</h2>
        <span id="records-counter" style="font-size: 0.85rem; color: #94a3b8;">__INITIAL_COUNTER__</span>
      </div>

      <!-- Search & Sort Controls -->
      <div style="display: flex; gap: 0.5rem; margin-bottom: 1rem; flex-wrap: wrap; align-items: center;">
        <div class="search-box-wrapper" style="flex: 1; min-width: 220px; margin-bottom: 0;">
          <span class="search-icon">🔍</span>
          <input
            type="text"
            id="search-input"
            class="search-input"
            placeholder="Search by project name, description, or ID..."
            autocomplete="off"
          />
          <button
            type="button"
            id="clear-search-btn"
            class="clear-btn"
            style="display: none;"
            title="Clear search"
          >✕</button>
        </div>
        <button type="button" id="btn-search" style="padding: 0.75rem 1.25rem; white-space: nowrap;">
          🔍 Search
        </button>

        <!-- Single Sort Button with Dropdown Menu -->
        <div id="sort-wrapper" style="position: relative;">
          <button type="button" id="btn-sort" class="btn-sort" title="Filter / Sort by category">
            <span>Sort: <strong id="sort-current-label">All</strong></span>
            <span id="sort-arrow" style="font-size: 0.75rem; margin-left: 0.25rem;">▼</span>
          </button>
          <div id="sort-dropdown-menu" class="sort-dropdown-menu" style="display: none;">
__INITIAL_SORT_OPTIONS__
          </div>
        </div>
      </div>

      <!-- Search Meta Indicator -->
      <div id="search-meta" class="search-meta" style="display: none;">
        <span id="search-meta-text"></span>
        <button type="button" class="btn-link" id="reset-filters-btn">Reset All Filters</button>
      </div>

      <!-- Projects Table -->
      <div class="table-container">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Name</th>
              <th>Description</th>
              <th>Tech</th>
              <th>Status</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody id="projects-tbody">
__INITIAL_TABLE_ROWS__
          </tbody>
        </table>
        </div>
      </div>

      <!-- Slide 2: Category Pie Chart View -->
      <div class="slide-pane" id="pane-chart">
        <div class="card">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.25rem; flex-wrap: wrap; gap: 0.75rem; border-bottom: 1px solid #2e264f; padding-bottom: 1rem;">
            <div>
              <h2 style="font-size: 1.25rem; color: #e9d5ff;">📊 Category Distribution Analytics</h2>
              <p style="color: #a79fc2; font-size: 0.85rem; margin-top: 0.2rem;">
                Interactive pie chart with categories sorted by project count
              </p>
            </div>
            <button type="button" id="btn-back-to-projects" class="btn-sort" style="font-size: 0.85rem; padding: 0.55rem 1rem;">
              ← Slide Back to Projects
            </button>
          </div>

          <!-- Chart Layout -->
          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 2rem; align-items: center;">
            <!-- Pie Chart SVG Container -->
            <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 1rem;">
              <div id="pie-chart-container" style="position: relative; width: 280px; height: 280px; display: flex; align-items: center; justify-content: center;">
                <!-- Rendered dynamically -->
              </div>
              <div id="pie-hover-info" style="margin-top: 1rem; min-height: 24px; font-size: 0.9rem; color: #c084fc; font-weight: 600; text-align: center;">
                Hover over or click a slice for details
              </div>
            </div>

            <!-- Sorted Categories Breakdown List -->
            <div>
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.85rem;">
                <h3 style="font-size: 1.05rem; color: #e9d5ff;">
                  Sorted Categories Breakdown
                </h3>
                <span id="chart-total-count" style="font-size: 0.85rem; color: #a79fc2; font-weight: 600;"></span>
              </div>
              <div id="categories-sorted-list" style="display: flex; flex-direction: column; gap: 0.75rem;">
                <!-- Dynamically populated sorted category cards -->
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>

  <script>
    // State pre-populated immediately from SQLite
    let allProjects = __INITIAL_PROJECTS__;
    let searchQuery = '';
    let selectedTech = 'All';
    const techOptions = ['All', 'Python', 'SQL', 'React', 'Fullstack'];

    // DOM Elements
    const projectsTbody = document.getElementById('projects-tbody');
    const recordsCounter = document.getElementById('records-counter');
    const searchInput = document.getElementById('search-input');
    const btnSearch = document.getElementById('btn-search');
    const clearSearchBtn = document.getElementById('clear-search-btn');
    const sortWrapper = document.getElementById('sort-wrapper');
    const btnSort = document.getElementById('btn-sort');
    const sortCurrentLabel = document.getElementById('sort-current-label');
    const sortArrow = document.getElementById('sort-arrow');
    const sortDropdownMenu = document.getElementById('sort-dropdown-menu');
    const searchMeta = document.getElementById('search-meta');
    const searchMetaText = document.getElementById('search-meta-text');
    const resetFiltersBtn = document.getElementById('reset-filters-btn');
    const projectForm = document.getElementById('project-form');
    const tabAdd = document.getElementById('tab-add');
    const tabEdit = document.getElementById('tab-edit');
    const panelAdd = document.getElementById('panel-add');
    const panelEdit = document.getElementById('panel-edit');
    const editForm = document.getElementById('edit-form');
    const editSelect = document.getElementById('edit-select');
    const editName = document.getElementById('edit-name');
    const editDesc = document.getElementById('edit-desc');
    const editTech = document.getElementById('edit-tech');
    const editStatus = document.getElementById('edit-status');
    const btnUpdate = document.getElementById('btn-update');
    const sliderTrack = document.getElementById('slider-track');
    const btnViewProjects = document.getElementById('btn-view-projects');
    const btnViewChart = document.getElementById('btn-view-chart');
    const btnBackToProjects = document.getElementById('btn-back-to-projects');
    const pieChartContainer = document.getElementById('pie-chart-container');
    const pieHoverInfo = document.getElementById('pie-hover-info');
    const categoriesSortedList = document.getElementById('categories-sorted-list');
    const chartTotalCount = document.getElementById('chart-total-count');

    // Helper: Escape HTML to prevent XSS
    function escapeHtml(str) {
      if (!str) return '';
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    }

    // Helper: Highlight matching query terms (safe substring matching without regex)
    function highlight(text, query) {
      const safeText = escapeHtml(text);
      if (!query || !query.trim()) return safeText;
      const q = query.trim().toLowerCase();
      const lower = safeText.toLowerCase();
      let result = '';
      let cursor = 0;
      let idx = lower.indexOf(q, cursor);
      if (idx === -1) return safeText;
      while (idx !== -1) {
        result += safeText.slice(cursor, idx) + '<span class="highlight">' + safeText.slice(idx, idx + q.length) + '</span>';
        cursor = idx + q.length;
        idx = lower.indexOf(q, cursor);
      }
      result += safeText.slice(cursor);
      return result;
    }

    // Render Sort Dropdown Menu options
    function renderSortMenu() {
      sortDropdownMenu.innerHTML = techOptions.map(t => {
        const count = t === 'All'
          ? allProjects.length
          : allProjects.filter(p => p.technology === t).length;
        const isSelected = selectedTech === t;
        const activeClass = isSelected ? 'active' : '';
        const checkIcon = isSelected ? '✓ ' : '';
        return '<button type="button" class="sort-option ' + activeClass + '" data-tech="' + t + '">' +
               '<span>' + checkIcon + t + '</span>' +
               '<span class="sort-badge">' + count + '</span>' +
               '</button>';
      }).join('');
      sortCurrentLabel.textContent = selectedTech;
    }

    // Toggle Dropdown Menu
    btnSort.addEventListener('click', (e) => {
      e.stopPropagation();
      const isOpen = sortDropdownMenu.style.display === 'block';
      sortDropdownMenu.style.display = isOpen ? 'none' : 'block';
      sortArrow.textContent = isOpen ? '▼' : '▲';
    });

    // Close Dropdown when clicking outside
    document.addEventListener('click', (e) => {
      if (sortWrapper && !sortWrapper.contains(e.target)) {
        sortDropdownMenu.style.display = 'none';
        sortArrow.textContent = '▼';
      }
    });

    // Close Dropdown on Escape
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        sortDropdownMenu.style.display = 'none';
        sortArrow.textContent = '▼';
      }
    });

    // Event Delegation for Sort Option selection
    sortDropdownMenu.addEventListener('click', (e) => {
      const btn = e.target.closest('.sort-option');
      if (!btn) return;
      selectedTech = btn.getAttribute('data-tech');
      searchQuery = '';
      searchInput.value = '';
      clearSearchBtn.style.display = 'none';
      sortDropdownMenu.style.display = 'none';
      sortArrow.textContent = '▼';
      renderSortMenu();
      renderTable();
    });

    // Populate Edit dropdown options
    function populateEditSelect(selectedId) {
      if (allProjects.length === 0) {
        editSelect.innerHTML = '<option value="">No projects available</option>';
        editName.value = '';
        editDesc.value = '';
        return;
      }
      editSelect.innerHTML = allProjects.map(p => {
        return '<option value="' + p.id + '">' +
               '#' + p.id + ' - ' + escapeHtml(p.name) + ' (' + escapeHtml(p.technology) + ')' +
               '</option>';
      }).join('');
      if (selectedId) {
        editSelect.value = String(selectedId);
      }
      loadSelectedProjectForEditing();
    }

    // Load selected project data into the edit inputs
    function loadSelectedProjectForEditing() {
      const currentId = editSelect.value;
      const project = allProjects.find(p => String(p.id) === String(currentId));
      if (project) {
        editName.value = project.name || '';
        editDesc.value = project.description || '';
        editTech.value = project.technology || 'Python';
        editStatus.value = project.status || 'In Progress';
      }
    }

    editSelect.addEventListener('change', loadSelectedProjectForEditing);

    // Tab switching handlers
    tabAdd.addEventListener('click', () => {
      tabAdd.classList.add('active');
      tabEdit.classList.remove('active');
      panelAdd.style.display = 'block';
      panelEdit.style.display = 'none';
    });

    tabEdit.addEventListener('click', () => {
      tabEdit.classList.add('active');
      tabAdd.classList.remove('active');
      panelAdd.style.display = 'none';
      panelEdit.style.display = 'block';
      populateEditSelect();
      editName.focus();
    });

    // Slider Navigation Handlers
    function slideToProjects() {
      sliderTrack.classList.remove('show-chart');
      btnViewProjects.classList.add('active');
      btnViewChart.classList.remove('active');
    }

    function slideToChart() {
      sliderTrack.classList.add('show-chart');
      btnViewChart.classList.add('active');
      btnViewProjects.classList.remove('active');
      renderPieChart();
    }

    btnViewProjects.addEventListener('click', slideToProjects);
    btnViewChart.addEventListener('click', slideToChart);
    btnBackToProjects.addEventListener('click', slideToProjects);

    // Color mapping for Pie Chart & Category Cards
    const categoryColorMap = {
      'Python': '#8b5cf6',
      'SQL': '#f59e0b',
      'React': '#c084fc',
      'Fullstack': '#10b981'
    };
    const defaultColorList = ['#8b5cf6', '#f59e0b', '#c084fc', '#10b981', '#06b6d4', '#ec4899', '#3b82f6', '#14b8a6'];

    function getCategoryColor(cat, idx) {
      if (categoryColorMap[cat]) return categoryColorMap[cat];
      return defaultColorList[idx % defaultColorList.length];
    }

    // Render Pie Chart & Sorted Category Breakdown
    function renderPieChart() {
      const counts = {};
      allProjects.forEach(p => {
        const cat = p.technology || 'Uncategorized';
        counts[cat] = (counts[cat] || 0) + 1;
      });

      const sortedCategories = Object.keys(counts)
        .map(cat => ({ name: cat, count: counts[cat] }))
        .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));

      const total = allProjects.length;
      if (chartTotalCount) {
        chartTotalCount.textContent = 'Total: ' + total + ' project' + (total === 1 ? '' : 's');
      }

      if (total === 0) {
        pieChartContainer.innerHTML = '<svg viewBox="0 0 280 280" width="260" height="260">' +
          '<circle cx="140" cy="140" r="95" fill="none" stroke="#2e264f" stroke-width="25" />' +
          '<text x="140" y="145" text-anchor="middle" font-size="14" fill="#a79fc2">No Projects</text>' +
          '</svg>';
        categoriesSortedList.innerHTML = '<div style="color: #a79fc2; padding: 1.5rem; text-align: center;">No projects in database yet. Add a project to view category statistics.</div>';
        pieHoverInfo.textContent = 'No project data available';
        return;
      }

      const cx = 140, cy = 140, r = 110, rInner = 58;
      let currentAngle = -Math.PI / 2;
      const slices = sortedCategories.map((d, idx) => {
        const fraction = d.count / total;
        const percent = Math.round(fraction * 1000) / 10;
        const color = getCategoryColor(d.name, idx);
        const angle = fraction * 2 * Math.PI;
        const startAngle = currentAngle;
        const endAngle = currentAngle + angle;
        currentAngle = endAngle;

        let path = '';
        if (sortedCategories.length === 1 || fraction >= 0.9999) {
          path = 'M ' + cx + ' ' + (cy - r) +
                 ' A ' + r + ' ' + r + ' 0 1 1 ' + cx + ' ' + (cy + r) +
                 ' A ' + r + ' ' + r + ' 0 1 1 ' + cx + ' ' + (cy - r) +
                 ' M ' + cx + ' ' + (cy - rInner) +
                 ' A ' + rInner + ' ' + rInner + ' 0 1 0 ' + cx + ' ' + (cy + rInner) +
                 ' A ' + rInner + ' ' + rInner + ' 0 1 0 ' + cx + ' ' + (cy - rInner) + ' Z';
        } else {
          const x1 = cx + r * Math.cos(startAngle);
          const y1 = cy + r * Math.sin(startAngle);
          const x2 = cx + r * Math.cos(endAngle);
          const y2 = cy + r * Math.sin(endAngle);
          const x3 = cx + rInner * Math.cos(endAngle);
          const y3 = cy + rInner * Math.sin(endAngle);
          const x4 = cx + rInner * Math.cos(startAngle);
          const y4 = cy + rInner * Math.sin(startAngle);
          const largeArc = angle > Math.PI ? 1 : 0;
          path = 'M ' + x1 + ' ' + y1 +
                 ' A ' + r + ' ' + r + ' 0 ' + largeArc + ' 1 ' + x2 + ' ' + y2 +
                 ' L ' + x3 + ' ' + y3 +
                 ' A ' + rInner + ' ' + rInner + ' 0 ' + largeArc + ' 0 ' + x4 + ' ' + y4 + ' Z';
        }

        return {
          name: d.name,
          count: d.count,
          percent: percent,
          color: color,
          path: path
        };
      });

      let svgHtml = '<svg viewBox="0 0 280 280" width="280" height="280">';
      slices.forEach((s) => {
        svgHtml += '<path class="pie-slice" data-cat="' + escapeHtml(s.name) + '" data-count="' + s.count + '" data-pct="' + s.percent + '" fill="' + s.color + '" stroke="#1c1735" stroke-width="2" d="' + s.path + '"></path>';
      });
      svgHtml += '<circle cx="' + cx + '" cy="' + cy + '" r="' + (rInner - 2) + '" fill="#120e24" />' +
                 '<text x="' + cx + '" y="' + (cy - 4) + '" text-anchor="middle" font-size="24" font-weight="700" fill="#f5f3ff">' + total + '</text>' +
                 '<text x="' + cx + '" y="' + (cy + 16) + '" text-anchor="middle" font-size="10" font-weight="600" fill="#a79fc2" letter-spacing="1">PROJECTS</text>' +
                 '</svg>';

      pieChartContainer.innerHTML = svgHtml;

      let cardsHtml = '';
      slices.forEach((s, idx) => {
        cardsHtml += '<div class="category-card" data-tech="' + escapeHtml(s.name) + '">' +
          '<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.45rem;">' +
            '<div style="display: flex; align-items: center; gap: 0.5rem;">' +
              '<span style="font-size: 0.75rem; font-weight: 700; color: #a79fc2; background: #1c1735; padding: 0.15rem 0.45rem; border-radius: 0.25rem;">#' + (idx + 1) + '</span>' +
              '<span style="display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: ' + s.color + ';"></span>' +
              '<strong style="color: #f5f3ff;">' + escapeHtml(s.name) + '</strong>' +
            '</div>' +
            '<div>' +
              '<span style="font-weight: 700; color: #c084fc;">' + s.count + ' project' + (s.count === 1 ? '' : 's') + '</span>' +
              '<span style="color: #a79fc2; font-size: 0.85rem; margin-left: 0.4rem;">(' + s.percent + '%)</span>' +
            '</div>' +
          '</div>' +
          '<div style="width: 100%; height: 6px; background: #0c0919; border-radius: 3px; overflow: hidden;">' +
            '<div style="width: ' + s.percent + '%; height: 100%; background: ' + s.color + '; border-radius: 3px; transition: width 0.4s ease;"></div>' +
          '</div>' +
          '<div style="text-align: right; margin-top: 0.35rem;">' +
            '<span style="font-size: 0.75rem; color: #a79fc2;">Click to filter table by ' + escapeHtml(s.name) + ' →</span>' +
          '</div>' +
        '</div>';
      });

      categoriesSortedList.innerHTML = cardsHtml;
    }

    // Filter table by technology and slide back to table
    function filterByTechAndSlide(tech) {
      selectedTech = tech;
      searchQuery = '';
      searchInput.value = '';
      clearSearchBtn.style.display = 'none';
      renderSortMenu();
      renderTable();
      slideToProjects();
    }

    // Pie chart slice interactions
    pieChartContainer.addEventListener('mouseover', (e) => {
      const slice = e.target.closest('.pie-slice');
      if (slice) {
        const cat = slice.getAttribute('data-cat');
        const count = slice.getAttribute('data-count');
        const pct = slice.getAttribute('data-pct');
        pieHoverInfo.textContent = cat + ': ' + count + ' project' + (count === '1' ? '' : 's') + ' (' + pct + '%)';
      }
    });

    pieChartContainer.addEventListener('mouseout', (e) => {
      const slice = e.target.closest('.pie-slice');
      if (slice) {
        pieHoverInfo.textContent = 'Hover over or click a slice for details';
      }
    });

    pieChartContainer.addEventListener('click', (e) => {
      const slice = e.target.closest('.pie-slice');
      if (slice) {
        const cat = slice.getAttribute('data-cat');
        if (cat) filterByTechAndSlide(cat);
      }
    });

    // Category card click
    categoriesSortedList.addEventListener('click', (e) => {
      const card = e.target.closest('.category-card');
      if (card) {
        const cat = card.getAttribute('data-tech');
        if (cat) filterByTechAndSlide(cat);
      }
    });

    // Render Projects Table
    function renderTable() {
      const q = searchQuery.trim().toLowerCase();
      const filtered = allProjects.filter(p => {
        // Filter by selected category button
        const matchTech = selectedTech === 'All' || p.technology === selectedTech;
        if (!matchTech) return false;

        // If no search query, show all records in category normally
        if (!q) return true;

        // When searched, show ONLY matching records
        const nameStr = (p.name || '').toLowerCase();
        const descStr = (p.description || '').toLowerCase();
        const techStr = (p.technology || '').toLowerCase();
        const statusStr = (p.status || '').toLowerCase();
        const idStr = String(p.id);

        return nameStr.includes(q) ||
          descStr.includes(q) ||
          techStr.includes(q) ||
          statusStr.includes(q) ||
          idStr === q ||
          ('#' + idStr) === q;
      });

      // Update counter
      if (filtered.length === allProjects.length && !q && selectedTech === 'All') {
        recordsCounter.textContent = 'Showing all ' + allProjects.length + ' records';
      } else {
        recordsCounter.textContent = 'Showing ' + filtered.length + ' of ' + allProjects.length + ' records';
      }

      // Update search/filter meta display
      if (searchQuery || selectedTech !== 'All') {
        searchMeta.style.display = 'flex';
        let metaHtml = '<span>Showing: ';
        if (selectedTech !== 'All') metaHtml += 'category <strong>' + escapeHtml(selectedTech) + '</strong>';
        if (selectedTech !== 'All' && searchQuery) metaHtml += ' + ';
        if (searchQuery) metaHtml += 'search "<strong>' + escapeHtml(searchQuery) + '</strong>"';
        metaHtml += '</span>';
        searchMetaText.innerHTML = metaHtml;
      } else {
        searchMeta.style.display = 'none';
      }

      // Render table rows
      if (filtered.length === 0) {
        if (allProjects.length > 0) {
          const reason = searchQuery ? 'search for "' + escapeHtml(searchQuery) + '"' : 'category "' + escapeHtml(selectedTech) + '"';
          projectsTbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: #94a3b8; padding: 2.5rem;">' +
            '🔍 No projects match your ' + reason + '.' +
            '<br><button type="button" class="btn-link" id="empty-clear-btn" style="margin-top: 0.75rem;">Show all records</button>' +
            '</td></tr>';
          const emptyBtn = document.getElementById('empty-clear-btn');
          if (emptyBtn) emptyBtn.addEventListener('click', resetFilters);
        } else {
          projectsTbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: #64748b; padding: 2rem;">No records found in database.</td></tr>';
        }
        return;
      }

      projectsTbody.innerHTML = filtered.map(p => {
        let badgeClass = 'badge-py';
        if (p.technology === 'SQL') badgeClass = 'badge-sql';
        else if (p.technology === 'React') badgeClass = 'badge-react';

        const flashClass = p._isNew ? ' class="new-row-flash"' : '';
        return '<tr' + flashClass + '>' +
          '<td>#' + p.id + '</td>' +
          '<td style="font-weight: 600;">' + highlight(p.name, searchQuery) + '</td>' +
          '<td style="color: #a79fc2;">' + highlight(p.description, searchQuery) + '</td>' +
          '<td><span class="badge ' + badgeClass + '">' + escapeHtml(p.technology) + '</span></td>' +
          '<td><span class="status-badge">' + escapeHtml(p.status) + '</span></td>' +
          '<td><button type="button" class="btn-danger" data-id="' + p.id + '">Delete</button></td>' +
          '</tr>';
      }).join('');

      // Reset temporary flash flag after rendering
      filtered.forEach(p => { if (p._isNew) delete p._isNew; });

    }

    // Event delegation: Delete project row
    projectsTbody.addEventListener('click', (e) => {
      const deleteBtn = e.target.closest('.btn-danger');
      if (deleteBtn) {
        const id = deleteBtn.getAttribute('data-id');
        if (id) deleteProject(id);
      }
    });

    // Reset all filters
    function resetFilters() {
      searchQuery = '';
      selectedTech = 'All';
      searchInput.value = '';
      clearSearchBtn.style.display = 'none';
      renderSortMenu();
      renderTable();
    }
    resetFiltersBtn.addEventListener('click', resetFilters);

    // Execute search when user clicks Search button or presses Enter
    function executeSearch() {
      searchQuery = searchInput.value.trim();
      clearSearchBtn.style.display = searchInput.value ? 'block' : 'none';
      renderTable();
    }

    btnSearch.addEventListener('click', executeSearch);

    searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        executeSearch();
      }
    });

    // Update clear button visibility as user types, and if cleared, auto-reset search
    searchInput.addEventListener('input', () => {
      clearSearchBtn.style.display = searchInput.value ? 'block' : 'none';
      if (searchInput.value.trim() === '' && searchQuery !== '') {
        searchQuery = '';
        renderTable();
      }
    });

    clearSearchBtn.addEventListener('click', () => {
      searchQuery = '';
      searchInput.value = '';
      clearSearchBtn.style.display = 'none';
      renderTable();
      searchInput.focus();
    });

    // Fetch API Data
    async function fetchProjects() {
      try {
        const res = await fetch('/api/projects');
        allProjects = await res.json();
        allProjects.sort((a, b) => Number(b.id) - Number(a.id));
        renderTable();
        renderSortMenu();
        populateEditSelect(editSelect.value);
        renderPieChart();
      } catch (err) {
        console.error('Error fetching projects:', err);
        projectsTbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:#ef4444; padding:2rem;">Error connecting to Python backend.</td></tr>';
      }
    }

    // Insert New Project with Instant Real-Time UI Update
    projectForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const nameInput = document.getElementById('proj-name');
      const descInput = document.getElementById('proj-desc');
      const techInput = document.getElementById('proj-tech');
      const btnSubmit = document.getElementById('btn-submit');

      const name = nameInput.value.trim();
      const desc = descInput.value.trim();
      const tech = techInput.value;
      if (!name) {
        nameInput.focus();
        nameInput.style.borderColor = '#ef4444';
        setTimeout(() => { nameInput.style.borderColor = '#3b3263'; }, 1500);
        return;
      }

      // Clear input fields immediately so user can type next entry
      nameInput.value = '';
      descInput.value = '';

      // Instant optimistic UI update: find lowest available ID in sequence (starting from 1) to reuse deleted IDs
      const existingIds = new Set(allProjects.map(p => Number(p.id)));
      let nextId = 1;
      while (existingIds.has(nextId)) {
        nextId++;
      }
      const newRecord = {
        id: nextId,
        name: name,
        description: desc,
        technology: tech,
        status: 'In Progress',
        _isNew: true
      };

      allProjects.push(newRecord);
      allProjects.sort((a, b) => Number(b.id) - Number(a.id));

      // Make sure the new row is visible in the table
      if (selectedTech !== 'All' && selectedTech !== tech) {
        selectedTech = 'All';
      }
      searchQuery = '';
      searchInput.value = '';
      clearSearchBtn.style.display = 'none';

      // Update UI in real-time (0ms delay)
      renderSortMenu();
      renderTable();
      populateEditSelect(newRecord.id);
      renderPieChart();

      // Asynchronously persist to SQLite in background
      try {
        const res = await fetch('/api/projects', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, description: desc, technology: tech })
        });
        if (!res.ok) throw new Error('Server returned ' + res.status);
        const data = await res.json();
        if (data && data.id) {
          newRecord.id = data.id;
          allProjects.sort((a, b) => Number(b.id) - Number(a.id));
          renderTable();
          populateEditSelect(data.id);
          renderPieChart();
        }
      } catch (err) {
        // Rollback on failure
        allProjects = allProjects.filter(p => p !== newRecord);
        allProjects.sort((a, b) => Number(b.id) - Number(a.id));
        renderSortMenu();
        renderTable();
        populateEditSelect();
        renderPieChart();
        alert('Error saving project to database: ' + err.message);
      }
    });

    // Update Existing Project with Instant Real-Time UI Update
    editForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const id = editSelect.value;
      if (!id) {
        alert('Please select a project to edit.');
        return;
      }
      const name = editName.value.trim();
      const desc = editDesc.value.trim();
      const tech = editTech.value;
      const status = editStatus.value;

      if (!name) {
        editName.focus();
        editName.style.borderColor = '#ef4444';
        setTimeout(() => { editName.style.borderColor = '#3b3263'; }, 1500);
        return;
      }

      const prevProjects = JSON.parse(JSON.stringify(allProjects));
      const targetProj = allProjects.find(p => String(p.id) === String(id));
      if (!targetProj) return;

      targetProj.name = name;
      targetProj.description = desc;
      targetProj.technology = tech;
      targetProj.status = status;
      targetProj._isNew = true;

      // Update UI immediately
      renderSortMenu();
      renderTable();
      populateEditSelect(id);
      renderPieChart();

      // Save button visual feedback
      btnUpdate.textContent = '✓ Saved!';
      btnUpdate.style.background = '#059669';
      setTimeout(() => {
        btnUpdate.textContent = '💾 Save Changes';
        btnUpdate.style.background = '#9333ea';
      }, 1200);

      // Asynchronously persist to SQLite in background
      try {
        const res = await fetch('/api/projects/' + id, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, description: desc, technology: tech, status })
        });
        if (!res.ok) throw new Error('Server returned ' + res.status);
      } catch (err) {
        allProjects = prevProjects;
        renderSortMenu();
        renderTable();
        populateEditSelect(id);
        renderPieChart();
        alert('Error updating project: ' + err.message);
      }
    });

    // Delete Project with Instant Real-Time UI Update
    async function deleteProject(id) {
      const prevProjects = [...allProjects];
      allProjects = allProjects.filter(p => String(p.id) !== String(id));
      renderSortMenu();
      renderTable();
      populateEditSelect();
      renderPieChart();

      try {
        const res = await fetch('/api/projects/' + id, { method: 'DELETE' });
        if (!res.ok) throw new Error('Server returned ' + res.status);
      } catch (err) {
        allProjects = prevProjects;
        renderSortMenu();
        renderTable();
        populateEditSelect();
        renderPieChart();
        alert('Error deleting project: ' + err.message);
      }
    }

    // Initial instant render from pre-loaded SQLite data
    renderSortMenu();
    renderTable();
    populateEditSelect();
    renderPieChart();

    // Background live refreshes
    fetchProjects();
  </script>
</body>
</html>
"""
        page_html = (page_template
                     .replace("__INITIAL_PROJECTS__", initial_json)
                     .replace("__INITIAL_TABLE_ROWS__", rows_html)
                     .replace("__INITIAL_SORT_OPTIONS__", sort_options_html)
                     .replace("__INITIAL_EDIT_OPTIONS__", edit_options_html)
                     .replace("__INITIAL_COUNTER__", counter_text))
        body = page_html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

# Multi-threaded server: handles concurrent requests in parallel so nothing hangs
class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True

def run():
    with ThreadedTCPServer(("", PORT), RequestHandler) as httpd:
        print(f"🚀 Python server running at http://127.0.0.1:{PORT}")
        print("💡 Tech Stack: Python (Backend) + SQLite (SQL) + React (Frontend)")
        print("Press Ctrl+C to stop.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")
            httpd.server_close()

if __name__ == "__main__":
    run()
