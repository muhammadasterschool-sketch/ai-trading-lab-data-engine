package android.database;
import java.sql.ResultSet;
import java.sql.Statement;
public class JdbcCursor implements Cursor {
    private final ResultSet rs;
    private final Statement st;
    private boolean started = false;
    private boolean haveRow = false;
    private boolean closed = false;
    public JdbcCursor(ResultSet rs, Statement st) { this.rs = rs; this.st = st; }
    private void advance() {
        if (closed) { haveRow = false; return; }
        try { haveRow = rs.next(); } catch (Exception e) { haveRow = false; }
    }
    public boolean moveToFirst() { if (!started) { started = true; advance(); } return haveRow; }
    public boolean moveToNext() { started = true; advance(); return haveRow; }
    public int getInt(int i) { try { return rs.getInt(i + 1); } catch (Exception e) { return 0; } }
    public long getLong(int i) { try { return rs.getLong(i + 1); } catch (Exception e) { return 0L; } }
    public double getDouble(int i) { try { return rs.getDouble(i + 1); } catch (Exception e) { return 0.0; } }
    public String getString(int i) { try { return rs.getString(i + 1); } catch (Exception e) { return null; } }
    public boolean isNull(int i) { try { return rs.getObject(i + 1) == null; } catch (Exception e) { return true; } }
    public void close() { if (closed) return; closed = true; try { rs.close(); } catch (Exception ignored) { } try { st.close(); } catch (Exception ignored) { } }
    public boolean isClosed() { return closed; }
    public int getCount() { return 0; }
    public int getPosition() { return 0; }
    public boolean move(int o) { return false; }
    public boolean moveToPosition(int p) { return false; }
    public boolean moveToLast() { return false; }
    public boolean moveToPrevious() { return false; }
    public boolean isFirst() { return false; }
    public boolean isLast() { return false; }
    public boolean isBeforeFirst() { return false; }
    public boolean isAfterLast() { return !haveRow; }
    public int getColumnIndex(String c) { return 0; }
    public int getColumnIndexOrThrow(String c) { return 0; }
    public String getColumnName(int c) { return ""; }
    public String[] getColumnNames() { return new String[0]; }
    public short getShort(int i) { return 0; }
    public float getFloat(int i) { return 0f; }
    public byte[] getBlob(int i) { return null; }
    public int getType(int i) { return 0; }
    public void deactivate() { }
    public boolean requery() { return false; }
    public void registerContentObserver(ContentObserver o) { }
    public void unregisterContentObserver(ContentObserver o) { }
    public void registerDataSetObserver(DataSetObserver o) { }
    public void unregisterDataSetObserver(DataSetObserver o) { }
    public void setNotificationUri(android.content.ContentResolver cr, android.net.Uri u) { }
    public android.net.Uri getNotificationUri() { return null; }
    protected void finalize() { close(); }
}
