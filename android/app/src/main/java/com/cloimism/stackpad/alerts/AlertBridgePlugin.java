package com.cloimism.stackpad.alerts;

import android.Manifest;
import android.content.Intent;
import android.os.Build;
import androidx.core.content.ContextCompat;
import com.getcapacitor.JSObject;
import com.getcapacitor.PermissionState;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;

@CapacitorPlugin(
        name = "AlertBridge",
        permissions = {
                @Permission(alias = "notifications", strings = {Manifest.permission.POST_NOTIFICATIONS})
        }
)
public class AlertBridgePlugin extends Plugin {

    @PluginMethod
    public void status(PluginCall call) {
        JSObject result = new JSObject();
        result.put("enabled", AlertStore.isAlertsEnabled(getContext()));
        call.resolve(result);
    }

    @PluginMethod
    public void start(PluginCall call) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (getPermissionState("notifications") != PermissionState.GRANTED) {
                requestPermissionForAlias("notifications", call, "startCallback");
                return;
            }
        }
        startAlertService();
        call.resolve();
    }

    @PermissionCallback
    private void startCallback(PluginCall call) {
        if (getPermissionState("notifications") == PermissionState.GRANTED) {
            startAlertService();
            call.resolve();
        } else {
            call.reject("Notification permission denied");
        }
    }

    private void startAlertService() {
        AlertStore.setAlertsEnabled(getContext(), true);
        Intent intent = new Intent(getContext(), AlertService.class);
        ContextCompat.startForegroundService(getContext(), intent);
    }

    @PluginMethod
    public void stop(PluginCall call) {
        AlertStore.setAlertsEnabled(getContext(), false);
        Intent intent = new Intent(getContext(), AlertService.class);
        getContext().stopService(intent);
        call.resolve();
    }
}
