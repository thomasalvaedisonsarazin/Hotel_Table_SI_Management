package com.dineopssi.app;

import androidx.annotation.NonNull;

import com.google.firebase.messaging.FirebaseMessagingService;
import com.google.firebase.messaging.RemoteMessage;

import java.util.Map;

/** Receives messages from the server, even when the app is closed, and starts or stops the ring. */
public class AlarmMessagingService extends FirebaseMessagingService {

    @Override
    public void onMessageReceived(@NonNull RemoteMessage message) {
        Map<String, String> data = message.getData();
        String kind = data.get("kind");
        if (kind == null) return;

        switch (kind) {
            case "alert": {
                Integer alertId = parseId(data.get("alert_id"));
                if (alertId != null) {
                    AlarmNotifications.showAlert(
                            this, alertId, data.get("title"), data.get("body"), data.get("ack_url"), data.get("ack_token"));
                }
                break;
            }
            case "cancel": {
                Integer alertId = parseId(data.get("alert_id"));
                if (alertId != null) AlarmNotifications.cancel(this, alertId);
                break;
            }
            case "test":
                AlarmNotifications.showTest(this, data.get("title"), data.get("body"));
                break;
            default:
                break;
        }
    }

    private static Integer parseId(String value) {
        try {
            return value == null ? null : Integer.valueOf(value);
        } catch (NumberFormatException e) {
            return null;
        }
    }

    // A new phone address is picked up and sent to the server the next time the app opens.
    @Override
    public void onNewToken(@NonNull String token) {}
}
