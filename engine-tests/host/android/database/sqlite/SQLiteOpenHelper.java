package android.database.sqlite;
import android.content.Context;
import android.database.Cursor;
public abstract class SQLiteOpenHelper {
    private final String path;
    private final int version;
    private SQLiteDatabase db;
    protected SQLiteOpenHelper(Context ctx, String name, SQLiteDatabase.CursorFactory factory, int version) {
        this.path = ctx.getDatabasePath(name).getAbsolutePath();
        this.version = version;
    }
    public synchronized SQLiteDatabase getWritableDatabase() { return open(); }
    public synchronized SQLiteDatabase getReadableDatabase() { return open(); }
    private SQLiteDatabase open() {
        if (db != null) return db;
        db = new SQLiteDatabase(path);
        int userVersion = 0;
        Cursor c = db.rawQuery("PRAGMA user_version", null);
        if (c.moveToFirst()) userVersion = c.getInt(0);
        c.close();
        onConfigure(db);
        if (userVersion == 0) {
            onCreate(db);
            db.execSQL("PRAGMA user_version=" + version);
        } else if (userVersion < version) {
            onUpgrade(db, userVersion, version);
            db.execSQL("PRAGMA user_version=" + version);
        }
        return db;
    }
    public abstract void onCreate(SQLiteDatabase d);
    public abstract void onUpgrade(SQLiteDatabase d, int oldVersion, int newVersion);
    public void onConfigure(SQLiteDatabase d) { }
    public synchronized void close() { if (db != null) { db.close(); db = null; } }
}
