package android.content.res;
public class AssetManager {
    private static String root = null;
    public static void setAssetsRoot(String r) { root = r; }
    public java.io.InputStream open(String name) throws java.io.IOException {
        if (root != null) return new java.io.FileInputStream(new java.io.File(root, name));
        throw new java.io.IOException("assets root not set");
    }
}
