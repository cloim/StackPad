package com.cloimism.stackpad.alerts;

import android.content.Context;
import android.content.SharedPreferences;

public final class AlertStore {
    private static final String PREF_NAME = "stackpad_alerts";
    private static final String KEY_ENABLED = "alerts_enabled";
    private static final String KEY_LAST_ID = "last_alert_id";

    private static SharedPreferences getPrefs(Context context) {
        return context.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE);
    }

    public static boolean isAlertsEnabled(Context context) {
        return getPrefs(context).getBoolean(KEY_ENABLED, false);
    }

    public static void setAlertsEnabled(Context context, boolean enabled) {
        getPrefs(context).edit().putBoolean(KEY_ENABLED, enabled).apply();
    }

    public static long getLastAlertId(Context context) {
        return getPrefs(context).getLong(KEY_LAST_ID, 0);
    }

    public static void setLastAlertId(Context context, long id) {
        getPrefs(context).edit().putLong(KEY_LAST_ID, id).apply();
    }
}
