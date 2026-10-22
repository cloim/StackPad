package com.cloimism.stackpad;

import android.content.Intent;
import android.os.Bundle;
import com.cloimism.stackpad.alerts.AlertBridgePlugin;
import com.cloimism.stackpad.widget.WidgetBridgePlugin;
import com.cloimism.stackpad.widget.WidgetStore;
import com.getcapacitor.BridgeActivity;
import com.getcapacitor.CapConfig;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import org.json.JSONObject;

public class MainActivity extends BridgeActivity {
    /** Shown from the APK when the paired PC cannot be reached. */
    public static final String OFFLINE_PAGE = "offline.html";

    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(WidgetBridgePlugin.class);
        registerPlugin(AlertBridgePlugin.class);
        // A paired phone opens the screen straight from the PC engine, so the screen always matches the PC version.
        // Without a paired PC the screen bundled in the APK opens and shows pairing.
        String server = new WidgetStore(this).server();
        if (server != null) config = remoteConfig(server);
        super.onCreate(savedInstanceState);
        handleIntent(getIntent());
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handleIntent(intent);
    }

    /** Keeps the settings from capacitor.config.json and only points the bridge at the paired PC. */
    private CapConfig remoteConfig(String server) {
        try (InputStream input = getAssets().open("capacitor.config.json")) {
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            byte[] buffer = new byte[8192];
            for (int read; (read = input.read(buffer)) != -1; ) output.write(buffer, 0, read);
            JSONObject json = new JSONObject(output.toString(StandardCharsets.UTF_8.name()));
            CapConfig.Builder builder = new CapConfig.Builder(this).setServerUrl(server).setErrorPath(OFFLINE_PAGE);
            JSONObject plugins = json.optJSONObject("plugins");
            if (plugins != null) builder.setPluginsConfiguration(plugins);
            String background = json.optString("backgroundColor", "");
            if (!background.isEmpty()) builder.setBackgroundColor(background);
            return builder.create();
        } catch (Exception error) {
            return null;
        }
    }

    private void handleIntent(Intent intent) {
        if (intent == null) return;
        String padId = intent.getStringExtra("pad_id");
        if (padId != null && !padId.isEmpty() && getBridge() != null && getBridge().getWebView() != null) {
            String script = "window.dispatchEvent(new CustomEvent('select-pad', { detail: '" + padId + "' }));";
            getBridge().getWebView().post(() -> getBridge().getWebView().evaluateJavascript(script, null));
        }
    }
}
