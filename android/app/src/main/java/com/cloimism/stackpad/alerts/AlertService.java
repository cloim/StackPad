package com.cloimism.stackpad.alerts;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.net.ConnectivityManager;
import android.net.Network;
import android.os.Build;
import android.os.IBinder;
import android.util.Log;
import androidx.annotation.Nullable;
import androidx.core.app.NotificationCompat;
import com.cloimism.stackpad.MainActivity;
import com.cloimism.stackpad.R;
import com.cloimism.stackpad.widget.WidgetStore;
import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicBoolean;

public class AlertService extends Service {
    private static final String TAG = "StackPadAlertService";
    public static final String CHANNEL_CONNECTION = "connection";
    public static final String CHANNEL_ALERTS = "pad-alerts";
    private static final int FOREGROUND_ID = 1001;

    private final AtomicBoolean running = new AtomicBoolean(false);
    private Thread workerThread;
    private ConnectivityManager connectivityManager;
    private ConnectivityManager.NetworkCallback networkCallback;

    @Override
    public void onCreate() {
        super.onCreate();
        createNotificationChannels();
        setupNetworkCallback();
    }

    private void createNotificationChannels() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationManager nm = getSystemService(NotificationManager.class);
            if (nm != null) {
                NotificationChannel connChannel = new NotificationChannel(
                        CHANNEL_CONNECTION,
                        getString(R.string.alert_channel_connection),
                        NotificationManager.IMPORTANCE_LOW
                );
                connChannel.setDescription(getString(R.string.alert_channel_connection_desc));
                nm.createNotificationChannel(connChannel);

                NotificationChannel alertChannel = new NotificationChannel(
                        CHANNEL_ALERTS,
                        getString(R.string.alert_channel_alerts),
                        NotificationManager.IMPORTANCE_HIGH
                );
                alertChannel.setDescription(getString(R.string.alert_channel_alerts_desc));
                alertChannel.enableVibration(true);
                nm.createNotificationChannel(alertChannel);
            }
        }
    }

    private void setupNetworkCallback() {
        connectivityManager = (ConnectivityManager) getSystemService(Context.CONNECTIVITY_SERVICE);
        if (connectivityManager != null) {
            networkCallback = new ConnectivityManager.NetworkCallback() {
                @Override
                public void onAvailable(Network network) {
                    if (running.get() && workerThread != null && workerThread.isAlive()) {
                        workerThread.interrupt();
                    }
                }
            };
            try {
                connectivityManager.registerDefaultNetworkCallback(networkCallback);
            } catch (Exception e) {
                Log.w(TAG, "Failed to register network callback", e);
            }
        }
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        startForeground(FOREGROUND_ID, buildForegroundNotification(getString(R.string.alert_service_connected)));
        if (!running.get()) {
            running.set(true);
            workerThread = new Thread(this::listenEvents, "StackPad-Alerts");
            workerThread.start();
        }
        return START_STICKY;
    }

    private Notification buildForegroundNotification(String text) {
        Intent notificationIntent = new Intent(this, MainActivity.class);
        PendingIntent pendingIntent = PendingIntent.getActivity(
                this, 0, notificationIntent,
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT
        );

        return new NotificationCompat.Builder(this, CHANNEL_CONNECTION)
                .setContentTitle(getString(R.string.app_name))
                .setContentText(text)
                .setSmallIcon(R.mipmap.ic_launcher)
                .setContentIntent(pendingIntent)
                .setOngoing(true)
                .setPriority(NotificationCompat.PRIORITY_LOW)
                .build();
    }

    private void listenEvents() {
        int backoffSec = 1;
        while (running.get()) {
            WidgetStore store = new WidgetStore(this);
            String origin = store.origin();
            if (origin == null || origin.isEmpty()) {
                origin = store.server();
            }
            String token = store.token();

            if (origin == null || origin.isEmpty() || token == null || token.isEmpty()) {
                try {
                    Thread.sleep(5000);
                } catch (InterruptedException ignored) {}
                continue;
            }

            HttpURLConnection conn = null;
            try {
                catchUpMissedAlerts(origin, token);

                String urlStr = origin + (origin.endsWith("/") ? "" : "/") + "api/events?topics=alert";
                URL url = new URL(urlStr);
                conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("GET");
                conn.setRequestProperty("Authorization", "Bearer " + token);
                conn.setRequestProperty("Accept", "text/event-stream");
                conn.setConnectTimeout(10000);
                conn.setReadTimeout(30000);

                int code = conn.getResponseCode();
                if (code == 200) {
                    backoffSec = 1;
                    InputStream is = conn.getInputStream();
                    BufferedReader reader = new BufferedReader(new InputStreamReader(is, StandardCharsets.UTF_8));
                    String line;
                    String currentEvent = "";
                    StringBuilder currentData = new StringBuilder();

                    while (running.get() && (line = reader.readLine()) != null) {
                        line = line.trim();
                        if (line.isEmpty()) {
                            if ("alert".equals(currentEvent) && currentData.length() > 0) {
                                try {
                                    JSONObject alert = new JSONObject(currentData.toString());
                                    handleAlert(alert);
                                } catch (Exception e) {
                                    Log.e(TAG, "Failed to parse alert data", e);
                                }
                            }
                            currentEvent = "";
                            currentData.setLength(0);
                        } else if (line.startsWith("event:")) {
                            currentEvent = line.substring(6).trim();
                        } else if (line.startsWith("data:")) {
                            currentData.append(line.substring(5).trim());
                        }
                    }
                }
            } catch (Exception e) {
                if (Thread.currentThread().isInterrupted()) {
                    backoffSec = 1;
                    continue;
                }
                Log.w(TAG, "Alert stream disconnected: " + e.getMessage());
            } finally {
                if (conn != null) {
                    conn.disconnect();
                }
            }

            if (running.get()) {
                try {
                    Thread.sleep(backoffSec * 1000L);
                } catch (InterruptedException ignored) {}
                backoffSec = Math.min(60, backoffSec * 2);
            }
        }
    }

    private void catchUpMissedAlerts(String origin, String token) {
        long lastId = AlertStore.getLastAlertId(this);
        if (lastId <= 0) return;
        HttpURLConnection conn = null;
        try {
            String urlStr = origin + (origin.endsWith("/") ? "" : "/") + "api/alerts?after=" + lastId;
            URL url = new URL(urlStr);
            conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("GET");
            conn.setRequestProperty("Authorization", "Bearer " + token);
            conn.setConnectTimeout(5000);
            conn.setReadTimeout(5000);
            if (conn.getResponseCode() == 200) {
                BufferedReader reader = new BufferedReader(new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8));
                StringBuilder sb = new StringBuilder();
                String line;
                while ((line = reader.readLine()) != null) {
                    sb.append(line);
                }
                JSONObject root = new JSONObject(sb.toString());
                JSONArray array = root.optJSONArray("alerts");
                if (array != null) {
                    for (int i = 0; i < array.length(); i++) {
                        handleAlert(array.getJSONObject(i));
                    }
                }
            }
        } catch (Exception e) {
            Log.w(TAG, "Catch-up failed: " + e.getMessage());
        } finally {
            if (conn != null) conn.disconnect();
        }
    }

    private void handleAlert(JSONObject alert) {
        long id = alert.optLong("id", 0);
        if (id > 0) {
            AlertStore.setLastAlertId(this, id);
        }
        String padId = alert.optString("pad_id", "");
        String padName = alert.optString("pad_name", "StackPad");
        String kind = alert.optString("kind", "");
        String message = alert.optString("message", "");

        String title;
        if ("crashed".equals(kind)) {
            title = padName + ": " + (isKorean() ? "비정상 종료" : "Crashed");
        } else if ("restarted".equals(kind)) {
            title = padName + ": " + (isKorean() ? "자동 재시작" : "Restarted");
        } else if ("gave_up".equals(kind)) {
            title = padName + ": " + (isKorean() ? "재시작 포기" : "Gave up restarting");
        } else if ("unhealthy".equals(kind)) {
            title = padName + ": " + (isKorean() ? "응답 이상" : "Unhealthy");
        } else if ("schedule_failed".equals(kind)) {
            title = padName + ": " + (isKorean() ? "예약 실행 실패" : "Schedule failed");
        } else if ("scene_failed".equals(kind)) {
            title = padName + ": " + (isKorean() ? "장면 실행 실패" : "Scene failed");
        } else {
            title = padName;
        }

        Intent intent = new Intent(this, MainActivity.class);
        if (!padId.isEmpty()) {
            intent.putExtra("pad_id", padId);
        }
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        PendingIntent pendingIntent = PendingIntent.getActivity(
                this,
                (int) (id % 10000),
                intent,
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT
        );

        Notification notification = new NotificationCompat.Builder(this, CHANNEL_ALERTS)
                .setContentTitle(title)
                .setContentText(message)
                .setSmallIcon(R.mipmap.ic_launcher)
                .setContentIntent(pendingIntent)
                .setAutoCancel(true)
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .build();

        NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        if (nm != null) {
            nm.notify((int) (id > 0 ? id : System.currentTimeMillis()), notification);
        }
    }

    private boolean isKorean() {
        return getResources().getConfiguration().getLocales().get(0).getLanguage().startsWith("ko");
    }

    @Override
    public void onDestroy() {
        running.set(false);
        if (workerThread != null) {
            workerThread.interrupt();
        }
        if (connectivityManager != null && networkCallback != null) {
            try {
                connectivityManager.unregisterNetworkCallback(networkCallback);
            } catch (Exception ignored) {}
        }
        stopForeground(true);
        super.onDestroy();
    }

    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
