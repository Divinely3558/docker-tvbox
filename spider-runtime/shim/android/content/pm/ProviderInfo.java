package android.content.pm;

import java.util.HashMap;
import java.util.Map;

public class ProviderInfo extends PackageItemInfo {
    public String authority;
    public String name;
    public Map<String, Object> metaData = new HashMap<>();
    public boolean exported;
    public int grantUriPermissions;
}
