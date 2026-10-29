package com.aitradinglab.engine;

import org.junit.After;
import org.junit.Test;

import java.lang.reflect.Field;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

/**
 * v3.0.2 P0 SECURITY REGRESSION TEST (host-side JUnit).
 *
 * Guards the loopback-only dashboard binding introduced in v3.0.2:
 * the old code `new ServerSocket(PORT)` bound the WILDCARD address, exposing the
 * dashboard + JSON API to every device on the phone's network. These tests fail
 * against the old implementation (isAnyLocalAddress == true) and pass only when
 * the listener is explicitly bound to 127.0.0.1:8788.
 *
 * Scope note: this proves JVM/OS-level socket semantics on the host (Linux) —
 * the exact java.net code path Android runs. On-device instrumentation (emulator
 * or real handset) is a separate, manual verification step (see release notes).
 */
public class HttpServerLoopbackTest {

    private HttpServer srv;

    @After public void tearDown() {
        if (srv != null) { srv.stop(); srv = null; }
    }

    private ServerSocket socketOf(HttpServer s) throws Exception {
        Field f = HttpServer.class.getDeclaredField("server");
        f.setAccessible(true);
        return (ServerSocket) f.get(s);
    }

    @Test public void port_is_unchanged_8788() {
        // WebView + ConnectActivity probe depend on this exact port
        assertEquals(8788, HttpServer.PORT);
    }

    @Test public void binds_loopback_only_not_wildcard() throws Exception {
        srv = new HttpServer(null);   // Api is not needed for binding
        srv.start();
        ServerSocket ss = socketOf(srv);
        assertTrue("listener must be bound", ss.isBound());
        InetAddress a = ss.getInetAddress();
        assertTrue("bind address must be loopback (got " + a + ")", a.isLoopbackAddress());
        assertFalse("must NOT bind wildcard/all interfaces (0.0.0.0)", a.isAnyLocalAddress());
        assertEquals("must be IPv4 loopback 127.0.0.1", "127.0.0.1", a.getHostAddress());
    }

    @Test public void loopback_connection_is_accepted() throws Exception {
        srv = new HttpServer(null);
        srv.start();
        Socket s = new Socket();
        s.setSoTimeout(5000);
        s.connect(new java.net.InetSocketAddress(InetAddress.getByName("127.0.0.1"), HttpServer.PORT), 3000);
        assertTrue("connect to 127.0.0.1:8788 must succeed", s.isConnected());
        // Send a minimal request; the acceptor must pick up the connection and the
        // handler must process it. Api==null makes route() throw -> handler catches
        // and closes the socket -> the client observes EOF. Reaching EOF proves the
        // full accept -> parse -> dispatch -> close pipeline ran on the loopback peer.
        s.getOutputStream().write("GET /api/health HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n".getBytes("UTF-8"));
        s.getOutputStream().flush();
        int r = s.getInputStream().read();
        assertEquals("server should close the connection after handling (EOF)", -1, r);
        s.close();
    }

    @Test public void stop_releases_listener() throws Exception {
        srv = new HttpServer(null);
        srv.start();
        ServerSocket ss = socketOf(srv);
        srv.stop();
        assertTrue("listener socket must be closed after stop()", ss.isClosed());
    }

    // ---- v3.0.3 P1: request-size cap (local OOM-DoS guard) ----

    private String readHead(Socket s) throws Exception {
        byte[] buf = new byte[4096];
        int n = s.getInputStream().read(buf);
        return n < 0 ? "" : new String(buf, 0, n, "UTF-8");
    }

    private Socket openLoopback() throws Exception {
        Socket s = new Socket();
        s.setSoTimeout(5000);
        s.connect(new java.net.InetSocketAddress(InetAddress.getByName("127.0.0.1"), HttpServer.PORT), 3000);
        return s;
    }

    @Test public void oversized_content_length_rejected_413_without_allocation() throws Exception {
        srv = new HttpServer(null);
        srv.start();
        Socket s = openLoopback();
        // Declares ~2 GB. The pre-cap handler would have tried `new char[2000000000]`
        // -> OutOfMemoryError -> engine process death (local DoS). Must be 413 instead.
        s.getOutputStream().write("POST /api/settings HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 2000000000\r\n\r\n".getBytes("UTF-8"));
        s.getOutputStream().flush();
        String head = readHead(s);
        assertTrue("expected 413 for oversized Content-Length, got: " + head,
                head.startsWith("HTTP/1.1 413"));
        s.close();
    }

    @Test public void malformed_content_length_rejected_413() throws Exception {
        srv = new HttpServer(null);
        srv.start();
        Socket s = openLoopback();
        // Non-numeric Content-Length used to throw NumberFormatException inside the
        // header loop -> unhandled in the parser -> connection dropped with no reply.
        s.getOutputStream().write("POST /api/settings HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: abc\r\n\r\n".getBytes("UTF-8"));
        s.getOutputStream().flush();
        String head = readHead(s);
        assertTrue("expected 413 for malformed Content-Length, got: " + head,
                head.startsWith("HTTP/1.1 413"));
        s.close();
    }

    @Test public void normal_small_body_still_accepted_pipeline() throws Exception {
        srv = new HttpServer(null);
        srv.start();
        Socket s = openLoopback();
        // Small well-formed body: the cap must NOT interfere. With Api==null the
        // route() call fails internally and the socket closes (EOF) — reaching that
        // EOF proves the body was accepted and dispatched past the size gate.
        s.getOutputStream().write("POST /api/health HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 2\r\n\r\n{}".getBytes("UTF-8"));
        s.getOutputStream().flush();
        int r = s.getInputStream().read();
        assertEquals("small body must pass the size gate (EOF after dispatch)", -1, r);
        s.close();
    }
}
