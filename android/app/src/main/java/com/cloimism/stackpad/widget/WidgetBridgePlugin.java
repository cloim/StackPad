package com.cloimism.stackpad.widget;

import android.appwidget.AppWidgetManager;
import android.content.ComponentName;
import android.net.Uri;
import android.os.Build;
import com.cloimism.stackpad.BuildConfig;
import com.cloimism.stackpad.R;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import org.json.JSONObject;

/** Bridges the web screen to native storage: the paired PC address and the home screen widget connection. */
@CapacitorPlugin(name = "WidgetBridge")
public class WidgetBridgePlugin extends Plugin {
    @PluginMethod
    public void server(PluginCall call) {
        JSObject result = new JSObject();
        result.put("url", new WidgetStore(getContext()).server());
        call.resolve(result);
    }

    @PluginMethod
    public void saveServer(PluginCall call) {
        String url = call.getString("url");
        // Debug builds may pair with an engine reached through adb reverse on the emulator.
        boolean allowed = url != null && (url.startsWith("https://") || (BuildConfig.DEBUG && url.startsWith("http://localhost:")));
        if (!allowed) {
            call.reject(getContext().getString(R.string.bridge_invalid_server));
            return;
        }
        new WidgetStore(getContext()).saveServer(url);
        call.resolve();
        if (!url.equals(getBridge().getServerUrl())) reopen();
    }

    /** Forgetting the PC also drops the widget connection that belonged to it. */
    @PluginMethod
    public void clearServer(PluginCall call) {
        forget();
        call.resolve();
    }

    private void forget() {
        new WidgetStore(getContext()).clear();
        UsageWidgetProvider.renderAll(getContext());
        if (getBridge().getServerUrl() != null) reopen();
    }

    /** The bridge reads the PC address only at start, so a changed address starts the screen again. */
    private void reopen() {
        getActivity().runOnUiThread(() -> getActivity().recreate());
    }

    /** The offline page opens from the APK without the bridge, so its buttons talk to the app through stackpad:// links. */
    @Override
    public Boolean shouldOverrideLoad(Uri url) {
        if (!"stackpad".equals(url.getScheme())) return null;
        if ("retry".equals(url.getHost())) getBridge().getWebView().post(() -> getBridge().getWebView().loadUrl(getBridge().getAppUrl()));
        else if ("unpair".equals(url.getHost())) forget();
        return true;
    }

    @PluginMethod
    public void status(PluginCall call) {
        JSObject result = new JSObject();
        result.put("id", new WidgetStore(getContext()).id());
        result.put("device", Build.MANUFACTURER + " " + Build.MODEL);
        call.resolve(result);
    }

    @PluginMethod
    public void saveToken(PluginCall call) {
        String id = call.getString("id");
        String token = call.getString("token");
        String origin = call.getString("origin");
        if (id == null || token == null || origin == null) {
            call.reject(getContext().getString(R.string.bridge_invalid_widget));
            return;
        }
        new WidgetStore(getContext()).connect(id, token, origin);
        UsageRefreshWorker.refreshNow(getContext());
        call.resolve();
    }

    /** The app screen hands over each usage answer, so the widget never shows older numbers than the app. */
    @PluginMethod
    public void saveUsage(PluginCall call) {
        String usage = call.getString("usage");
        try {
            new JSONObject(usage).getJSONArray("providers");
        } catch (Exception error) {
            call.reject(getContext().getString(R.string.bridge_invalid_usage));
            return;
        }
        WidgetStore store = new WidgetStore(getContext());
        // A widget without a connection keeps asking for sign-in instead of showing numbers it cannot refresh.
        if (store.token() != null) {
            store.saveUsage(usage, System.currentTimeMillis());
            UsageWidgetProvider.renderAll(getContext());
        }
        call.resolve();
    }

    /** Asks the launcher to place the widget; the launcher shows its own confirmation. */
    @PluginMethod
    public void pinWidget(PluginCall call) {
        AppWidgetManager manager = AppWidgetManager.getInstance(getContext());
        if (!manager.isRequestPinAppWidgetSupported()) {
            call.reject(getContext().getString(R.string.bridge_pin_unsupported));
            return;
        }
        manager.requestPinAppWidget(new ComponentName(getContext(), UsageWidgetProvider.class), null, null);
        call.resolve();
    }

    @PluginMethod
    public void clearToken(PluginCall call) {
        new WidgetStore(getContext()).revoke(getContext().getString(R.string.widget_connects_after_sign_in));
        UsageWidgetProvider.renderAll(getContext());
        call.resolve();
    }
}
