package com.dineopssi.app;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;

import android.Manifest;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.content.Context;
import android.media.AudioAttributes;
import android.service.notification.StatusBarNotification;

import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;

import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;

/** Runs on a real Android system in CI. Shows the alert and checks what Android received. */
@RunWith(AndroidJUnit4.class)
public class AlarmNotificationsTest {

    private static final int ALERT_ID = 42;

    private Context context;
    private NotificationManager manager;

    @Before
    public void setUp() {
        context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        manager = context.getSystemService(NotificationManager.class);
        InstrumentationRegistry.getInstrumentation().getUiAutomation()
                .grantRuntimePermission(context.getPackageName(), Manifest.permission.POST_NOTIFICATIONS);
        manager.cancelAll();
    }

    @After
    public void tearDown() {
        manager.cancelAll();
    }

    private Notification active(int id) throws InterruptedException {
        for (int wait = 0; wait < 20; wait++) {
            for (StatusBarNotification posted : manager.getActiveNotifications()) {
                if (posted.getId() == id) return posted.getNotification();
            }
            Thread.sleep(100);
        }
        return null;
    }

    @Test
    public void channelRingsOnTheAlarmVolumeWithOurOwnSound() {
        AlarmNotifications.ensureChannel(context);
        NotificationChannel channel = manager.getNotificationChannel(AlarmNotifications.CHANNEL_ID);
        assertNotNull(channel);
        assertEquals(NotificationManager.IMPORTANCE_HIGH, channel.getImportance());
        assertEquals(AudioAttributes.USAGE_ALARM, channel.getAudioAttributes().getUsage());
        assertTrue(channel.getSound().toString().endsWith("/" + R.raw.dineops_alarm));
    }

    @Test
    public void alertKeepsRingingAndOffersAcknowledge() throws InterruptedException {
        AlarmNotifications.showAlert(
                context, ALERT_ID, "Table 4", "Table 4 is waiting", "https://example.com/ack", "token");
        Notification shown = active(ALERT_ID);
        assertNotNull(shown);
        assertNotEquals(0, shown.flags & Notification.FLAG_INSISTENT);
        assertEquals(AlarmNotifications.CHANNEL_ID, shown.getChannelId());
        assertEquals(AlarmNotifications.ALERT_RING_MILLIS, shown.getTimeoutAfter());
        assertEquals("Acknowledge", shown.actions[0].title.toString());
    }

    @Test
    public void cancelStopsTheRing() throws InterruptedException {
        AlarmNotifications.showAlert(context, ALERT_ID, "Table 4", "Waiting", "https://example.com/ack", "token");
        assertNotNull(active(ALERT_ID));
        AlarmNotifications.cancel(context, ALERT_ID);
        Thread.sleep(500);
        for (StatusBarNotification posted : manager.getActiveNotifications()) {
            assertNotEquals(ALERT_ID, posted.getId());
        }
    }

    @Test
    public void testRingStopsByItselfQuickly() throws InterruptedException {
        AlarmNotifications.showTest(context, "Test alert", "Test");
        Notification shown = active(AlarmNotifications.TEST_NOTIFICATION_ID);
        assertNotNull(shown);
        assertEquals(AlarmNotifications.TEST_RING_MILLIS, shown.getTimeoutAfter());
        assertEquals("Stop", shown.actions[0].title.toString());
    }
}
