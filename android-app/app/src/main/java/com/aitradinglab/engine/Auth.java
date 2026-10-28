package com.aitradinglab.engine;

import android.database.Cursor;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Mac;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import javax.crypto.spec.SecretKeySpec;

/** Auth: PBKDF2 passwords, TOTP 2FA (RFC 6238), invite codes, sessions. */
public class Auth {
    private static final char[] B32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567".toCharArray();
    private static final SecureRandom RND = new SecureRandom();

    // ---------- passwords: PBKDF2WithHmacSHA256 ----------
    public static String hashPw(String password) {
        byte[] salt = new byte[16]; RND.nextBytes(salt);
        byte[] dk = pbkdf2(password, salt, 120000, 32);
        return "pbkdf2:" + hex(salt) + ":" + hex(dk);
    }

    public static boolean verifyPw(String password, String stored) {
        try {
            String[] p = stored.split(":");
            if (!"pbkdf2".equals(p[0])) return false;
            byte[] salt = unhex(p[1]);
            byte[] expect = unhex(p[2]);
            byte[] got = pbkdf2(password, salt, 120000, 32);
            return MessageIsEqual(expect, got);
        } catch (Exception e) { return false; }
    }

    private static boolean MessageIsEqual(byte[] a, byte[] b) {
        return java.security.MessageDigest.isEqual(a, b);
    }

    private static byte[] pbkdf2(String pw, byte[] salt, int iters, int len) {
        try {
            PBEKeySpec spec = new PBEKeySpec(pw.toCharArray(), salt, iters, len * 8);
            return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).getEncoded();
        } catch (Exception e) { throw new RuntimeException(e); }
    }

    // ---------- tokens / secrets ----------
    public static String token() {
        byte[] b = new byte[32]; RND.nextBytes(b);
        return hex(b);
    }

    public static String totpSecret() { return base32(randomBytes(20)); }

    /**
     * v5.7: human-friendly invite code for the owner's Control tab — 8 chars from an
     * unambiguous alphabet (no 0/O, 1/I/L confusion), SecureRandom, e.g. "K7RM2X9B".
     */
    public static String newInviteCode() {
        String alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789";
        StringBuilder sb = new StringBuilder(8);
        for (int i = 0; i < 8; i++) sb.append(alphabet.charAt(RND.nextInt(alphabet.length())));
        return sb.toString();
    }

    private static byte[] randomBytes(int n) { byte[] b = new byte[n]; RND.nextBytes(b); return b; }

    // ---------- base32 ----------
    public static String base32(byte[] data) {
        StringBuilder out = new StringBuilder();
        int bits = 0, value = 0;
        for (byte x : data) { value = (value << 8) | (x & 0xff); bits += 8;
            while (bits >= 5) { out.append(B32[(value >>> (bits - 5)) & 31]); bits -= 5; } }
        if (bits > 0) out.append(B32[(value << (5 - bits)) & 31]);
        return out.toString();
    }

    public static byte[] base32Decode(String str) {
        String clean = str.toUpperCase().replaceAll("=+$", "").replaceAll("\\s", "");
        int bits = 0, value = 0; StringBuilder out = new StringBuilder();
        for (char ch : clean.toCharArray()) {
            int idx = new String(B32).indexOf(ch);
            if (idx < 0) continue;
            value = (value << 5) | idx; bits += 5;
            if (bits >= 8) { out.append((char) ((value >>> (bits - 8)) & 0xff)); bits -= 8; }
        }
        byte[] res = new byte[out.length()];
        for (int i = 0; i < out.length(); i++) res[i] = (byte) out.charAt(i);
        return res;
    }

    // ---------- TOTP ----------
    public static boolean verifyTotp(String secretB32, String code) {
        String clean = code == null ? "" : code.replaceAll("\\D", "");
        if (clean.length() != 6) return false;
        long step = System.currentTimeMillis() / 1000 / 30;
        for (int i = -1; i <= 1; i++) {
            if (hotp(base32Decode(secretB32), step + i).equals(clean)) return true;
        }
        return false;
    }

    private static String hotp(byte[] key, long counter) {
        try {
            byte[] buf = new byte[8];
            for (int i = 7; i >= 0; i--) { buf[i] = (byte) (counter & 0xff); counter >>>= 8; }
            Mac mac = Mac.getInstance("HmacSHA1");
            mac.init(new SecretKeySpec(key, "HmacSHA1"));
            byte[] h = mac.doFinal(buf);
            int off = h[h.length - 1] & 0x0f;
            int code = ((h[off] & 0x7f) << 24) | ((h[off + 1] & 0xff) << 16) | ((h[off + 2] & 0xff) << 8) | (h[off + 3] & 0xff);
            return String.format("%06d", code % 1000000);
        } catch (Exception e) { return "000000"; }
    }

    // ---------- hex ----------
    public static String hex(byte[] b) {
        StringBuilder s = new StringBuilder();
        for (byte x : b) s.append(String.format("%02x", x));
        return s.toString();
    }

    public static byte[] unhex(String s) {
        byte[] r = new byte[s.length() / 2];
        for (int i = 0; i < r.length; i++) r[i] = (byte) Integer.parseInt(s.substring(i * 2, i * 2 + 2), 16);
        return r;
    }

    /** Validate invite code and consume one use. Returns error message or null on success. */
    public static String checkInvite(Db db, String code) {
        String raw = code == null ? "" : code.trim().toUpperCase();
        if (raw.isEmpty()) return "Invitation code required — this engine is invite-only";
        Cursor c = db.getReadableDatabase().rawQuery("SELECT max_uses, uses, active FROM invites WHERE code=?", new String[]{raw});
        boolean ok = false; int maxUses = 0, uses = 0, active = 0;
        if (c.moveToFirst()) { maxUses = c.getInt(0); uses = c.getInt(1); active = c.getInt(2); ok = true; }
        c.close();
        if (!ok || active == 0) return "Invalid or deactivated invitation code";
        if (maxUses > 0 && uses >= maxUses) return "This invitation code has reached its usage limit";
        db.getWritableDatabase().execSQL("UPDATE invites SET uses=uses+1 WHERE code=?", new Object[]{raw});
        return null;
    }
}
