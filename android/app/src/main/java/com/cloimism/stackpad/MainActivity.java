package com.cloimism.stackpad;

import android.content.Intent;
import android.os.Bundle;
import com.cloimism.stackpad.alerts.AlertBridgePlugin;
import com.cloimism.stackpad.widget.WidgetBridgePlugin;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(WidgetBridgePlugin.class);
        registerPlugin(AlertBridgePlugin.class);
        super.onCreate(savedInstanceState);
        handleIntent(getIntent());
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handleIntent(intent);
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

