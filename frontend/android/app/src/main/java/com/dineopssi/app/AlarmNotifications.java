package com.dineopssi.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.media.AudioAttributes;
import android.net.Uri;

import androidx.core.app.NotificationCompat;

/** Shows table alerts that keep ringing, on the alarm volume, until someone responds. */
public final class AlarmNotifications {

    // Android fixes a channel's sound when it is created. To change the sound, change this id.
    static final String CHANNEL_ID = "table_alerts_v1";
    static final int TEST_NOTIFICATION_ID = -1;

    static final long ALERT_RING_MILLIS = 5 * 60 * 1000L;
    static final long TEST_RING_MILLIS = 20 * 1000L;

    private static final long[] VIBRATION = {0, 700, 300, 700, 300, 700};

    private AlarmNotifications() {}

    static void ensureChannel(Context context) {
        NotificationManager manager = context.getSystemService(NotificationManager.class);
        if (manager.getNotificationChannel(CHANNEL_ID) != null) return;

        NotificationChannel channel =
                new NotificationChannel(CHANNEL_ID, "Table alerts", NotificationManager.IMPORTANCE_HIGH);
        channel.setDescription("Rings when a table needs a waiter or needs cleaning");
        Uri sound = Uri.parse("android.resource://" + context.getPackageName() + "/" + R.raw.dineops_alarm);
        channel.setSound(
                sound,
                new AudioAttributes.Builder()
                        // The alarm volume is separate from the ringer, so silent mode doesn't mute it.
                        .setUsage(AudioAttributes.USAGE_ALARM)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                        .build());
        channel.enableVibration(true);
        channel.setVibrationPattern(VIBRATION);
        channel.setLockscreenVisibility(Notification.VISIBILITY_PUBLIC);
        manager.createNotificationChannel(channel);
    }

    /** Rings for a real alert. The Acknowledge button tells the server someone is on it. */
    static void showAlert(Context context, int alertId, String title, String body, String ackUrl, String ackToken) {
        Intent acknowledge = new Intent(context, AcknowledgeReceiver.class)
                .putExtra(AcknowledgeReceiver.EXTRA_NOTIFICATION_ID, alertId)
                .putExtra(AcknowledgeReceiver.EXTRA_ACK_URL, ackUrl)
                .putExtra(AcknowledgeReceiver.EXTRA_ACK_TOKEN, ackToken);
        show(context, alertId, title, body, "Acknowledge", acknowledge, ALERT_RING_MILLIS);
    }

    /** Rings briefly so staff can check their phone's volume and settings. */
    static void showTest(Context context, String title, String body) {
        Intent stop = new Intent(context, AcknowledgeReceiver.class)
                .putExtra(AcknowledgeReceiver.EXTRA_NOTIFICATION_ID, TEST_NOTIFICATION_ID);
        show(context, TEST_NOTIFICATION_ID, title, body, "Stop", stop, TEST_RING_MILLIS);
    }

    static void cancel(Context context, int notificationId) {
        context.getSystemService(NotificationManager.class).cancel(notificationId);
    }

    private static void show(
            Context context, int id, String title, String body, String actionLabel, Intent action, long ringMillis) {
        ensureChannel(context);
        int immutable = PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE;
        Intent open = new Intent(context, MainActivity.class)
                .setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);

        Notification notification = new NotificationCompat.Builder(context, CHANNEL_ID)
                .setSmallIcon(R.drawable.ic_stat_alert)
                .setContentTitle(title)
                .setContentText(body)
                .setStyle(new NotificationCompat.BigTextStyle().bigText(body))
                .setCategory(NotificationCompat.CATEGORY_ALARM)
                .setPriority(NotificationCompat.PRIORITY_MAX)
                .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
                // Can't be swiped away by accident: it needs a tap, a button, or the timeout.
                .setOngoing(true)
                .setAutoCancel(true)
                .setTimeoutAfter(ringMillis)
                .setContentIntent(PendingIntent.getActivity(context, id, open, immutable))
                .addAction(0, actionLabel, PendingIntent.getBroadcast(context, id, action, immutable))
                .build();
        // Repeats the sound until the notification goes away.
        notification.flags |= Notification.FLAG_INSISTENT;
        context.getSystemService(NotificationManager.class).notify(id, notification);
    }
}
