#!/usr/bin/env python3
"""
Simple HTTP server to serve the frontend locally.
This avoids CORS issues by serving both frontend and backend from the same origin.
"""
import http.server
import socketserver
import os
import sys

class CORSRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Custom request handler that adds CORS headers."""

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def do_OPTIONS(self):
        """Handle preflight requests."""
        self.send_response(200)
        self.end_headers()

def find_available_port(start_port=8000, max_attempts=10):
    """Find an available port starting from start_port."""
    import socket
    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('', port))
                return port
        except OSError:
            continue
    raise OSError("No available ports found")

def main():
    """Start the development server."""
    port = find_available_port(8000)

    # Change to frontend directory
    frontend_dir = os.path.join(os.path.dirname(__file__), 'frontend')
    if not os.path.exists(frontend_dir):
        print(f"Error: Frontend directory not found: {frontend_dir}")
        sys.exit(1)

    os.chdir(frontend_dir)

    with socketserver.TCPServer(("", port), CORSRequestHandler) as httpd:
        print(f"🚀 Frontend server running at http://localhost:{port}")
        print(f"📁 Serving files from: {frontend_dir}")
        print("💡 Open your browser to the URL above")
        print("💡 Backend API should be running on http://localhost:5000")
        print("Press Ctrl+C to stop the server")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n👋 Server stopped")
            httpd.shutdown()

if __name__ == '__main__':
    main()