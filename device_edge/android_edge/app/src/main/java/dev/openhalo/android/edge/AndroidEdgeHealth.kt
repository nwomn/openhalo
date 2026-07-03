package dev.openhalo.android.edge

import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.PowerManager
import android.provider.Settings

object AndroidEdgeHealth {
    fun batteryOptimizationState(context: Context): String {
        val powerManager = context.getSystemService(PowerManager::class.java)
        return if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) {
            "not required"
        } else if (powerManager.isIgnoringBatteryOptimizations(context.packageName)) {
            "unrestricted"
        } else {
            "may restrict background"
        }
    }

    fun fullScreenAlertState(context: Context): String {
        return if (Build.VERSION.SDK_INT < 34) {
            "available"
        } else if (context.getSystemService(NotificationManager::class.java)
                .canUseFullScreenIntent()
        ) {
            "available"
        } else {
            "needs permission"
        }
    }

    fun batterySettingsIntent(context: Context): Intent {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).apply {
                data = Uri.parse("package:${context.packageName}")
            }
        } else {
            Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                data = Uri.parse("package:${context.packageName}")
            }
        }
    }

    fun appNotificationSettingsIntent(context: Context): Intent {
        return Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).apply {
            putExtra(Settings.EXTRA_APP_PACKAGE, context.packageName)
        }
    }

    fun fullScreenAlertSettingsIntent(context: Context): Intent {
        return if (Build.VERSION.SDK_INT >= 34) {
            Intent(Settings.ACTION_MANAGE_APP_USE_FULL_SCREEN_INTENT).apply {
                data = Uri.parse("package:${context.packageName}")
            }
        } else {
            appNotificationSettingsIntent(context)
        }
    }
}
