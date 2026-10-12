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
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
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
            cursor.execute("""
            INSERT INTO projects (name, description, technology, status)
            VALUES (?, ?, ?, 'In Progress')
            """, (name, desc, tech))
            conn.commit()
            new_id = cursor.lastrowid
            conn.close()

            self._send_json(201, {"id": new_id, "message": "Project created successfully"})
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

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/projects/"):
            try:
                project_id = int(path.split("/")[-1])
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
                conn.commit()
                conn.close()
                self._send_json(200, {"message": f"Project {project_id} deleted"})
            except ValueError:
                self._send_json(400, {"error": "Invalid project ID"})
        else:
            self.send_error(404, "Not Found")

    def serve_react_app(self):
        # Query initial data from SQLite so page renders instantly without waiting for fetch
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM projects ORDER BY id DESC")
        initial_projects = [dict(row) for row in cursor.fetchall()]
        cursor.execute("SELECT COUNT(*) FROM projects")
        total_count = cursor.fetchone()[0]
        conn.close()

        initial_json = json.dumps(initial_projects)

        html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Full-Stack Web App: Python + SQL + React</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    body { background: #0f172a; color: #f8fafc; min-height: 100vh; padding: 2rem 1rem; }
    .container { max-width: 900px; margin: 0 auto; }
    header { margin-bottom: 2rem; border-bottom: 1px solid #1e293b; padding-bottom: 1.5rem; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem; }
    h1 { font-size: 1.8rem; font-weight: 700; color: #38bdf8; }
    .badges { display: flex; gap: 0.5rem; }
    .badge { padding: 0.35rem 0.75rem; border-radius: 9999px; font-size: 0.8rem; font-weight: 600; display: inline-block; }
    .badge-py { background: #0284c7; color: white; }
    .badge-sql { background: #d97706; color: white; }
    .badge-react { background: #06b6d4; color: white; }
    .card { background: #1e293b; border-radius: 0.75rem; padding: 1.5rem; margin-bottom: 1.5rem; border: 1px solid #334155; }
    .card h2 { font-size: 1.25rem; margin-bottom: 1rem; color: #e2e8f0; }
    .form-group { display: flex; gap: 0.75rem; margin-bottom: 1rem; flex-wrap: wrap; }
    input, select, button { padding: 0.75rem 1rem; border-radius: 0.5rem; border: 1px solid #475569; font-size: 0.95rem; }
    input, select { background: #0f172a; color: white; flex: 1; min-width: 200px; }
    input:focus, select:focus { outline: none; border-color: #38bdf8; }
    button { background: #38bdf8; color: #0f172a; font-weight: 600; cursor: pointer; border: none; transition: background 0.2s; }
    button:hover { background: #0ea5e9; }
    .btn-danger { background: #ef4444; color: white; padding: 0.4rem 0.8rem; font-size: 0.85rem; border-radius: 0.35rem; }
    .btn-danger:hover { background: #dc2626; }
    .table-container { overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; text-align: left; }
    th, td { padding: 0.85rem; border-bottom: 1px solid #334155; }
    th { color: #94a3b8; font-weight: 600; font-size: 0.85rem; text-transform: uppercase; }
    .status-badge { display: inline-block; padding: 0.25rem 0.6rem; border-radius: 0.35rem; font-size: 0.75rem; font-weight: 600; background: #065f46; color: #6ee7b7; }
    .sql-box { background: #090d16; padding: 1rem; border-radius: 0.5rem; font-family: monospace; color: #a5f3fc; margin-top: 1rem; border: 1px solid #1e293b; overflow-x: auto; }
    .stats-bar { display: flex; gap: 1rem; margin-bottom: 1.5rem; }
    .stat-item { flex: 1; background: #1e293b; padding: 1rem; border-radius: 0.5rem; border: 1px solid #334155; text-align: center; }
    .stat-val { font-size: 1.5rem; font-weight: 700; color: #38bdf8; }
    .stat-lbl { font-size: 0.8rem; color: #94a3b8; margin-top: 0.25rem; }
    .search-box-wrapper { position: relative; margin-bottom: 0.75rem; }
    .search-input { width: 100%; padding-left: 2.75rem; padding-right: 2.5rem; background: #090d16; font-size: 0.95rem; }
    .search-icon { position: absolute; left: 1rem; top: 50%; transform: translateY(-50%); color: #64748b; font-size: 1rem; pointer-events: none; }
    .clear-btn { position: absolute; right: 0.75rem; top: 50%; transform: translateY(-50%); background: transparent; border: none; color: #94a3b8; font-size: 1.1rem; cursor: pointer; padding: 0.25rem; }
    .clear-btn:hover { color: #f8fafc; background: transparent; }
    .filter-chips { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 1rem; }
    .chip { padding: 0.35rem 0.8rem; border-radius: 9999px; font-size: 0.8rem; font-weight: 600; cursor: pointer; background: #0f172a; border: 1px solid #334155; color: #94a3b8; transition: all 0.2s; }
    .chip:hover { border-color: #38bdf8; color: white; }
    .chip.active { background: #0284c7; border-color: #38bdf8; color: white; }
    .search-meta { display: flex; justify-content: space-between; align-items: center; font-size: 0.85rem; color: #94a3b8; margin-bottom: 0.75rem; }
    .highlight { background: rgba(56, 189, 248, 0.3); color: #38bdf8; font-weight: 700; border-radius: 0.2rem; padding: 0 0.2rem; }
    .btn-link { background: transparent; color: #38bdf8; border: none; padding: 0; font-size: 0.85rem; cursor: pointer; text-decoration: underline; }
    .btn-link:hover { background: transparent; color: #7dd3fc; }
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
      <div class="badges">
        <span class="badge badge-py">Python 3</span>
        <span class="badge badge-sql">SQLite SQL</span>
        <span class="badge badge-react">Interactive UI</span>
      </div>
    </header>

    <div class="stats-bar">
      <div class="stat-item">
        <div class="stat-val" id="stat-total">__TOTAL_COUNT__</div>
        <div class="stat-lbl">Total Records in SQL DB</div>
      </div>
      <div class="stat-item">
        <div class="stat-val" style="color: #4ade80;">Online</div>
        <div class="stat-lbl">Python Server Status</div>
      </div>
      <div class="stat-item">
        <div class="stat-val" id="stat-port">:5050</div>
        <div class="stat-lbl">Active Port</div>
      </div>
    </div>

    <!-- Insert Form -->
    <div class="card">
      <h2>Add New Project (SQL INSERT)</h2>
      <form id="project-form">
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

    <!-- Live Database Records with Search -->
    <div class="card">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; flex-wrap: wrap; gap: 0.5rem;">
        <h2>Live Database Records (SQL SELECT)</h2>
        <span id="records-counter" style="font-size: 0.85rem; color: #94a3b8;">Loading records...</span>
      </div>

      <!-- Live Search Box -->
      <div class="search-box-wrapper">
        <span class="search-icon">🔍</span>
        <input
          type="text"
          id="search-input"
          class="search-input"
          placeholder="Live search by project name or description in real-time..."
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

      <!-- Filter Chips -->
      <div class="filter-chips" id="filter-chips"></div>

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
            <tr>
              <td colspan="6" style="text-align: center; color: #64748b; padding: 2rem;">Loading projects...</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- SQL Explorer -->
    <div class="card">
      <h2>Interactive SQL Explorer</h2>
      <p style="color: #94a3b8; font-size: 0.85rem; marginBottom: 0.75rem;">
        Execute custom SQL SELECT queries directly against the Python SQLite database:
      </p>
      <div style="display: flex; gap: 0.75rem; flex-wrap: wrap;">
        <input
          type="text"
          id="sql-input"
          value="SELECT id, name, technology, status FROM projects"
          style="font-family: monospace; flex: 1; min-width: 260px;"
        />
        <button type="button" id="btn-run-sql">Execute SQL</button>
      </div>
      <pre id="sql-result" class="sql-box" style="display: none;"></pre>
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
    const clearSearchBtn = document.getElementById('clear-search-btn');
    const filterChipsContainer = document.getElementById('filter-chips');
    const searchMeta = document.getElementById('search-meta');
    const searchMetaText = document.getElementById('search-meta-text');
    const resetFiltersBtn = document.getElementById('reset-filters-btn');
    const statTotal = document.getElementById('stat-total');
    const statPort = document.getElementById('stat-port');
    const projectForm = document.getElementById('project-form');
    const sqlInput = document.getElementById('sql-input');
    const btnRunSql = document.getElementById('btn-run-sql');
    const sqlResult = document.getElementById('sql-result');

    // Display active port
    if (window.location.port) {
      statPort.textContent = ':' + window.location.port;
    }

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

    // Helper: Highlight matching query terms
    function highlight(text, query) {
      const safeText = escapeHtml(text);
      if (!query || !query.trim()) return safeText;
      const cleanQ = query.trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const regex = new RegExp('(' + cleanQ + ')', 'gi');
      return safeText.replace(regex, '<span class="highlight">$1</span>');
    }

    // Render Filter Chips
    function renderChips() {
      filterChipsContainer.innerHTML = techOptions.map(t => {
        const count = t === 'All'
          ? allProjects.length
          : allProjects.filter(p => p.technology === t).length;
        const activeClass = selectedTech === t ? 'active' : '';
        return '<button type="button" class="chip ' + activeClass + '" data-tech="' + t + '">' +
               t + ' (' + count + ')</button>';
      }).join('');

      // Add click handlers
      filterChipsContainer.querySelectorAll('.chip').forEach(btn => {
        btn.addEventListener('click', () => {
          selectedTech = btn.getAttribute('data-tech');
          renderTable();
          renderChips();
        });
      });
    }

    // Render Projects Table
    function renderTable() {
      const q = searchQuery.trim().toLowerCase();
      const filtered = allProjects.filter(p => {
        const matchSearch = !q ||
          p.name.toLowerCase().includes(q) ||
          (p.description && p.description.toLowerCase().includes(q));
        const matchTech = selectedTech === 'All' || p.technology === selectedTech;
        return matchSearch && matchTech;
      });

      // Update counter
      if (filtered.length === allProjects.length) {
        recordsCounter.textContent = 'Showing all ' + allProjects.length + ' records';
      } else {
        recordsCounter.textContent = 'Showing ' + filtered.length + ' of ' + allProjects.length + ' records';
      }

      // Update search meta info
      if (searchQuery || selectedTech !== 'All') {
        searchMeta.style.display = 'flex';
        let metaHtml = 'Filtering by: ';
        if (searchQuery) metaHtml += 'query "<strong>' + escapeHtml(searchQuery) + '</strong>" ';
        if (selectedTech !== 'All') metaHtml += 'technology "<strong>' + escapeHtml(selectedTech) + '</strong>"';
        searchMetaText.innerHTML = metaHtml;
      } else {
        searchMeta.style.display = 'none';
      }

      // Render table rows
      if (filtered.length === 0) {
        if (allProjects.length > 0) {
          projectsTbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: #94a3b8; padding: 2.5rem;">' +
            '🔍 No projects match your search for "' + escapeHtml(searchQuery) + '".' +
            '<br><button type="button" class="btn-link" id="empty-clear-btn" style="margin-top: 0.75rem;">Clear search filters</button>' +
            '</td></tr>';
          const emptyBtn = document.getElementById('empty-clear-btn');
          if (emptyBtn) emptyBtn.addEventListener('click', resetFilters);
        } else {
          projectsTbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: #64748b; padding: 2rem;">No records found in database.</td></tr>';
        }
        return;
      }

      projectsTbody.innerHTML = filtered.map(p => {
        return '<tr>' +
          '<td>#' + p.id + '</td>' +
          '<td style="font-weight: 600;">' + highlight(p.name, searchQuery) + '</td>' +
          '<td style="color: #94a3b8;">' + highlight(p.description, searchQuery) + '</td>' +
          '<td><span class="badge badge-py">' + escapeHtml(p.technology) + '</span></td>' +
          '<td><span class="status-badge">' + escapeHtml(p.status) + '</span></td>' +
          '<td><button type="button" class="btn-danger" data-id="' + p.id + '">Delete</button></td>' +
          '</tr>';
      }).join('');

      // Attach delete listeners
      projectsTbody.querySelectorAll('.btn-danger').forEach(btn => {
        btn.addEventListener('click', () => {
          const id = btn.getAttribute('data-id');
          deleteProject(id);
        });
      });
    }

    // Reset all filters
    function resetFilters() {
      searchQuery = '';
      selectedTech = 'All';
      searchInput.value = '';
      clearSearchBtn.style.display = 'none';
      renderTable();
      renderChips();
    }
    resetFiltersBtn.addEventListener('click', resetFilters);

    // Live search input handler
    searchInput.addEventListener('input', (e) => {
      searchQuery = e.target.value;
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

    // Fetch API Data
    async function fetchProjects() {
      try {
        const res = await fetch('/api/projects');
        allProjects = await res.json();
        renderTable();
        renderChips();
      } catch (err) {
        console.error('Error fetching projects:', err);
        projectsTbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:#ef4444; padding:2rem;">Error connecting to Python backend.</td></tr>';
      }
    }

    async function fetchStats() {
      try {
        const res = await fetch('/api/stats');
        const data = await res.json();
        statTotal.textContent = data.total || 0;
      } catch (err) {
        console.error('Error fetching stats:', err);
      }
    }

    // Insert New Project
    projectForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const nameInput = document.getElementById('proj-name');
      const descInput = document.getElementById('proj-desc');
      const techInput = document.getElementById('proj-tech');
      const btnSubmit = document.getElementById('btn-submit');

      const name = nameInput.value.trim();
      const desc = descInput.value.trim();
      const tech = techInput.value;
      if (!name) return;

      btnSubmit.disabled = true;
      btnSubmit.textContent = 'Inserting...';

      try {
        await fetch('/api/projects', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, description: desc, technology: tech })
        });
        nameInput.value = '';
        descInput.value = '';
        await fetchProjects();
        await fetchStats();
      } catch (err) {
        alert('Error saving project: ' + err.message);
      } finally {
        btnSubmit.disabled = false;
        btnSubmit.textContent = '+ Insert into SQL';
      }
    });

    // Delete Project
    async function deleteProject(id) {
      try {
        await fetch('/api/projects/' + id, { method: 'DELETE' });
        await fetchProjects();
        await fetchStats();
      } catch (err) {
        alert('Error deleting project: ' + err.message);
      }
    }

    // Execute Raw SQL Query
    btnRunSql.addEventListener('click', async () => {
      const query = sqlInput.value.trim();
      if (!query) return;

      try {
        const res = await fetch('/api/raw-sql', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query })
        });
        const data = await res.json();
        sqlResult.style.display = 'block';
        sqlResult.textContent = JSON.stringify(data, null, 2);
      } catch (err) {
        sqlResult.style.display = 'block';
        sqlResult.textContent = 'Error: ' + err.message;
      }
    });

    // Initial instant render from pre-loaded SQLite data
    renderChips();
    renderTable();

    // Background live refreshes
    fetchProjects();
    fetchStats();
  </script>
</body>
</html>
"""
        html = html.replace("__INITIAL_PROJECTS__", initial_json).replace("__TOTAL_COUNT__", str(total_count))
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
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
