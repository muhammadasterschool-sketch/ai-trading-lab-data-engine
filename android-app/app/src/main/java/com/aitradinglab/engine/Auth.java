package com.aitradinglab.engine;

import android.database.Cursor;
import java.security.MessageDigest;
import java.security.SecureRandom;
import javax.crypto.Mac;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import javax.crypto.spec.SecretKeySpec;

/* loaded from: classes.dex */
public class Auth {
    private static final char[] B32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567".toCharArray();
    private static final SecureRandom RND = new SecureRandom();

    public static String hashPw(String str) {
        byte[] bArr = new byte[16];
        RND.nextBytes(bArr);
        return "pbkdf2:" + hex(bArr) + ":" + hex(pbkdf2(str, bArr, 120000, 32));
    }

    public static boolean verifyPw(String str, String str2) {
        try {
            String[] split = str2.split(":");
            if (!"pbkdf2".equals(split[0])) {
                return false;
            }
            return MessageIsEqual(unhex(split[2]), pbkdf2(str, unhex(split[1]), 120000, 32));
        } catch (Exception unused) {
            return false;
        }
    }

    private static boolean MessageIsEqual(byte[] bArr, byte[] bArr2) {
        return MessageDigest.isEqual(bArr, bArr2);
    }

    private static byte[] pbkdf2(String str, byte[] bArr, int i, int i2) {
        try {
            return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(new PBEKeySpec(str.toCharArray(), bArr, i, i2 * 8)).getEncoded();
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }

    public static String token() {
        byte[] bArr = new byte[32];
        RND.nextBytes(bArr);
        return hex(bArr);
    }

    public static String totpSecret() {
        return base32(randomBytes(20));
    }

    public static String newInviteCode() {
        StringBuilder sb = new StringBuilder(8);
        for (int i = 0; i < 8; i++) {
            sb.append("ABCDEFGHJKMNPQRSTUVWXYZ23456789".charAt(RND.nextInt(31)));
        }
        return sb.toString();
    }

    private static byte[] randomBytes(int i) {
        byte[] bArr = new byte[i];
        RND.nextBytes(bArr);
        return bArr;
    }

    public static String base32(byte[] bArr) {
        StringBuilder sb = new StringBuilder();
        int i = 0;
        int i2 = 0;
        for (byte b : bArr) {
            i2 = (i2 << 8) | (b & 255);
            i += 8;
            while (i >= 5) {
                sb.append(B32[(i2 >>> (i - 5)) & 31]);
                i -= 5;
            }
        }
        if (i > 0) {
            sb.append(B32[(i2 << (5 - i)) & 31]);
        }
        return sb.toString();
    }

    public static byte[] base32Decode(String str) {
        String replaceAll = str.toUpperCase().replaceAll("=+$", "").replaceAll("\\s", "");
        StringBuilder sb = new StringBuilder();
        int i = 0;
        int i2 = 0;
        for (char c : replaceAll.toCharArray()) {
            int indexOf = new String(B32).indexOf(c);
            if (indexOf >= 0) {
                i = (i << 5) | indexOf;
                int i3 = i2 + 5;
                if (i3 >= 8) {
                    sb.append((char) ((i >>> (i2 - 3)) & 255));
                    i2 -= 3;
                } else {
                    i2 = i3;
                }
            }
        }
        byte[] bArr = new byte[sb.length()];
        for (int i4 = 0; i4 < sb.length(); i4++) {
            bArr[i4] = (byte) sb.charAt(i4);
        }
        return bArr;
    }

    public static boolean verifyTotp(String str, String str2) {
        String replaceAll = str2 != null ? str2.replaceAll("\\D", "") : "";
        if (replaceAll.length() != 6) {
            return false;
        }
        long currentTimeMillis = (System.currentTimeMillis() / 1000) / 30;
        for (int i = -1; i <= 1; i++) {
            if (hotp(base32Decode(str), i + currentTimeMillis).equals(replaceAll)) {
                return true;
            }
        }
        return false;
    }

    private static String hotp(byte[] bArr, long j) {
        try {
            byte[] bArr2 = new byte[8];
            for (int i = 7; i >= 0; i--) {
                bArr2[i] = (byte) (255 & j);
                j >>>= 8;
            }
            Mac mac = Mac.getInstance("HmacSHA1");
            mac.init(new SecretKeySpec(bArr, "HmacSHA1"));
            byte[] doFinal = mac.doFinal(bArr2);
            int i2 = doFinal[doFinal.length - 1] & 15;
            return String.format("%06d", Integer.valueOf(((doFinal[i2 + 3] & 255) | ((((doFinal[i2] & Byte.MAX_VALUE) << 24) | ((doFinal[i2 + 1] & 255) << 16)) | ((doFinal[i2 + 2] & 255) << 8))) % 1000000));
        } catch (Exception unused) {
            return "000000";
        }
    }

    public static String hex(byte[] bArr) {
        StringBuilder sb = new StringBuilder();
        for (byte b : bArr) {
            sb.append(String.format("%02x", Byte.valueOf(b)));
        }
        return sb.toString();
    }

    public static byte[] unhex(String str) {
        int length = str.length() / 2;
        byte[] bArr = new byte[length];
        for (int i = 0; i < length; i++) {
            int i2 = i * 2;
            bArr[i] = (byte) Integer.parseInt(str.substring(i2, i2 + 2), 16);
        }
        return bArr;
    }

    public static String checkInvite(Db db, String str) {
        int i = 0;
        int i2 = 0;
        String upperCase = str == null ? "" : str.trim().toUpperCase();
        if (upperCase.isEmpty()) {
            return "Invitation code required — this engine is invite-only";
        }
        boolean z = true;
        int i3 = 0;
        Cursor rawQuery = db.getReadableDatabase().rawQuery("SELECT max_uses, uses, active FROM invites WHERE code=?", new String[]{upperCase});
        if (rawQuery.moveToFirst()) {
            int i4 = rawQuery.getInt(0);
            i2 = rawQuery.getInt(1);
            i = i4;
            i3 = rawQuery.getInt(2);
        } else {
            z = false;
            i = 0;
            i2 = 0;
        }
        rawQuery.close();
        if (!z || i3 == 0) {
            return "Invalid or deactivated invitation code";
        }
        if (i > 0 && i2 >= i) {
            return "This invitation code has reached its usage limit";
        }
        db.getWritableDatabase().execSQL("UPDATE invites SET uses=uses+1 WHERE code=?", new Object[]{upperCase});
        return null;
    }
}
