package com.cloimism.stackpad.widget;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.IBinder;
import androidx.annotation.Nullable;
import androidx.core.app.NotificationCompat;
import com.cloimism.stackpad.R;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Runs a widget tap refresh as a short foreground service.
 * A broadcast receiver counts as a background process, so Doze and battery saver cut its network;
 * a foreground service keeps it, and a widget tap is allowed to start one from the background.
 */
public class UsageRefreshService extends Service {
    private static final String CHANNEL = "widget-refresh";
    private static final int NOTIFICATION_ID = 1002;
    private static final ExecutorService WORK = Executors.newSingleThreadExecutor();

    /** Returns false when the system refuses the foreground service, so the caller refreshes in the receiver instead. */
    static boolean start(Context context) {
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) context.startForegroundService(new Intent(context, UsageRefreshService.class));
            else context.startService(new Intent(context, UsageRefreshService.class));
            return true;
        } catch (IllegalStateException | SecurityException refused) {
            return false;
        }
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        Notification notification = notification();
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SHORT_SERVICE);
        } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC);
        } else {
            startForeground(NOTIFICATION_ID, notification);
        }
        Context app = getApplicationContext();
        WORK.execute(() -> {
            try {
                UsageRefreshWorker.refreshFromTap(app);
            } finally {
                UsageWidgetProvider.tapFinished();
                stopSelf(startId);
            }
        });
        return START_NOT_STICKY;
    }

    /** A short service must stop within 3 minutes; the tap fetch ends long before, so this only guards a hang. */
    @Override
    public void onTimeout(int startId) {
        stopSelf(startId);
    }

    @Override
    public void onTimeout(int startId, int fgsType) {
        stopSelf(startId);
    }

    private Notification notification() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(CHANNEL, getString(R.string.widget_refresh_channel), NotificationManager.IMPORTANCE_MIN);
            channel.setDescription(getString(R.string.widget_refresh_channel_desc));
            getSystemService(NotificationManager.class).createNotificationChannel(channel);
        }
        // Android 12+ delays the notification by 10 seconds, so a normal refresh ends before it appears.
        return new NotificationCompat.Builder(this, CHANNEL)
                .setContentTitle(getString(R.string.widget_refreshing))
                .setSmallIcon(R.mipmap.ic_launcher)
                .setPriority(NotificationCompat.PRIORITY_MIN)
                .setSilent(true)
                .build();
    }

    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
