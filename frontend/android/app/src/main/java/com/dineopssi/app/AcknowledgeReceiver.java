package com.dineopssi.app;

import android.app.NotificationManager;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

import androidx.core.app.NotificationCompat;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.IOException;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/** The button on a ringing alert. Stops the ring at once, then tells the server in the background. */
public class AcknowledgeReceiver extends BroadcastReceiver {

    static final String EXTRA_NOTIFICATION_ID = "notification_id";
    static final String EXTRA_ACK_URL = "ack_url";
    static final String EXTRA_ACK_TOKEN = "ack_token";

    private static final String TAG = "DineOpsAlarm";
    private static final int ATTEMPTS = 3;
    private static final int TIMEOUT_MILLIS = 6000;

    @Override
    public void onReceive(Context context, Intent intent) {
        int notificationId = intent.getIntExtra(EXTRA_NOTIFICATION_ID, AlarmNotifications.TEST_NOTIFICATION_ID);
        AlarmNotifications.cancel(context, notificationId);

        String url = intent.getStringExtra(EXTRA_ACK_URL);
        String token = intent.getStringExtra(EXTRA_ACK_TOKEN);
        if (url == null || token == null) return;

        Context app = context.getApplicationContext();
        PendingResult pending = goAsync();
        new Thread(() -> {
            try {
                if (!sendWithRetries(url, token)) showNotSent(app, notificationId);
            } finally {
                pending.finish();
            }
        }).start();
    }

    private static boolean sendWithRetries(String url, String token) {
        for (int attempt = 1; attempt <= ATTEMPTS; attempt++) {
            try {
                int status = post(url, token);
                if (status >= 200 && status < 300) return true;
                if (status < 500) return false;
            } catch (IOException | JSONException e) {
                Log.w(TAG, "Acknowledge attempt failed: " + e.getClass().getSimpleName());
            }
        }
        return false;
    }

    private static int post(String url, String token) throws IOException, JSONException {
        HttpURLConnection connection = (HttpURLConnection) new URL(url).openConnection();
        try {
            connection.setRequestMethod("POST");
            connection.setConnectTimeout(TIMEOUT_MILLIS);
            connection.setReadTimeout(TIMEOUT_MILLIS);
            connection.setDoOutput(true);
            connection.setRequestProperty("Content-Type", "application/json");
            byte[] body = new JSONObject().put("token", token).toString().getBytes(StandardCharsets.UTF_8);
            try (OutputStream output = connection.getOutputStream()) {
                output.write(body);
            }
            return connection.getResponseCode();
        } finally {
            connection.disconnect();
        }
    }

    /** The ring has stopped but nobody else knows, so say so instead of failing silently. */
    private static void showNotSent(Context context, int notificationId) {
        AlarmNotifications.ensureChannel(context);
        context.getSystemService(NotificationManager.class).notify(
                notificationId,
                new NotificationCompat.Builder(context, AlarmNotifications.CHANNEL_ID)
                        .setSmallIcon(R.drawable.ic_stat_alert)
                        .setContentTitle("Acknowledge wasn't sent")
                        .setContentText("No connection. Open DineOps SI and acknowledge the alert there.")
                        .setSilent(true)
                        .setAutoCancel(true)
                        .build());
    }
}
