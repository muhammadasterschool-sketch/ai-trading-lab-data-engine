package android.util;
public class Log {
    public static int v(String t, String m) { return emit("V", t, m); }
    public static int d(String t, String m) { return emit("D", t, m); }
    public static int i(String t, String m) { return emit("I", t, m); }
    public static int w(String t, String m) { return emit("W", t, m); }
    public static int e(String t, String m) { return emit("E", t, m); }
    public static int w(String t, String m, Throwable x) { return emit("W", t, m + " :: " + x); }
    public static int e(String t, String m, Throwable x) { return emit("E", t, m + " :: " + x); }
    private static int emit(String lv, String t, String m) { System.out.println("[" + lv + "/" + t + "] " + m); return 0; }
}
