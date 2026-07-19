package dev.openhalo.android.edge

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat

object RuntimeNotificationPresenter {
    private const val CHANNEL_ID = "openhalo_runtime_alerts_v3"
    private const val CHANNEL_NAME = "OpenHalo runtime alerts"
    private const val URGENT_CHANNEL_ID = "openhalo_runtime_urgent_alerts_v1"
    private const val URGENT_CHANNEL_NAME = "OpenHalo urgent alerts"

    fun canPostNotifications(context: Context): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
            ContextCompat.checkSelfPermission(
                context,
                Manifest.permission.POST_NOTIFICATIONS
            ) == PackageManager.PERMISSION_GRANTED

    fun ensureNotificationChannel(context: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            return
        }
        val channel = alertChannel(
            CHANNEL_ID,
            CHANNEL_NAME,
            "User-visible OpenHalo runtime messages."
        )
        val urgentChannel = alertChannel(
            URGENT_CHANNEL_ID,
            URGENT_CHANNEL_NAME,
            "Time-sensitive OpenHalo alerts that may open an alert screen."
        )
        context.getSystemService(NotificationManager::class.java)
            .createNotificationChannels(listOf(channel, urgentChannel))
    }

    fun show(context: Context, title: String, body: String): String {
        ensureNotificationChannel(context)
        if (!canPostNotifications(context)) {
            return "POST_NOTIFICATIONS permission is not granted"
        }
        val launchIntent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra(MainActivity.EXTRA_INITIAL_VIEW, MainActivity.VIEW_NOTIFICATIONS)
        }
        val contentIntent = PendingIntent.getActivity(
            context,
            0,
            launchIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_MESSAGE)
            .setDefaults(NotificationCompat.DEFAULT_ALL)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setContentIntent(contentIntent)
            .setAutoCancel(true)
            .build()
        NotificationManagerCompat.from(context).notify(
            (System.currentTimeMillis() % Int.MAX_VALUE).toInt(),
            notification
        )
        return ""
    }

    fun showUrgent(context: Context, message: String): String {
        ensureNotificationChannel(context)
        if (!canPostNotifications(context)) {
            return "POST_NOTIFICATIONS permission is not granted"
        }
        val alertIntent = Intent(context, RuntimeAlertActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or
                Intent.FLAG_ACTIVITY_CLEAR_TOP or
                Intent.FLAG_ACTIVITY_SINGLE_TOP
            putExtra(RuntimeAlertActivity.EXTRA_MESSAGE, message)
        }
        val alertPendingIntent = PendingIntent.getActivity(
            context,
            1,
            alertIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val notification = NotificationCompat.Builder(context, URGENT_CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle("OpenHalo Alert")
            .setContentText(message)
            .setStyle(NotificationCompat.BigTextStyle().bigText(message))
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setDefaults(NotificationCompat.DEFAULT_ALL)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setContentIntent(alertPendingIntent)
            .setFullScreenIntent(alertPendingIntent, true)
            .setAutoCancel(true)
            .build()
        NotificationManagerCompat.from(context).notify(
            (System.currentTimeMillis() % Int.MAX_VALUE).toInt(),
            notification
        )
        return ""
    }

    private fun alertChannel(
        id: String,
        name: String,
        description: String
    ): NotificationChannel {
        val channel = NotificationChannel(
            id,
            name,
            NotificationManager.IMPORTANCE_HIGH
        )
        channel.description = description
        channel.enableVibration(true)
        channel.lockscreenVisibility = Notification.VISIBILITY_PUBLIC
        return channel
    }
}
