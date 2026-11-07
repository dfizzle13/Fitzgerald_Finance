package com.fitzgerald.finance;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.Build;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import android.webkit.WebView;
import androidx.biometric.BiometricManager;
import androidx.biometric.BiometricPrompt;
import androidx.core.content.ContextCompat;
import org.json.JSONObject;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.security.MessageDigest;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/** Device-only, biometric-gated Android Keystore vault. Never stores a password. */
final class SecureDeviceVault {
    private final MainActivity activity;private final WebView webView;private final SharedPreferences preferences;
    private BiometricPrompt prompt;private String active;
    SecureDeviceVault(MainActivity activity,WebView webView){this.activity=activity;this.webView=webView;preferences=activity.getSharedPreferences("finance_device_vault",Context.MODE_PRIVATE);}
    private String name(String scope)throws Exception{byte[] hash=MessageDigest.getInstance("SHA-256").digest(scope.getBytes(StandardCharsets.UTF_8));StringBuilder hex=new StringBuilder("finance.biometric.");for(byte b:hash)hex.append(String.format("%02x",b&255));return hex.toString();}
    private SecretKey key(String alias,boolean create)throws Exception{
        KeyStore store=KeyStore.getInstance("AndroidKeyStore");store.load(null);
        if(!store.containsAlias(alias)&&create){
            KeyGenerator generator=KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore");
            KeyGenParameterSpec.Builder options=new KeyGenParameterSpec.Builder(alias,KeyProperties.PURPOSE_ENCRYPT|KeyProperties.PURPOSE_DECRYPT).setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).setUserAuthenticationRequired(true);
            if(Build.VERSION.SDK_INT>=30)options.setUserAuthenticationParameters(0,KeyProperties.AUTH_BIOMETRIC_STRONG);else options.setUserAuthenticationValidityDurationSeconds(-1);
            if(Build.VERSION.SDK_INT>=24)options.setInvalidatedByBiometricEnrollment(true);
            generator.init(options.build());generator.generateKey();
        }
        SecretKey key=(SecretKey)store.getKey(alias,null);if(key==null)throw new Exception("Sign in with your password and enable this device again.");return key;
    }
    boolean has(String scope){if(!activity.trustedScope(scope))return false;try{return preferences.contains(name(scope)+".data");}catch(Exception error){return false;}}
    void remove(String scope){if(!activity.trustedScope(scope))return;try{String alias=name(scope);preferences.edit().remove(alias+".data").remove(alias+".iv").apply();KeyStore store=KeyStore.getInstance("AndroidKeyStore");store.load(null);if(store.containsAlias(alias))store.deleteEntry(alias);}catch(Exception ignored){}}
    void cancel(String request){activity.runOnUiThread(()->{if(prompt!=null&&request!=null&&request.equals(active))prompt.cancelAuthentication();});}
    void authenticate(String scope,String value,String requestId){
        if(!activity.trustedScope(scope)||requestId==null||requestId.length()>100||value!=null&&value.length()>4096){callback("error",requestId,"Device credential request rejected.");return;}
        activity.runOnUiThread(()->{
            if(prompt!=null){callback("error",requestId,"Finish the current device authentication first.");return;}
            try{
                if(BiometricManager.from(activity).canAuthenticate(BiometricManager.Authenticators.BIOMETRIC_STRONG)!=BiometricManager.BIOMETRIC_SUCCESS)throw new Exception("Enable a strong biometric in your device settings first.");
                boolean encrypt=value!=null;String alias=name(scope);Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");
                if(encrypt)cipher.init(Cipher.ENCRYPT_MODE,key(alias,true));
                else{String iv=preferences.getString(alias+".iv",null);if(iv==null)throw new Exception("Sign in with your password and enable this device again.");cipher.init(Cipher.DECRYPT_MODE,key(alias,false),new GCMParameterSpec(128,Base64.decode(iv,Base64.NO_WRAP)));}
                active=requestId;
                prompt=new BiometricPrompt(activity,ContextCompat.getMainExecutor(activity),new BiometricPrompt.AuthenticationCallback(){
                    @Override public void onAuthenticationSucceeded(BiometricPrompt.AuthenticationResult result){
                        prompt=null;active=null;
                        try{
                            Cipher authenticated=result.getCryptoObject()==null?null:result.getCryptoObject().getCipher();if(authenticated==null)throw new Exception("Device verification did not return a secure key.");
                            if(encrypt){byte[] encrypted=authenticated.doFinal(value.getBytes(StandardCharsets.UTF_8));preferences.edit().putString(alias+".data",Base64.encodeToString(encrypted,Base64.NO_WRAP)).putString(alias+".iv",Base64.encodeToString(authenticated.getIV(),Base64.NO_WRAP)).apply();callback("success",requestId,"stored");}
                            else{String encrypted=preferences.getString(alias+".data",null);if(encrypted==null)throw new Exception("Device credential is missing.");String credential=new String(authenticated.doFinal(Base64.decode(encrypted,Base64.NO_WRAP)),StandardCharsets.UTF_8);callback("success",requestId,credential);}
                        }catch(Exception error){callback("error",requestId,"Sign in with your password and enable this device again.");}
                    }
                    @Override public void onAuthenticationFailed(){callback("failed",requestId,"");}
                    @Override public void onAuthenticationError(int code,CharSequence message){prompt=null;active=null;callback("error",requestId,message==null?"Device authentication ended.":message.toString());}
                });
                BiometricPrompt.PromptInfo info=new BiometricPrompt.PromptInfo.Builder().setTitle("Fitzgerald Finance").setSubtitle(encrypt?"Enable secure sign-in on this device":"Unlock your household sign-in").setDescription("Your fingerprint or face data stays with this device.").setAllowedAuthenticators(BiometricManager.Authenticators.BIOMETRIC_STRONG).setNegativeButtonText("Cancel").build();
                prompt.authenticate(info,new BiometricPrompt.CryptoObject(cipher));
            }catch(Exception error){prompt=null;active=null;callback("error",requestId,"Sign in with your password and enable this device again. "+(error.getMessage()==null?"":error.getMessage()));}
        });
    }
    private void callback(String method,String id,String value){if(id==null)return;String script="window.FinanceNativeVaultCallbacks&&window.FinanceNativeVaultCallbacks."+method+"("+JSONObject.quote(id)+","+JSONObject.quote(value)+")";activity.runOnUiThread(()->webView.evaluateJavascript(script,null));}
}
