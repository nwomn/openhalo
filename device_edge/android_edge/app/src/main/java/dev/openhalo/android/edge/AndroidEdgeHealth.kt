package dev.openhalo.android.edge

import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.PowerManager
import android.provider.Settings
import android.text.TextUtils
import java.util.Locale

object AndroidEdgeHealth {
    fun accessibilityServiceState(context: Context): String {
        val expected = "${context.packageName}/${OpenHaloAccessibilityService::class.java.name}"
        val enabled = Settings.Secure.getString(
            context.contentResolver,
            Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES
        ) ?: return "disabled"
        return if (enabled.split(':').any { TextUtils.equals(it, expected) }) {
            "enabled"
        } else {
            "disabled"
        }
    }

    fun accessibilitySettingsIntent(): Intent =
        Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)

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

    fun backgroundPermissionGuidance(
        manufacturer: String = Build.MANUFACTURER,
        batteryState: String
    ): String {
        if (batteryState == "unrestricted" || batteryState == "not required") {
            return "ready for foreground-service background observation"
        }
        val vendor = manufacturer.lowercase(Locale.US)
        val vendorHint = when {
            vendor.contains("xiaomi") || vendor.contains("redmi") -> {
                "enable Autostart and set Battery saver to No restrictions"
            }
            vendor.contains("huawei") || vendor.contains("honor") -> {
                "allow app launch/background running in Battery settings"
            }
            vendor.contains("oppo") || vendor.contains("oneplus") || vendor.contains("realme") -> {
                "allow background activity and disable app battery optimization"
            }
            vendor.contains("vivo") || vendor.contains("iqoo") -> {
                "allow high background power use and autostart"
            }
            vendor.contains("samsung") -> {
                "remove OpenHalo from Sleeping apps and allow background usage"
            }
            else -> "allow unrestricted battery/background usage for OpenHalo"
        }
        return "may restrict background; $vendorHint"
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
