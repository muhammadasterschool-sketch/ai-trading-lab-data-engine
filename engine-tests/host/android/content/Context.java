package android.content;
public class Context {
    public static final String POWER_SERVICE = "power";
    public static final String NOTIFICATION_SERVICE = "notification";
    public static final String ALARM_SERVICE = "alarm";
    private java.io.File dbRoot = new java.io.File("/tmp/atl-host");
    public void setDbRoot(java.io.File f) { dbRoot = f; }
    public android.content.Context getApplicationContext() { return this; }
    public java.io.File getDatabasePath(String name) { return new java.io.File(dbRoot, name); }
    public java.io.File getFilesDir() { return dbRoot; }
    public String getPackageName() { return "com.aitradinglab.host"; }
    public Object getSystemService(String name) { return null; }
    public android.content.res.AssetManager getAssets() { return new android.content.res.AssetManager(); }
}
