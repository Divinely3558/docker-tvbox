package android.content.pm;

import android.content.Context;
import android.content.res.XmlResourceParser;

public class PackageItemInfo {
    public String packageName;
    public String name;
    public int labelRes;
    public int nonLocalizedLabelRes;
    public String nonLocalizedLabel;
    public int icon;
    public Object loadLabel(Context ctx) { return name == null ? packageName : name; }
    public XmlResourceParser loadXmlMetaData(Context ctx) { return null; }
    public Object loadIcon(Context ctx) { return null; }
    public Object loadName(Context ctx) { return name; }
}
