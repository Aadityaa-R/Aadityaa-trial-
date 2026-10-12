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
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

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
            cursor.execute("SELECT * FROM projects ORDER BY id DESC")
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
        html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Python + SQL + React Web App</title>
  <script src="https://unpkg.com/react@18/umd/react.development.js" crossorigin></script>
  <script src="https://unpkg.com/react-dom@18/umd/react-dom.development.js" crossorigin></script>
  <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    body { background: #0f172a; color: #f8fafc; min-height: 100vh; padding: 2rem 1rem; }
    .container { max-width: 900px; margin: 0 auto; }
    header { margin-bottom: 2rem; border-bottom: 1px solid #1e293b; padding-bottom: 1.5rem; display: flex; justify-content: space-between; align-items: center; }
    h1 { font-size: 1.8rem; font-weight: 700; color: #38bdf8; }
    .badges { display: flex; gap: 0.5rem; }
    .badge { padding: 0.35rem 0.75rem; border-radius: 9999px; font-size: 0.8rem; font-weight: 600; }
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
    .btn-danger { background: #ef4444; color: white; padding: 0.4rem 0.8rem; font-size: 0.85rem; }
    .btn-danger:hover { background: #dc2626; }
    .table-container { overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; text-align: left; }
    th, td { padding: 0.85rem; border-bottom: 1px solid #334155; }
    th { color: #94a3b8; font-weight: 600; font-size: 0.85rem; text-transform: uppercase; }
    .status-badge { display: inline-block; padding: 0.25rem 0.6rem; border-radius: 0.35rem; font-size: 0.75rem; font-weight: 600; background: #065f46; color: #6ee7b7; }
    .sql-box { background: #090d16; padding: 1rem; border-radius: 0.5rem; font-family: monospace; color: #a5f3fc; margin-bottom: 1rem; border: 1px solid #1e293b; }
    .stats-bar { display: flex; gap: 1rem; margin-bottom: 1.5rem; }
    .stat-item { flex: 1; background: #1e293b; padding: 1rem; border-radius: 0.5rem; border: 1px solid #334155; text-align: center; }
    .stat-val { font-size: 1.5rem; font-weight: 700; color: #38bdf8; }
    .stat-lbl { font-size: 0.8rem; color: #94a3b8; margin-top: 0.25rem; }
  </style>
</head>
<body>
  <div id="root"></div>

  <script type="text/babel">
    const { useState, useEffect } = React;

    function App() {
      const [projects, setProjects] = useState([]);
      const [stats, setStats] = useState({ total: 0 });
      const [name, setName] = useState('');
      const [desc, setDesc] = useState('');
      const [tech, setTech] = useState('Python');
      const [sqlQuery, setSqlQuery] = useState('SELECT id, name, technology, status FROM projects');
      const [sqlResult, setSqlResult] = useState(null);
      const [loading, setLoading] = useState(false);

      const fetchProjects = async () => {
        try {
          const res = await fetch('/api/projects');
          const data = await res.json();
          setProjects(data);
        } catch (err) {
          console.error('Error fetching projects:', err);
        }
      };

      const fetchStats = async () => {
        try {
          const res = await fetch('/api/stats');
          const data = await res.json();
          setStats(data);
        } catch (err) {
          console.error('Error fetching stats:', err);
        }
      };

      useEffect(() => {
        fetchProjects();
        fetchStats();
      }, []);

      const handleSubmit = async (e) => {
        e.preventDefault();
        if (!name.trim()) return;
        setLoading(true);
        try {
          await fetch('/api/projects', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, description: desc, technology: tech })
          });
          setName('');
          setDesc('');
          fetchProjects();
          fetchStats();
        } catch (err) {
          console.error('Error saving project:', err);
        } finally {
          setLoading(false);
        }
      };

      const handleDelete = async (id) => {
        try {
          await fetch(`/api/projects/${id}`, { method: 'DELETE' });
          fetchProjects();
          fetchStats();
        } catch (err) {
          console.error('Error deleting project:', err);
        }
      };

      const runSql = async () => {
        try {
          const res = await fetch('/api/raw-sql', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: sqlQuery })
          });
          const data = await res.json();
          setSqlResult(data);
        } catch (err) {
          setSqlResult({ error: err.message });
        }
      };

      return (
        <div className="container">
          <header>
            <div>
              <h1>Full-Stack Web App</h1>
              <p style={{ color: '#94a3b8', fontSize: '0.9rem', marginTop: '0.25rem' }}>
                Python Backend (HTTP REST) + SQL Database (SQLite) + React UI
              </p>
            </div>
            <div className="badges">
              <span className="badge badge-py">Python 3</span>
              <span className="badge badge-sql">SQLite SQL</span>
              <span className="badge badge-react">React 18</span>
            </div>
          </header>

          <div className="stats-bar">
            <div className="stat-item">
              <div className="stat-val">{stats.total || 0}</div>
              <div className="stat-lbl">Total Records in SQL DB</div>
            </div>
            <div className="stat-item">
              <div className="stat-val">Online</div>
              <div className="stat-lbl">Python Server Status</div>
            </div>
            <div className="stat-item">
              <div className="stat-val">:{window.location.port || '5050'}</div>
              <div className="stat-lbl">Active Port</div>
            </div>
          </div>

          <div className="card">
            <h2>Add New Project (SQL INSERT)</h2>
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <input
                  type="text"
                  placeholder="Project Name (e.g. Authentication Module)"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                />
                <input
                  type="text"
                  placeholder="Description"
                  value={desc}
                  onChange={(e) => setDesc(e.target.value)}
                />
                <select value={tech} onChange={(e) => setTech(e.target.value)}>
                  <option value="Python">Python</option>
                  <option value="SQL">SQL</option>
                  <option value="React">React</option>
                  <option value="Fullstack">Fullstack</option>
                </select>
                <button type="submit" disabled={loading}>
                  {loading ? 'Inserting...' : '+ Insert into SQL'}
                </button>
              </div>
            </form>
          </div>

          <div className="card">
            <h2>Live Database Records (SQL SELECT)</h2>
            <div className="table-container">
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
                <tbody>
                  {projects.map((p) => (
                    <tr key={p.id}>
                      <td>#{p.id}</td>
                      <td style={{ fontWeight: 600 }}>{p.name}</td>
                      <td style={{ color: '#94a3b8' }}>{p.description}</td>
                      <td><span className="badge badge-py">{p.technology}</span></td>
                      <td><span className="status-badge">{p.status}</span></td>
                      <td>
                        <button className="btn-danger" onClick={() => handleDelete(p.id)}>
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                  {projects.length === 0 && (
                    <tr>
                      <td colSpan="6" style={{ textAlign: 'center', color: '#64748b', padding: '2rem' }}>
                        No records found in database.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="card">
            <h2>Interactive SQL Explorer</h2>
            <p style={{ color: '#94a3b8', fontSize: '0.85rem', marginBottom: '0.75rem' }}>
              Execute custom SQL SELECT queries directly against the Python SQLite database:
            </p>
            <div style={{ display: 'flex', gap: '0.75rem' }}>
              <input
                type="text"
                value={sqlQuery}
                onChange={(e) => setSqlQuery(e.target.value)}
                style={{ fontFamily: 'monospace' }}
              />
              <button onClick={runSql}>Execute SQL</button>
            </div>
            {sqlResult && (
              <pre className="sql-box" style={{ marginTop: '1rem' }}>
                {JSON.stringify(sqlResult, null, 2)}
              </pre>
            )}
          </div>
        </div>
      );
    }

    const root = ReactDOM.createRoot(document.getElementById('root'));
    root.render(<App />);
  </script>
</body>
</html>
"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

def run():
    with socketserver.TCPServer(("", PORT), RequestHandler) as httpd:
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
