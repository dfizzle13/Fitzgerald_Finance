package com.fitzgerald.finance;

import android.app.Activity;
import android.webkit.JavascriptInterface;
import android.webkit.WebView;

import androidx.biometric.BiometricManager;
import androidx.biometric.BiometricPrompt;
import androidx.core.content.ContextCompat;
import androidx.fragment.app.FragmentActivity;

import java.util.concurrent.Executor;

public final class FinanceBiometricBridge {
    private final FragmentActivity activity;
    private final WebView webView;
    private final SecureDeviceVault vault;
    private BiometricPrompt activePrompt;
    private String activeRequestId;

    public FinanceBiometricBridge(FragmentActivity activity, WebView webView) {
        this.activity = activity;
        this.webView = webView;
        this.vault = new SecureDeviceVault((MainActivity) activity, webView);
    }

    @JavascriptInterface public void openPhoneAccounts(){ ((MainActivity)activity).openPhoneAccounts(); }
    @JavascriptInterface public void setPhoneTransferId(String id){ ((MainActivity)activity).setPhoneTransferId(id); }
    @JavascriptInterface public void finishPhoneTransfer(String id){ ((MainActivity)activity).finishPhoneTransfer(id); }
    @JavascriptInterface public boolean consumePhoneTransferCompletion(){ return ((MainActivity)activity).consumePhoneTransferCompletion(); }
    @JavascriptInterface public void returnToHouseholdServer(){ ((MainActivity)activity).returnToHouseholdServer(); }
    @JavascriptInterface public String getServerUrl() { return ((MainActivity)activity).serverUrl(); }
    @JavascriptInterface public void testServer(String url,String requestId) { ((MainActivity)activity).testServer(url,requestId,false); }
    @JavascriptInterface public void connectServer(String url,String requestId) { ((MainActivity)activity).testServer(url,requestId,true); }
    @JavascriptInterface public void disconnectServer() { ((MainActivity)activity).disconnectServer(); }
    @JavascriptInterface public boolean hasBiometricCredential(String scope) { return vault.has(scope); }
    @JavascriptInterface public void storeBiometricCredential(String scope,String value,String requestId) { vault.authenticate(scope,value,requestId); }
    @JavascriptInterface public void unlockBiometricCredential(String scope,String requestId) { vault.authenticate(scope,null,requestId); }
    @JavascriptInterface public void removeBiometricCredential(String scope) { vault.remove(scope); }
    @JavascriptInterface
    public boolean isBiometricAvailable() {
        return BiometricManager.from(activity).canAuthenticate(
            BiometricManager.Authenticators.BIOMETRIC_STRONG
        ) == BiometricManager.BIOMETRIC_SUCCESS;
    }

    @JavascriptInterface
    public void authenticate(String purpose, String requestId) {
        if (requestId == null || requestId.length() > 100) return;
        activity.runOnUiThread(() -> {
            if (!isBiometricAvailable()) {
                sendError(requestId, "No enrolled strong biometric is available on this device.");
                return;
            }
            activeRequestId = requestId;
            Executor executor = ContextCompat.getMainExecutor(activity);
            activePrompt = new BiometricPrompt(activity, executor, new BiometricPrompt.AuthenticationCallback() {
                @Override
                public void onAuthenticationSucceeded(BiometricPrompt.AuthenticationResult result) {
                    String id = activeRequestId;
                    activeRequestId = null;
                    activePrompt = null;
                    if (id != null) runCallback("onSuccess", id, "");
                }

                @Override
                public void onAuthenticationFailed() {
                    String id = activeRequestId;
                    if (id != null) runCallback("onScanFailed", id, "");
                }

                @Override
                public void onAuthenticationError(int errorCode, CharSequence errString) {
                    String id = activeRequestId;
                    activeRequestId = null;
                    activePrompt = null;
                    if (id != null) sendError(id, errString == null ? "Biometric authentication ended." : errString.toString());
                }
            });

            BiometricPrompt.PromptInfo prompt = new BiometricPrompt.PromptInfo.Builder()
                .setTitle("Fitzgerald Finance")
                .setSubtitle("setup".equals(purpose)
                    ? "Confirm your identity to enable biometric sign-in"
                    : "Confirm your identity to sign in")
                .setDescription("Your biometric data stays on this device.")
                .setAllowedAuthenticators(BiometricManager.Authenticators.BIOMETRIC_STRONG)
                .setNegativeButtonText("Cancel")
                .build();
            activePrompt.authenticate(prompt);
        });
    }

    @JavascriptInterface
    public void cancelAuthentication(String requestId) {
        vault.cancel(requestId);
        activity.runOnUiThread(() -> {
            if (activePrompt != null && requestId != null && requestId.equals(activeRequestId)) {
                activePrompt.cancelAuthentication();
            }
        });
    }

    private void sendError(String requestId, String message) {
        runCallback("onError", requestId, message);
    }

    private void runCallback(String method, String requestId, String message) {
        String id = quote(requestId);
        String msg = quote(message);
        String script;
        if ("onScanFailed".equals(method)) {
            script = "window.FitzgeraldFinanceNativeCallback && window.FitzgeraldFinanceNativeCallback.onScanFailed(" + id + ")";
        } else if ("onSuccess".equals(method)) {
            script = "window.FitzgeraldFinanceNativeCallback && window.FitzgeraldFinanceNativeCallback.onSuccess(" + id + ")";
        } else {
            script = "window.FitzgeraldFinanceNativeCallback && window.FitzgeraldFinanceNativeCallback.onError(" + id + "," + msg + ")";
        }
        activity.runOnUiThread(() -> webView.evaluateJavascript(script, null));
    }

    private String quote(String value) {
        String safe = value == null ? "" : value;
        safe = safe.replace("\\", "\\\\")
                   .replace("'", "\\'")
                   .replace("\r", " ")
                   .replace("\n", " ");
        return "'" + safe + "'";
    }
}
