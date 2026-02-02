import http.server
import socketserver

PORT = 8080

class CORSRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'X-Requested-With, Content-Type, Accept')
        http.server.SimpleHTTPRequestHandler.end_headers(self)

if __name__ == "__main__":
    import os
    os.chdir(os.path.dirname(__file__))
    with socketserver.TCPServer(("", PORT), CORSRequestHandler) as httpd:
        print(f"Serving frontend at http://localhost:{PORT}")
        httpd.serve_forever()
