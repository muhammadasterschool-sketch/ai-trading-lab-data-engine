package android.app;
public class Notification {
    public static final int PRIORITY_HIGH = 1;
    public static class Style { }
    public static class Builder {
        public Builder(android.content.Context c) { }
        public Builder(android.content.Context c, String channel) { }
        public Builder setContentTitle(CharSequence t) { return this; }
        public Builder setContentText(CharSequence t) { return this; }
        public Builder setStyle(Style s) { return this; }
        public Builder setSmallIcon(int i) { return this; }
        public Builder setAutoCancel(boolean b) { return this; }
        public Builder setWhen(long w) { return this; }
        public Builder setPriority(int p) { return this; }
        public Notification build() { return new Notification(); }
    }
    public static class BigTextStyle extends Style {
        public BigTextStyle() { }
        public BigTextStyle bigText(CharSequence t) { return this; }
    }
}
