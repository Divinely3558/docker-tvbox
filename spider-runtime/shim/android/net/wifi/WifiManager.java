package android.net.wifi;

import java.net.InetAddress;
import java.net.NetworkInterface;
import java.util.Collections;
import java.util.Enumeration;

/** Reports the real host address so spiders that derive a device id from it stay stable. */
public class WifiManager {
    public static final int WIFI_STATE_ENABLED = 3;
    private volatile WifiInfo cached;

    public WifiInfo getConnectionInfo() {
        WifiInfo info = cached;
        if (info == null) {
            info = probe();
            cached = info;
        }
        return info;
    }

    private static WifiInfo probe() {
        try {
            Enumeration<NetworkInterface> ifs = NetworkInterface.getNetworkInterfaces();
            for (NetworkInterface nif : Collections.list(ifs)) {
                if (!nif.isUp() || nif.isLoopback()) continue;
                byte[] hw = nif.getHardwareAddress();
                for (InetAddress a : Collections.list(nif.getInetAddresses())) {
                    byte[] addr = a.getAddress();
                    if (addr.length != 4) continue;
                    int ip = 0;
                    for (int i = 3; i >= 0; i--) ip = (ip << 8) | (addr[i] & 0xff);
                    String mac = hw == null ? "02:00:00:00:00:00" : join(hw);
                    return new WifiInfo(ip, mac);
                }
            }
        } catch (Exception ignored) {}
        return new WifiInfo(0, "02:00:00:00:00:00");
    }

    private static String join(byte[] hw) {
        StringBuilder sb = new StringBuilder();
        for (byte b : hw) { if (sb.length() > 0) sb.append(':'); sb.append(String.format("%02x", b)); }
        return sb.toString();
    }

    public boolean isWifiEnabled() { return true; }
    public int getWifiState() { return WIFI_STATE_ENABLED; }
    public Object startScan() { return null; }
}
