package dev.openhalo.android.edge

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat

class AndroidEdgeService : Service() {
    private var client: AndroidEdgeClient? = null

    override fun onCreate() {
        super.onCreate()
        ensureServiceNotificationChannel()
        client = AndroidEdgeClient(
            context = applicationContext,
            initialState = EdgeDiagnosticsStore.current()
        ) { next ->
            EdgeDiagnosticsStore.update(next.copy(serviceState = "foreground"))
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action ?: ACTION_START) {
            ACTION_START -> {
                startAsForegroundService()
                val runtimeUrl = intent?.getStringExtra(EXTRA_RUNTIME_URL)
                    ?: EdgeDiagnosticsStore.current().runtimeUrl
                val deviceId = intent?.getStringExtra(EXTRA_DEVICE_ID)
                    ?: EdgeDiagnosticsStore.current().deviceId
                Log.i(LOG_TAG, "OPENHALO_EDGE_EVENT {\"event\":\"service_start_requested\"}")
                client?.connect(runtimeUrl, deviceId)
            }

            ACTION_SEND_OBSERVATIONS -> {
                startAsForegroundService()
                Log.i(LOG_TAG, "OPENHALO_EDGE_EVENT {\"event\":\"service_observation_requested\"}")
                client?.sendCurrentObservations()
            }

            ACTION_STOP -> {
                Log.i(LOG_TAG, "OPENHALO_EDGE_EVENT {\"event\":\"service_stop_requested\"}")
                client?.disconnect()
                EdgeDiagnosticsStore.update(
                    EdgeDiagnosticsStore.current().copy(serviceState = "stopped")
                )
                stopForeground(STOP_FOREGROUND_REMOVE)
                stopSelf()
            }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        client?.disconnect()
        client = null
        EdgeDiagnosticsStore.update(
            EdgeDiagnosticsStore.current().copy(serviceState = "stopped")
        )
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun startAsForegroundService() {
        val notification = serviceNotification()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(
                SERVICE_NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
            )
        } else {
            startForeground(SERVICE_NOTIFICATION_ID, notification)
        }
        EdgeDiagnosticsStore.update(
            EdgeDiagnosticsStore.current().copy(serviceState = "foreground")
        )
    }

    private fun serviceNotification(): Notification {
        val activityIntent = Intent(this, MainActivity::class.java)
        val pendingIntent = PendingIntent.getActivity(
            this,
            0,
            activityIntent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        return NotificationCompat.Builder(this, SERVICE_CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle("OpenHalo Android Edge")
            .setContentText("Presence edge session is running")
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()
    }

    private fun ensureServiceNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            return
        }
        val channel = NotificationChannel(
            SERVICE_CHANNEL_ID,
            "OpenHalo edge service",
            NotificationManager.IMPORTANCE_LOW
        )
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    companion object {
        const val ACTION_START = "dev.openhalo.android.edge.action.START"
        const val ACTION_STOP = "dev.openhalo.android.edge.action.STOP"
        const val ACTION_SEND_OBSERVATIONS =
            "dev.openhalo.android.edge.action.SEND_OBSERVATIONS"
        const val EXTRA_RUNTIME_URL = "runtime_url"
        const val EXTRA_DEVICE_ID = "device_id"
        private const val SERVICE_CHANNEL_ID = "openhalo_edge_service"
        private const val SERVICE_NOTIFICATION_ID = 1702
        private const val LOG_TAG = "OpenHaloEdge"

        fun startIntent(context: Context, runtimeUrl: String, deviceId: String): Intent =
            Intent(context, AndroidEdgeService::class.java).apply {
                action = ACTION_START
                putExtra(EXTRA_RUNTIME_URL, runtimeUrl)
                putExtra(EXTRA_DEVICE_ID, deviceId)
            }

        fun sendObservationsIntent(context: Context): Intent =
            Intent(context, AndroidEdgeService::class.java).apply {
                action = ACTION_SEND_OBSERVATIONS
            }

        fun stopIntent(context: Context): Intent =
            Intent(context, AndroidEdgeService::class.java).apply {
                action = ACTION_STOP
            }
    }
}
