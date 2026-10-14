package com.cloimism.stackpad.widget;

import android.content.Context;
import android.content.SharedPreferences;
import androidx.security.crypto.EncryptedSharedPreferences;
import androidx.security.crypto.MasterKey;

/** Keeps the widget token encrypted with an Android Keystore key, plus the last usage response for offline display. */
public final class WidgetStore {
    private static final String FILE = "stackpad_widget";
    private final SharedPreferences preferences;

    public WidgetStore(Context context) {
        try {
            MasterKey key = new MasterKey.Builder(context).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build();
            preferences = EncryptedSharedPreferences.create(context, FILE, key,
                    EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
                    EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM);
        } catch (Exception error) {
            throw new IllegalStateException("Widget storage is unavailable", error);
        }
    }

    public String id() { return preferences.getString("id", null); }
    public String token() { return preferences.getString("token", null); }
    public String origin() { return preferences.getString("origin", null); }
    public String usage() { return preferences.getString("usage", null); }
    /** The PC address the app paired with; it outlives sign-outs so the app can reconnect. */
    public String server() { return preferences.getString("server", null); }
    public void saveServer(String url) { preferences.edit().putString("server", url).apply(); }
    public long fetchedAt() { return preferences.getLong("fetched_at", 0); }
    public String problem() { return preferences.getString("problem", null); }

    public void connect(String id, String token, String origin) {
        preferences.edit().putString("id", id).putString("token", token).putString("origin", origin).remove("problem").apply();
    }

    public void clear() {
        preferences.edit().clear().apply();
    }

    public void saveUsage(String json, long fetchedAt) {
        preferences.edit().putString("usage", json).putLong("fetched_at", fetchedAt).remove("problem").apply();
    }

    public void saveProblem(String message) {
        preferences.edit().putString("problem", message).apply();
    }

    /** A revoked device keeps no usage history, so the widget asks for a new login instead of showing stale numbers. */
    public void revoke(String message) {
        preferences.edit().remove("id").remove("token").remove("usage").remove("fetched_at").putString("problem", message).apply();
    }
}
