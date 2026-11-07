package android.webkit;

import java.io.InputStream;
import java.util.Map;

public class WebResourceResponse {
    public WebResourceResponse() {}

    public WebResourceResponse(String mimeType, String encoding, InputStream data) {}

    public WebResourceResponse(String mimeType, String encoding, int statusCode, String reasonPhrase, Map<String, String> headers, InputStream data) {}

    public void setMimeType(String mimeType) {}

    public void setEncoding(String encoding) {}

    public void setData(InputStream data) {}

    public void setStatusCode(int statusCode) {}

    public void setReasonPhrase(String reasonPhrase) {}

    public void setResponseHeaders(Map<String, String> headers) {}
}
