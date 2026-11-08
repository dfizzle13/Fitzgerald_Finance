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
import android.widget.FrameLayout;
import android.view.ViewGroup;
import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowInsetsCompat;
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
        WindowCompat.setDecorFitsSystemWindows(getWindow(),false);
        getWindow().setStatusBarColor(Color.rgb(243,246,241));getWindow().setNavigationBarColor(Color.rgb(243,246,241));
        webView=new WebView(this);webView.setBackgroundColor(Color.rgb(243,246,241));webView.setFitsSystemWindows(false);
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
        webView.setWebChromeClient(new WebChromeClient());webView.addJavascriptInterface(new FinanceBiometricBridge(this,webView),"FitzgeraldAndroid");
        FrameLayout host=new FrameLayout(this);host.setBackgroundColor(Color.rgb(243,246,241));
        host.addView(webView,new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,ViewGroup.LayoutParams.MATCH_PARENT));
        // Own system-bar, cutout, and keyboard insets once, outside the WebView.
        // Android 15 enforces edge-to-edge even when decor fitting was requested.
        // Recalculate when rotation, navigation mode, or keyboard visibility changes.
        ViewCompat.setOnApplyWindowInsetsListener(host,(view,windowInsets)->{
            Insets bars=windowInsets.getInsets(WindowInsetsCompat.Type.systemBars()|WindowInsetsCompat.Type.displayCutout());
            Insets keyboard=windowInsets.getInsets(WindowInsetsCompat.Type.ime());
            view.setPadding(bars.left,bars.top,bars.right,Math.max(bars.bottom,keyboard.bottom));
            return WindowInsetsCompat.CONSUMED;
        });
        setContentView(host);
        WindowCompat.getInsetsController(getWindow(),getWindow().getDecorView()).setAppearanceLightStatusBars(true);
        WindowCompat.getInsetsController(getWindow(),getWindow().getDecorView()).setAppearanceLightNavigationBars(true);
        ViewCompat.requestApplyInsets(host);
        String server=serverUrl();if(server.isEmpty())webView.loadUrl(LOCAL);else loadServer(server);
    }
    public void openPhoneAccounts(){
        if(!trustedPage())return;
        runOnUiThread(()->webView.loadUrl(LOCAL+"#device-transfer"));
    }
    public void setPhoneTransferId(String identifier){
        if(currentPage.startsWith(LOCAL)&&identifier!=null&&identifier.matches("[a-f0-9]{32}"))connections.edit().putString("pendingTransfer",identifier).apply();
    }
    public void finishPhoneTransfer(String identifier){
        if(!trustedScope(serverUrl()+"|transfer")||identifier==null||!identifier.equals(connections.getString("pendingTransfer","")))return;
        connections.edit().putBoolean("completeTransfer",true).apply();
        runOnUiThread(()->webView.loadUrl(LOCAL+"#complete-transfer"));
    }
    public boolean consumePhoneTransferCompletion(){
        if(!currentPage.startsWith(LOCAL)||!connections.getBoolean("completeTransfer",false))return false;
        connections.edit().remove("completeTransfer").remove("pendingTransfer").apply();return true;
    }
    public void returnToHouseholdServer(){
        if(currentPage.startsWith(LOCAL)&&!serverUrl().isEmpty())runOnUiThread(()->loadServer(serverUrl()));
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
