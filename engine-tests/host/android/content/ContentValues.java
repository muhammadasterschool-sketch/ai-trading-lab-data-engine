package android.content;
public class ContentValues {
    private final java.util.HashMap<String,Object> m = new java.util.HashMap<>();
    public void put(String k, String v) { m.put(k, v); }
    public void put(String k, Integer v) { m.put(k, v); }
    public void put(String k, Long v) { m.put(k, v); }
    public void put(String k, Double v) { m.put(k, v); }
    public void put(String k, Boolean v) { m.put(k, v); }
    public Object get(String k) { return m.get(k); }
    public java.util.Set<String> keySet() { return m.keySet(); }
}
