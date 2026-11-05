package com.dineopssi.app;

import android.Manifest;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.PowerManager;
import android.provider.Settings;

import com.getcapacitor.JSObject;
import com.getcapacitor.PermissionState;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;
import com.google.firebase.FirebaseApp;
import com.google.firebase.messaging.FirebaseMessaging;

/** What the web screens can ask the phone to do. */
@CapacitorPlugin(
        name = "DineOpsPush",
        permissions = @Permission(alias = "notifications", strings = {Manifest.permission.POST_NOTIFICATIONS}))
public class DineOpsPushPlugin extends Plugin {

    @PluginMethod
    public void status(PluginCall call) {
        Context context = getContext();
        AlarmNotifications.ensureChannel(context);
        NotificationManager manager = context.getSystemService(NotificationManager.class);
        NotificationChannel channel = manager.getNotificationChannel(AlarmNotifications.CHANNEL_ID);
        PowerManager power = context.getSystemService(PowerManager.class);

        JSObject result = new JSObject();
        result.put("firebaseReady", !FirebaseApp.getApps(context).isEmpty());
        result.put("notificationsAllowed", manager.areNotificationsEnabled());
        result.put("ringEnabled", channel != null
                && channel.getImportance() >= NotificationManager.IMPORTANCE_HIGH
                && channel.getSound() != null);
        result.put("batteryUnrestricted", power.isIgnoringBatteryOptimizations(context.getPackageName()));
        call.resolve(result);
    }

    @PluginMethod
    public void requestPermission(PluginCall call) {
        boolean needsAsking = Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU
                && getPermissionState("notifications") != PermissionState.GRANTED;
        if (needsAsking) {
            requestPermissionForAlias("notifications", call, "permissionAnswered");
        } else {
            status(call);
        }
    }

    @PermissionCallback
    private void permissionAnswered(PluginCall call) {
        status(call);
    }

    @PluginMethod
    public void getToken(PluginCall call) {
        if (FirebaseApp.getApps(getContext()).isEmpty()) {
            call.reject("This build of the app isn't connected to Firebase", "FIREBASE_NOT_SET_UP");
            return;
        }
        FirebaseMessaging.getInstance().getToken().addOnCompleteListener(task -> {
            if (task.isSuccessful() && task.getResult() != null) {
                JSObject result = new JSObject();
                result.put("token", task.getResult());
                call.resolve(result);
            } else {
                call.reject("Could not reach Firebase", "FIREBASE_UNAVAILABLE");
            }
        });
    }

    @PluginMethod
    public void testRing(PluginCall call) {
        AlarmNotifications.showTest(getContext(), "Test alert", "This is how a table alert sounds. Tap Stop to end it.");
        call.resolve();
    }

    @PluginMethod
    public void openNotificationSettings(PluginCall call) {
        Intent intent = new Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                .putExtra(Settings.EXTRA_APP_PACKAGE, getContext().getPackageName());
        getActivity().startActivity(intent);
        call.resolve();
    }

    /** Battery options differ by phone brand, but all of them are reachable from the app's page. */
    @PluginMethod
    public void openAppSettings(PluginCall call) {
        Intent intent = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
                .setData(Uri.parse("package:" + getContext().getPackageName()));
        getActivity().startActivity(intent);
        call.resolve();
    }
}
