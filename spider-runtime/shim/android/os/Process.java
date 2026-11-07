package android.os;

public class Process {
    public static int myPid() { return 1; }
    public static int myTid() { return 1; }
    public static int myUid() { return 0; }
    public static void setThreadPriority(int p) {}
    public static int getThreadPriority() { return 0; }
}
