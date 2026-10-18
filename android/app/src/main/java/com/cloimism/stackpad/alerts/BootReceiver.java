package com.cloimism.stackpad.alerts;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import androidx.core.content.ContextCompat;
import com.cloimism.stackpad.widget.WidgetStore;

public class BootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        if (Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())) {
            if (AlertStore.isAlertsEnabled(context)) {
                WidgetStore store = new WidgetStore(context);
                if (store.token() != null && !store.token().isEmpty()) {
                    Intent serviceIntent = new Intent(context, AlertService.class);
                    ContextCompat.startForegroundService(context, serviceIntent);
                }
            }
        }
    }
}
