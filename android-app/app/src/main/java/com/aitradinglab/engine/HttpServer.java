package com.aitradinglab.engine;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;
import org.json.JSONArray;
import org.json.JSONObject;

/** Minimal HTTP/1.1 server (no deps) hosting the dashboard + JSON API on 127.0.0.1:8788. */
public class HttpServer {
    public static final int PORT = 8788;
    private final Api api;
    private ServerSocket server;
    private volatile boolean running;

    public HttpServer(Api api) { this.api = api; }

    public void start() throws IOException {
        server = new ServerSocket(PORT);
        running = true;
        Thread acceptor = new Thread(() -> {
            while (running) {
                try {
                    Socket s = server.accept();
                    Thread t = new Thread(() -> handle(s));
                    t.setDaemon(true);
                    t.start();
                } catch (IOException ignored) { }
            }
        }, "http-acceptor");
        acceptor.setDaemon(true);
        acceptor.start();
    }

    public void stop() {
        running = false;
        try { if (server != null) server.close(); } catch (IOException ignored) { }
    }

    private void handle(Socket s) {
        try {
            BufferedReader in = new BufferedReader(new InputStreamReader(s.getInputStream(), StandardCharsets.UTF_8));
            String line = in.readLine();
            if (line == null) { s.close(); return; }
            String[] parts = line.split(" ");
            if (parts.length < 2) { s.close(); return; }
            String method = parts[0], path = parts[1];

            Map<String, String> headers = new HashMap<>();
            String h;
            int contentLength = 0;
            while ((h = in.readLine()) != null && !h.isEmpty()) {
                int c = h.indexOf(':');
                if (c > 0) {
                    String key = h.substring(0, c).trim().toLowerCase();
                    String val = h.substring(c + 1).trim();
                    headers.put(key, val);
                    if ("content-length".equals(key)) contentLength = Integer.parseInt(val);
                }
            }
            StringBuilder body = new StringBuilder();
            if (contentLength > 0) {
                char[] buf = new char[contentLength];
                int read = 0;
                while (read < contentLength) {
                    int n = in.read(buf, read, contentLength - read);
                    if (n < 0) break;
                    read += n;
                }
                body.append(buf, 0, read);
            }

            Api.Res res = api.route(method, path, headers.get("authorization"), body.toString());
            respond(s, res);
        } catch (Exception ignored) {
        } finally {
            try { s.close(); } catch (IOException ignored) { }
        }
    }

    private void respond(Socket s, Api.Res res) throws IOException {
        byte[] body = res.body == null ? new byte[0] : res.body.getBytes(StandardCharsets.UTF_8);
        OutputStream out = s.getOutputStream();
        StringBuilder head = new StringBuilder();
        head.append("HTTP/1.1 ").append(res.status).append(" OK\r\n");
        head.append("Content-Type: ").append(res.contentType).append("\r\n");
        head.append("Content-Length: ").append(body.length).append("\r\n");
        head.append("Cache-Control: no-store\r\n");
        head.append("Access-Control-Allow-Origin: *\r\n");
        head.append("Connection: close\r\n\r\n");
        out.write(head.toString().getBytes(StandardCharsets.UTF_8));
        out.write(body);
        out.flush();
    }

    /** JSON helpers */
    static JSONObject jObj(String raw) {
        try { return new JSONObject(raw == null ? "" : raw); } catch (Exception e) { return new JSONObject(); }
    }

    static String jStr(JSONObject o, String k) {
        String v = o.optString(k, "");
        return v == null ? "" : v.trim();
    }
}
