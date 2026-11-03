package android.database.sqlite;
import android.content.ContentValues;
import android.database.Cursor;
import android.database.JdbcCursor;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
public class SQLiteDatabase {
    /** android.jar parity — engine ctor descriptor isi par compile hua hai. */
    public static class CursorFactory { }

    private final Connection conn;
    private int txDepth = 0;
    private boolean txSuccess = false;
    public SQLiteDatabase(String path) {
        try {
            Class.forName("org.sqlite.JDBC");
            conn = DriverManager.getConnection("jdbc:sqlite:" + path);
        } catch (Exception e) { throw new RuntimeException(e); }
    }
    public Cursor rawQuery(String sql, String[] args) {
        try {
            PreparedStatement ps = conn.prepareStatement(sql);
            if (args != null) for (int i = 0; i < args.length; i++) ps.setString(i + 1, args[i]);
            ResultSet rs = ps.executeQuery();
            return new JdbcCursor(rs, ps);
        } catch (SQLException e) { throw new RuntimeException(e); }
    }
    public void execSQL(String sql) {
        try (Statement st = conn.createStatement()) { st.execute(sql); }
        catch (SQLException e) { throw new RuntimeException(e); }
    }
    public void execSQL(String sql, Object[] bindArgs) {
        try {
            PreparedStatement ps = conn.prepareStatement(sql);
            for (int i = 0; i < bindArgs.length; i++) {
                Object o = bindArgs[i];
                if (o == null) ps.setObject(i + 1, null);
                else if (o instanceof Integer) ps.setInt(i + 1, (Integer) o);
                else if (o instanceof Long) ps.setLong(i + 1, (Long) o);
                else if (o instanceof Double) ps.setDouble(i + 1, (Double) o);
                else if (o instanceof Float) ps.setFloat(i + 1, (Float) o);
                else if (o instanceof Boolean) ps.setInt(i + 1, (Boolean) o ? 1 : 0);
                else ps.setString(i + 1, String.valueOf(o));
            }
            ps.executeUpdate();
            ps.close();
        } catch (SQLException e) { throw new RuntimeException(e); }
    }
    public int update(String table, ContentValues cv, String whereClause, String[] whereArgs) {
        if (cv.keySet().isEmpty()) return 0;
        StringBuilder sb = new StringBuilder("UPDATE ").append(table).append(" SET ");
        for (String k : cv.keySet()) sb.append(k).append("=?,");
        sb.setLength(sb.length() - 1);
        if (whereClause != null && !whereClause.isEmpty()) sb.append(" WHERE ").append(whereClause);
        try {
            PreparedStatement ps = conn.prepareStatement(sb.toString());
            int i = 1;
            for (String k : cv.keySet()) {
                Object o = cv.get(k);
                if (o instanceof Integer) ps.setInt(i, (Integer) o);
                else if (o instanceof Long) ps.setLong(i, (Long) o);
                else if (o instanceof Double) ps.setDouble(i, (Double) o);
                else if (o instanceof Boolean) ps.setInt(i, (Boolean) o ? 1 : 0);
                else ps.setString(i, String.valueOf(o));
                i++;
            }
            if (whereArgs != null) for (String w : whereArgs) ps.setString(i++, w);
            int n = ps.executeUpdate();
            ps.close();
            return n;
        } catch (SQLException e) { throw new RuntimeException(e); }
    }
    public void beginTransaction() {
        try { if (txDepth++ == 0) { conn.setAutoCommit(false); txSuccess = false; } }
        catch (SQLException e) { throw new RuntimeException(e); }
    }
    public void setTransactionSuccessful() { if (txDepth > 0) txSuccess = true; }
    public void endTransaction() {
        try {
            if (--txDepth <= 0) {
                txDepth = 0;
                if (txSuccess) conn.commit(); else conn.rollback();
                conn.setAutoCommit(true);
            }
        } catch (SQLException e) { throw new RuntimeException(e); }
    }
    public void close() { try { conn.close(); } catch (SQLException ignored) { } }
}
