package com.cloimism.stackpad.widget;

import android.content.Context;
import android.util.Log;
import androidx.annotation.NonNull;
import androidx.work.Constraints;
import androidx.work.ExistingPeriodicWorkPolicy;
import androidx.work.ExistingWorkPolicy;
import androidx.work.NetworkType;
import androidx.work.OneTimeWorkRequest;
import androidx.work.PeriodicWorkRequest;
import androidx.work.WorkManager;
import androidx.work.Worker;
import androidx.work.WorkerParameters;
import com.cloimism.stackpad.R;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.concurrent.TimeUnit;
import java.util.function.BooleanSupplier;
import org.json.JSONObject;

/** Fetches /api/widget/usage with the device token and redraws every placed widget. */
public class UsageRefreshWorker extends Worker {
    private static final String PERIODIC = "stackpad-usage-periodic";
    private static final String NOW = "stackpad-usage-now";
    private static final String TAG = "StackPadWidget";
    /** Pauses before the second and third attempt; a short pause is enough for transient glitches. */
    private static final long[] RETRY_DELAYS = {2000, 4000};

    public UsageRefreshWorker(@NonNull Context context, @NonNull WorkerParameters parameters) {
        super(context, parameters);
    }

    /** Android allows 15 minutes as the shortest periodic interval. */
    private static Constraints online() {
        return new Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build();
    }

    public static void schedule(Context context) {
        PeriodicWorkRequest request = new PeriodicWorkRequest.Builder(UsageRefreshWorker.class, 15, TimeUnit.MINUTES)
                .setConstraints(online()).build();
        WorkManager.getInstance(context).enqueueUniquePeriodicWork(PERIODIC, ExistingPeriodicWorkPolicy.KEEP, request);
    }

    public static void cancel(Context context) {
        WorkManager.getInstance(context).cancelUniqueWork(PERIODIC);
    }

    public static void refreshNow(Context context) {
        // KEEP lets a running request finish; replacing it would cancel the connection mid-flight.
        OneTimeWorkRequest request = new OneTimeWorkRequest.Builder(UsageRefreshWorker.class).setConstraints(online()).build();
        WorkManager.getInstance(context).enqueueUniqueWork(NOW, ExistingWorkPolicy.KEEP, request);
    }

    /** A tap fetches inside the click broadcast, skipping the WorkManager queue and the engine's 60 second cache. */
    static void refreshFromTap(Context context) {
        WidgetStore store = new WidgetStore(context);
        if (store.token() == null) {
            UsageWidgetProvider.renderAll(context);
            return;
        }
        store.markRefreshing(true);
        UsageWidgetProvider.renderAll(context);
        boolean done = false;
        try {
            done = fetch(context, store, true, false, () -> false);
        } finally {
            if (done) {
                store.markRefreshing(false);
                UsageWidgetProvider.renderAll(context);
            }
        }
        // A network hiccup goes to the worker, which keeps the spinner and retries with pauses the broadcast cannot afford.
        if (!done) refreshNow(context);
    }

    @NonNull
    @Override
    public Result doWork() {
        Context context = getApplicationContext();
        WidgetStore store = new WidgetStore(context);
        try {
            if (store.token() == null) return Result.success();
            store.markRefreshing(true);
            UsageWidgetProvider.renderAll(context);
            for (int attempt = 0; !fetch(context, store, false, attempt == RETRY_DELAYS.length, this::isStopped); attempt++) {
                Thread.sleep(RETRY_DELAYS[attempt]);
                if (isStopped()) break;
            }
            return Result.success();
        } catch (InterruptedException error) {
            return Result.success();
        } finally {
            store.markRefreshing(false);
            if (!isStopped()) UsageWidgetProvider.renderAll(context);
        }
    }

    /** Returns false for a transient network failure that should be retried; the message is shown only on the last attempt. */
    private static boolean fetch(Context context, WidgetStore store, boolean refresh, boolean lastAttempt, BooleanSupplier stopped) {
        HttpURLConnection connection = null;
        try {
            connection = (HttpURLConnection) new URL(store.origin() + "/api/widget/usage" + (refresh ? "?refresh=1" : "")).openConnection();
            connection.setConnectTimeout(refresh ? 3000 : 10000);
            connection.setReadTimeout(refresh ? 5000 : 20000);
            connection.setInstanceFollowRedirects(false);
            connection.setRequestProperty("Accept", "application/json");
            // The engine answers in this language, so provider messages match the phone.
            connection.setRequestProperty("Accept-Language", Locale.getDefault().toLanguageTag());
            // A pooled connection idle for 15 minutes may already be closed by the tunnel.
            connection.setRequestProperty("Connection", "close");
            connection.setRequestProperty("Authorization", "Bearer " + store.token());
            int status = connection.getResponseCode();
            String type = connection.getContentType();
            if (status == 200) {
                String body = read(connection.getInputStream());
                new JSONObject(body).getJSONArray("providers");
                store.saveUsage(body, System.currentTimeMillis());
            } else if (status == 401 && type != null && type.startsWith("application/json")) {
                store.revoke(context.getString(R.string.widget_sign_in_again));
            } else if (status == 502 || status == 503 || status == 530) {
                store.saveProblem(context.getString(R.string.widget_engine_off));
            } else if (status >= 300 && status < 500) {
                store.saveProblem(context.getString(R.string.widget_check_access));
            } else {
                store.saveProblem(context.getString(R.string.widget_usage_failed));
            }
        } catch (IOException error) {
            if (stopped.getAsBoolean()) return true;
            Log.w(TAG, "Usage request failed: " + error.getClass().getSimpleName() + " " + error.getMessage());
            if (!lastAttempt) return false;
            store.saveProblem(context.getString(R.string.widget_check_network));
        } catch (Exception error) {
            Log.w(TAG, "Usage response rejected: " + error.getClass().getSimpleName());
            store.saveProblem(context.getString(R.string.widget_usage_failed));
        } finally {
            if (connection != null) connection.disconnect();
        }
        return true;
    }

    private static String read(InputStream input) throws IOException {
        try (InputStream source = input; ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[8192];
            int length;
            while ((length = source.read(buffer)) != -1) output.write(buffer, 0, length);
            return output.toString(StandardCharsets.UTF_8.name());
        }
    }
}
