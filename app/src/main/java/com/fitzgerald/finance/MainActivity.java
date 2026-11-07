package com.fitzgerald.finance;

import android.os.Build;
import android.os.Bundle;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.net.Uri;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceError;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;
import androidx.fragment.app.FragmentActivity;
import androidx.core.view.WindowCompat;
import org.json.JSONObject;
import java.net.HttpURLConnection;
import java.net.URL;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

public final class MainActivity extends FragmentActivity {
    private static final String LOCAL="file:///android_asset/www/index.html";
    private WebView webView;
    private volatile String currentPage=LOCAL;
    private SharedPreferences connections;
    @Override public void onCreate(Bundle state){
        super.onCreate(state);
        connections=getSharedPreferences("finance_connection",MODE_PRIVATE);
        WindowCompat.setDecorFitsSystemWindows(getWindow(),true);
        getWindow().setStatusBarColor(Color.rgb(31,85,66));getWindow().setNavigationBarColor(Color.rgb(243,246,241));
        if(Build.VERSION.SDK_INT>=Build.VERSION_CODES.O)getWindow().getDecorView().setSystemUiVisibility(android.view.View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        webView=new WebView(this);webView.setBackgroundColor(Color.rgb(243,246,241));webView.setFitsSystemWindows(true);
        WebSettings settings=webView.getSettings();settings.setJavaScriptEnabled(true);settings.setDomStorageEnabled(true);settings.setDatabaseEnabled(true);settings.setAllowFileAccess(true);settings.setAllowContentAccess(false);settings.setJavaScriptCanOpenWindowsAutomatically(false);settings.setSupportMultipleWindows(false);settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);settings.setMediaPlaybackRequiresUserGesture(true);
        webView.setWebViewClient(new WebViewClient(){
            @Override public boolean shouldOverrideUrlLoading(WebView view,WebResourceRequest request){return !allowed(request.getUrl().toString());}
            @Override public void onPageStarted(WebView view,String url,Bitmap favicon){currentPage=allowed(url)?url:"";}
            @Override public void onReceivedError(WebView view,WebResourceRequest request,WebResourceError error){
                if(request.isForMainFrame()&&!request.getUrl().toString().startsWith("file:")){
                    currentPage=LOCAL;view.loadUrl(LOCAL+"#connection");Toast.makeText(MainActivity.this,"Server unavailable. Check Server connectivity.",Toast.LENGTH_LONG).show();
                }
            }
        });
        webView.setWebChromeClient(new WebChromeClient());webView.addJavascriptInterface(new FinanceBiometricBridge(this,webView),"FitzgeraldAndroid");setContentView(webView);
        String server=serverUrl();if(server.isEmpty())webView.loadUrl(LOCAL);else loadServer(server);
    }
    public String serverUrl(){return connections.getString("url","");}
    private boolean allowed(String url){
        if(url.startsWith("file:///android_asset/www/"))return true;
        String base=serverUrl();return !base.isEmpty()&&url.startsWith(base);
    }
    public boolean trustedPage(){return allowed(currentPage)&&!currentPage.isEmpty();}
    public boolean trustedScope(String scope){String base=serverUrl();return !base.isEmpty()&&currentPage.startsWith(base)&&scope!=null&&scope.startsWith(base+"|")&&scope.length()<1200;}
    private String normalize(String value)throws Exception{
        Uri parsed=Uri.parse(value.trim());String host=parsed.getHost();
        if(!"https".equalsIgnoreCase(parsed.getScheme())||host==null||parsed.getUserInfo()!=null||parsed.getQuery()!=null||parsed.getFragment()!=null)throw new Exception("Use your Finance HTTPS server address.");
        String path=parsed.getEncodedPath();if(path==null||path.isEmpty())path="/";
        if(path.contains("..")||path.contains("\\"))throw new Exception("Invalid server path.");
        if(!path.endsWith("/"))path+="/";
        String authority=host.toLowerCase(Locale.ROOT)+(parsed.getPort()>0&&parsed.getPort()!=443?":"+parsed.getPort():"");
        return new Uri.Builder().scheme("https").encodedAuthority(authority).encodedPath(path).build().toString();
    }
    private void loadServer(String url){Map<String,String> headers=new HashMap<>();headers.put("ngrok-skip-browser-warning","1");webView.loadUrl(url,headers);}
    public void testServer(String value,String requestId,boolean connect){
        if(!trustedPage()||requestId==null||requestId.length()>100)return;
        new Thread(()->{
            HttpURLConnection connection=null;
            try{
                String url=normalize(value);connection=(HttpURLConnection)new URL(url+"api/status").openConnection();connection.setConnectTimeout(10000);connection.setReadTimeout(10000);connection.setInstanceFollowRedirects(false);connection.setRequestProperty("ngrok-skip-browser-warning","1");
                if(connection.getResponseCode()!=200)throw new Exception("Finance server did not respond successfully.");
                StringBuilder content=new StringBuilder();try(BufferedReader reader=new BufferedReader(new InputStreamReader(connection.getInputStream(),StandardCharsets.UTF_8))){String line;while((line=reader.readLine())!=null){content.append(line);if(content.length()>65536)throw new Exception("Unexpected server response.");}}
                JSONObject result=new JSONObject(content.toString());if(!"fitzgerald-finance".equals(result.optString("application"))||!result.optBoolean("shared"))throw new Exception("This is not a Fitzgerald Finance server. Include /finance/ in the shared ngrok address.");
                connectionCallback("success",requestId,"{\"ok\":true,\"application\":\"fitzgerald-finance\"}");
                if(connect)runOnUiThread(()->{connections.edit().putString("url",url).apply();loadServer(url);});
            }catch(Exception error){connectionCallback("error",requestId,error.getMessage()==null?"Could not connect to server.":error.getMessage());}
            finally{if(connection!=null)connection.disconnect();}
        },"Finance connection check").start();
    }
    private void connectionCallback(String method,String id,String message){String script="window.FinanceConnectionCallbacks&&window.FinanceConnectionCallbacks."+method+"("+JSONObject.quote(id)+","+JSONObject.quote(message)+")";runOnUiThread(()->webView.evaluateJavascript(script,null));}
    public void disconnectServer(){if(!trustedPage())return;runOnUiThread(()->{connections.edit().remove("url").apply();currentPage=LOCAL;webView.loadUrl(LOCAL);});}
    @Override public void onBackPressed(){if(webView!=null&&webView.canGoBack())webView.goBack();else super.onBackPressed();}
}
