import http.server, socketserver

class H(http.server.SimpleHTTPRequestHandler):
    # Disable keep-alive so connections don't pile up
    protocol_version = "HTTP/1.0"
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("Connection", "close")
        super().end_headers()

# ThreadingHTTPServer handles concurrent requests; SimpleHTTPServer blocks
class TS(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

with TS(("", 7878), H) as httpd:
    print("serving on http://localhost:7878 (threaded, no-store)")
    httpd.serve_forever()
