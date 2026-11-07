package android.net.wifi;

public class WifiInfo {
    private final int ip;
    private final String mac;
    public WifiInfo(int ip, String mac) { this.ip = ip; this.mac = mac; }
    public int getIpAddress() { return ip; }
    public String getMacAddress() { return mac; }
    public String getBSSID() { return mac; }
    public String getSSID() { return "\"web\""; }
    public int getRssi() { return -50; }
    public int getNetworkId() { return 0; }
    public int getSpeed() { return 0; }
}
