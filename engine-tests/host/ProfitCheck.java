import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Statement;

/** $100 profit observation query — accounts, trades, per-user P/L, equity curve. */
public class ProfitCheck {
    public static void main(String[] a) throws Exception {
        String db = a.length > 0 ? a[0] : "/tmp/atl-host/atl-engine.db";
        try (Connection c = DriverManager.getConnection("jdbc:sqlite:" + db)) {
            System.out.println("=== PROFIT CHECK — " + db + " ===");
            try (Statement st = c.createStatement()) {
                ResultSet rs = st.executeQuery("SELECT COUNT(*) FROM trades");
                if (rs.next()) System.out.println("total trades: " + rs.getInt(1));
            }
            try (Statement st = c.createStatement();
                 ResultSet rs = st.executeQuery(
                    "SELECT u.id, u.email, u.role, IFNULL(a.balance,0), IFNULL(a.start_balance,0) " +
                    "FROM users u LEFT JOIN accounts a ON a.user_id=u.id ORDER BY u.id")) {
                System.out.println("--- ACCOUNTS ---");
                while (rs.next())
                    System.out.printf("user#%d %s [%s] balance=%.2f start=%.2f net=%+.2f%n",
                        rs.getLong(1), rs.getString(2), rs.getString(3), rs.getDouble(4), rs.getDouble(5),
                        rs.getDouble(4) - rs.getDouble(5));
            }
            try (PreparedStatement ps = c.prepareStatement(
                    "SELECT user_id, status, COUNT(*), IFNULL(SUM(pnl),0) FROM trades GROUP BY user_id, status ORDER BY user_id")) {
                System.out.println("--- TRADES by user/status ---");
                while (rs2(ps)) { }
            }
            try (Statement st = c.createStatement();
                 ResultSet rs = st.executeQuery(
                    "SELECT strategy, status, COUNT(*), IFNULL(SUM(pnl),0) FROM trades WHERE strategy LIKE 'PB:%' GROUP BY strategy, status")) {
                System.out.println("--- PLAYBOOK (PB:) trades ---");
                boolean any = false;
                while (rs.next()) { any = true;
                    System.out.printf("%s %s n=%d pnl=%+.2f%n", rs.getString(1), rs.getString(2), rs.getInt(3), rs.getDouble(4));
                }
                if (!any) System.out.println("(koi PB trade nahi hua abhi)");
            }
            try (Statement st = c.createStatement();
                 ResultSet rs = st.executeQuery("SELECT MAX(ts), MIN(ts) FROM equity")) {
                if (rs.next()) System.out.println("equity snapshots: " + rs.getLong(1) + " .. " + rs.getLong(2));
            }
            try (Statement st = c.createStatement();
                 ResultSet rs = st.executeQuery(
                    "SELECT event, COUNT(*) FROM logs WHERE component='PB' OR component='PACK' OR component='3C' GROUP BY event ORDER BY 2 DESC LIMIT 12")) {
                System.out.println("--- ENGINE EVENTS ---");
                while (rs.next()) System.out.println(rs.getString(1) + " x" + rs.getInt(2));
            }
        }
    }
    static boolean rs2(PreparedStatement ps) throws Exception {
        ResultSet rs = ps.executeQuery();
        boolean had = false;
        while (rs.next()) { had = true;
            System.out.printf("user#%d %-9s n=%-4d pnl=%+.2f%n", rs.getLong(1), rs.getString(2), rs.getInt(3), rs.getDouble(4));
        }
        rs.close();
        return false;
    }
}
