package com.cloimism.stackpad.widget;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.res.ColorStateList;
import android.os.Build;
import android.os.Bundle;
import android.util.SizeF;
import android.view.View;
import android.widget.RemoteViews;
import com.cloimism.stackpad.R;
import java.time.OffsetDateTime;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;
import org.json.JSONArray;
import org.json.JSONObject;

/** Home screen widget showing the 5h and weekly limits of each agent provider. */
public class UsageWidgetProvider extends AppWidgetProvider {
    private static final String REFRESH = "com.cloimism.stackpad.widget.REFRESH";
    private static final int ROWS = 4;
    /** Below this height (dp) the 4x1 layout is used; two rows and more get the detailed layout. */
    private static final int DETAILED_HEIGHT = 120;
    private static final int GREEN = 0xFF75D9A5, ORANGE = 0xFFEFA668, RED = 0xFFF2A0A7;
    /** A spinner older than this belongs to a refresh whose process was killed, so it is hidden. */
    private static final long SPINNER_LIMIT = 90000;
    private static final ExecutorService TAPS = Executors.newSingleThreadExecutor();
    private static final AtomicBoolean TAP_RUNNING = new AtomicBoolean();

    @Override
    public void onEnabled(Context context) {
        UsageRefreshWorker.schedule(context);
    }

    @Override
    public void onDisabled(Context context) {
        UsageRefreshWorker.cancel(context);
    }

    @Override
    public void onUpdate(Context context, AppWidgetManager manager, int[] ids) {
        renderAll(context);
        UsageRefreshWorker.schedule(context);
        UsageRefreshWorker.refreshNow(context);
    }

    @Override
    public void onReceive(Context context, Intent intent) {
        super.onReceive(context, intent);
        // Repeated taps while a refresh runs are ignored instead of queueing more requests.
        if (!REFRESH.equals(intent.getAction()) || !TAP_RUNNING.compareAndSet(false, true)) return;
        Context app = context.getApplicationContext();
        // The foreground service keeps network access under Doze and battery saver; the receiver path is the fallback.
        if (UsageRefreshService.start(app)) return;
        PendingResult result = goAsync();
        TAPS.execute(() -> {
            try {
                UsageRefreshWorker.refreshFromTap(app);
            } finally {
                tapFinished();
                result.finish();
            }
        });
    }

    static void tapFinished() {
        TAP_RUNNING.set(false);
    }

    @Override
    public void onAppWidgetOptionsChanged(Context context, AppWidgetManager manager, int id, Bundle options) {
        renderAll(context);
    }

    public static void renderAll(Context context) {
        AppWidgetManager manager = AppWidgetManager.getInstance(context);
        for (int id : manager.getAppWidgetIds(new ComponentName(context, UsageWidgetProvider.class))) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                // The launcher picks the layout for the current size, including while the user resizes.
                Map<SizeF, RemoteViews> sizes = new HashMap<>();
                sizes.put(new SizeF(180f, 40f), render(context, false));
                sizes.put(new SizeF(180f, DETAILED_HEIGHT), render(context, true));
                manager.updateAppWidget(id, new RemoteViews(sizes));
            } else {
                int height = manager.getAppWidgetOptions(id).getInt(AppWidgetManager.OPTION_APPWIDGET_MIN_HEIGHT);
                manager.updateAppWidget(id, render(context, height >= DETAILED_HEIGHT));
            }
        }
    }

    private static RemoteViews render(Context context, boolean detailed) {
        RemoteViews views = new RemoteViews(context.getPackageName(), detailed ? R.layout.widget_usage : R.layout.widget_usage_compact);
        int flags = PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE;
        Intent refresh = new Intent(context, UsageWidgetProvider.class).setAction(REFRESH);
        // The root is @android:id/background so the launcher rounds the widget edge, not the content block.
        views.setOnClickPendingIntent(android.R.id.background, PendingIntent.getBroadcast(context, 0, refresh, flags));

        WidgetStore store = new WidgetStore(context);
        String problem = store.problem();
        JSONArray providers = null;
        try {
            if (store.usage() != null) providers = new JSONObject(store.usage()).getJSONArray("providers");
        } catch (Exception ignored) {
            providers = null;
        }
        if (store.token() == null) problem = problem != null ? problem : context.getString(R.string.widget_connects_after_sign_in);
        // There is no title row, so a dot marks values that could not be refreshed.
        views.setViewVisibility(R.id.status_dot, problem != null && providers != null ? View.VISIBLE : View.GONE);
        // An empty list means AI usage is turned off on the PC.
        boolean off = providers != null && providers.length() == 0;
        long since = store.refreshingSince();
        boolean refreshing = since > 0 && System.currentTimeMillis() - since < SPINNER_LIMIT;
        views.setViewVisibility(R.id.loading, refreshing ? View.VISIBLE : View.GONE);
        // The spinner replaces the placeholder text so the two do not overlap.
        views.setViewVisibility(R.id.empty, (providers == null || off) && !refreshing ? View.VISIBLE : View.GONE);
        views.setViewVisibility(R.id.rows, providers == null || off ? View.GONE : View.VISIBLE);
        views.setTextViewText(R.id.empty, context.getString(store.token() == null ? R.string.widget_sign_in : off ? R.string.widget_usage_off : R.string.widget_loading));
        String prefix = detailed ? "" : "c_";
        for (int row = 0; row < ROWS; row++) renderRow(context, views, prefix, detailed, row, providers == null ? null : providers.optJSONObject(row));
        return views;
    }

    private static int id(Context context, String name) {
        return context.getResources().getIdentifier(name, "id", context.getPackageName());
    }

    private static void renderRow(Context context, RemoteViews views, String prefix, boolean detailed, int row, JSONObject provider) {
        views.setViewVisibility(id(context, prefix + "row_" + row), provider == null ? View.GONE : View.VISIBLE);
        if (provider == null) return;
        String name = provider.optString("name");
        if (detailed && !provider.isNull("stale_minutes")) {
            int stale = provider.optInt("stale_minutes");
            name += "  " + (stale >= 60 ? context.getString(R.string.widget_hours_ago, stale / 60) : context.getString(R.string.widget_minutes_ago, stale));
        }
        views.setTextViewText(id(context, prefix + "name_" + row), name);
        boolean ok = "ok".equals(provider.optString("status"));
        JSONArray windows = provider.optJSONArray("windows");
        views.setViewVisibility(id(context, prefix + "message_" + row), ok ? View.GONE : View.VISIBLE);
        views.setTextViewText(id(context, prefix + "message_" + row), provider.isNull("message") ? context.getString(R.string.widget_unavailable) : provider.optString("message"));
        for (int column = 0; column < 2; column++) {
            JSONObject window = ok && windows != null ? windows.optJSONObject(column) : null;
            String suffix = "_" + row + "_" + column;
            views.setViewVisibility(id(context, prefix + "window" + suffix), window == null ? (ok ? View.INVISIBLE : View.GONE) : View.VISIBLE);
            if (window == null) continue;
            int percent = (int) Math.round(Math.max(0, Math.min(100, window.optDouble("used_percent", 0))));
            int color = percent >= 90 ? RED : percent >= 70 ? ORANGE : GREEN;
            views.setTextViewText(id(context, prefix + "label" + suffix), window.optString("label"));
            views.setProgressBar(id(context, prefix + "bar" + suffix), 100, percent, false);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                views.setColorStateList(id(context, prefix + "bar" + suffix), "setProgressTintList", ColorStateList.valueOf(color));
            }
            views.setTextViewText(id(context, prefix + "percent" + suffix), percent + "%");
            views.setTextColor(id(context, prefix + "percent" + suffix), color);
            views.setTextViewText(id(context, prefix + "reset" + suffix), remaining(window.isNull("resets_at") ? null : window.optString("resets_at")));
        }
    }

    /** Same short format as the web usage bar: 6d 9h, 2h 13m, 45m. */
    private static String remaining(String reset) {
        if (reset == null) return "";
        try {
            long minutes = Math.max(0, (long) Math.ceil((OffsetDateTime.parse(reset).toInstant().toEpochMilli() - System.currentTimeMillis()) / 60000.0));
            if (minutes >= 1440) return minutes / 1440 + "d " + minutes % 1440 / 60 + "h";
            if (minutes >= 60) return minutes / 60 + "h " + minutes % 60 + "m";
            return minutes + "m";
        } catch (Exception error) {
            return "";
        }
    }
}
